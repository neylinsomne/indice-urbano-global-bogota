"""
Agente LLM con acceso a tools para consultar datos inmobiliarios
Usa LangChain para SQL Agent + tools personalizadas
"""
from typing import Dict, Any, List, Optional
import asyncpg
import json as json_module
import logging
import os
import re
import time
from decimal import Decimal
from dotenv import load_dotenv

from .tools import AVAILABLE_TOOLS
from .cache_manager import llm_cache

load_dotenv()
logger = logging.getLogger(__name__)

# Intentar importar LangChain (opcional)
try:
    from langchain_community.agent_toolkits import create_sql_agent
    from langchain_community.utilities import SQLDatabase
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain no disponible. Funcionalidad LLM limitada a tools predefinidas.")

# Intentar importar proveedores LLM (orden: Ollama → Gemini → OpenAI)
LLM_PROVIDER = None
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    LLM_PROVIDER = "gemini"
except ImportError:
    pass

_ChatOpenAI = None
try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI
    if not LLM_PROVIDER:
        LLM_PROVIDER = "openai"
except ImportError:
    pass

_OLLAMA_AVAILABLE = False
try:
    from langchain_ollama import ChatOllama
    _OLLAMA_AVAILABLE = True
except ImportError:
    pass

if not LLM_PROVIDER and not _OLLAMA_AVAILABLE:
    logger.warning("Ningun proveedor LLM disponible (ni Ollama, ni Gemini, ni OpenAI).")


LOCALIDADES = [
    'CHAPINERO', 'SUBA', 'USAQUEN', 'KENNEDY', 'ENGATIVA',
    'FONTIBON', 'TEUSAQUILLO', 'BARRIOS UNIDOS', 'SANTA FE',
    'CANDELARIA', 'BOSA', 'CIUDAD BOLIVAR', 'RAFAEL URIBE URIBE',
    'SAN CRISTOBAL', 'TUNJUELITO', 'ANTONIO NARIÑO', 'PUENTE ARANDA',
    'MARTIRES', 'USME', 'SUMAPAZ'
]

RAW_SQL_PATTERNS = [
    r'^\s*\[?\s*\(',
    r'\(\d+,\s*(None|\')',
    r"^\s*\[\(.*\)\]\s*$",
    r"Decimal\(",
]

CLARIFICATION_PROMPT = """Eres un asistente inmobiliario inteligente que ayuda a construir busquedas precisas.
Tu trabajo es analizar la consulta del usuario y decidir si necesitas clarificar informacion CRITICA antes de buscar.

DATOS DISPONIBLES:
- Ciudades: Actualmente solo Bogota (21 localidades). Proximamente mas ciudades.
- Localidades de Bogota: {localidades}
- Tipos de inmueble: Apartamento, Casa, Lote, Local, Oficina, Bodega
- Amenidades (booleanos en BD): piscina, gimnasio, parqueadero, vigilancia, ascensor, salon comunal, BBQ, cancha, jacuzzi, deposito
- Indicadores: I_URB (calidad urbana 0-5), I_ACC (accesibilidad), I_SEG (seguridad), I_HED (precio hedonico)
- Dotaciones/POIs: hospitales (dotacion_salud), colegios (dotacion_educacion), parques, centros comerciales, farmacias (dotaciones_poi)
- NO tenemos datos de: piso/planta del inmueble, numero exacto de pisos

REGLAS DE DECISION (PRIORIDAD: construir la query progresivamente):
1. PREGUNTAS FACTUALES/INFORMATIVAS: Si el usuario pregunta por datos de infraestructura (listar hospitales, colegios, parques, dotaciones, estadisticas, precios, conteos, etc.), SIEMPRE procede directo (action=proceed). Estas preguntas NO necesitan clarificacion. Ejemplos: "que hospitales hay en Suba?", "cuantos colegios hay?", "precio promedio en Chapinero", "listar parques en Usaquen".
2. CIUDAD: Si el usuario busca INMUEBLES y NO menciona ciudad, pregunta en que ciudad busca. Si menciona Bogota o una localidad de Bogota, no preguntes ciudad.
3. LOCALIDAD: Si busca INMUEBLE pero NO menciona localidad/zona ni lugar de referencia, pregunta en que zona/localidad de Bogota prefiere.
4. DESAMBIGUACION DE LUGARES: Si menciona un nombre que puede referirse a multiples lugares (ej: "hospital Santa Fe" - puede ser la localidad Santa Fe, el Hospital de la Fundacion Santa Fe en Usaquen, o el Hospital Santa Fe en Santa Fe), pregunta ESPECIFICAMENTE a cual se refiere, listando las opciones conocidas.
5. CONTEXTO IMPLICITO: Si el contexto sugiere necesidades (ej: "vivo con mi abuela" sugiere ascensor, 2+ habitaciones), SUGIERE solo amenidades que EXISTEN en la BD (ascensor, habitaciones). NUNCA sugieras "primer piso" porque no tenemos ese dato.
6. NO REPITAS: Si el historial ya aclara algo, NO lo preguntes de nuevo. Si el usuario insiste en que le des informacion, procede (action=proceed).
7. MAXIMO 1-2 preguntas por respuesta. Se conciso y directo.
8. CONSTRUYE LA QUERY: Cuando tengas suficiente info, genera enriched_query que incluya TODO el contexto acumulado del historial.
9. ANTE LA DUDA, PROCEDE: Si no estas seguro de si clarificar, procede. Es mejor dar una respuesta general que bloquear al usuario con preguntas.

HISTORIAL DE CONVERSACION:
{history}

CONSULTA ACTUAL DEL USUARIO:
{query}

Responde EXCLUSIVAMENTE con un JSON valido (sin markdown, sin ```):
{{"action": "proceed" | "clarify", "enriched_query": "consulta enriquecida con TODO el contexto del historial (solo si action=proceed)", "clarification_message": "pregunta(s) especificas de clarificacion (solo si action=clarify)", "detected_context": {{"ciudad": "detectada o null", "localidad": "detectada o null", "tipo_inmueble": "detectado o null", "amenidades": [], "necesidades_especiales": "texto o null"}}}}"""


class InmobiliarioLLMAgent:
    """
    Agente LLM para consultas inteligentes sobre datos inmobiliarios
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.llm = None
        self.sql_agent = None
        self.provider_name = None

    async def initialize(self):
        """
        Auto-detecta proveedor LLM en orden de prioridad:
          1. Ollama local (si OLLAMA_BASE_URL está configurado y responde)
          2. Gemini API (si GOOGLE_API_KEY existe)
          3. OpenAI API (si OPENAI_API_KEY existe)
          4. Solo tools predefinidas (siempre funciona)
        """
        if not LANGCHAIN_AVAILABLE:
            logger.warning("LangChain no disponible. Solo tools predefinidas.")
            return

        # 1. Ollama local — gratis, sin rate limits
        if _OLLAMA_AVAILABLE and os.getenv('OLLAMA_BASE_URL'):
            base_url, model_name = await self._detect_ollama()
            if base_url and model_name:
                llm = ChatOllama(model=model_name, base_url=base_url, temperature=0)
                if self._init_langchain(llm, f"Ollama/{model_name}"):
                    return

        # 2. Gemini API (Google)
        google_key = os.getenv('GOOGLE_API_KEY')
        if google_key and LLM_PROVIDER == "gemini":
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash", temperature=0, google_api_key=google_key
            )
            if self._init_langchain(llm, "Gemini 2.0 Flash"):
                return

        # 3. OpenAI API (fallback)
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and _ChatOpenAI:
            llm = _ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=openai_key)
            if self._init_langchain(llm, "OpenAI GPT-4o-mini"):
                return

        logger.warning("Ningun proveedor LLM activo. Solo tools predefinidas disponibles.")

    async def _detect_ollama(self) -> tuple:
        """Detecta si Ollama está corriendo y tiene un modelo Qwen disponible."""
        import httpx
        base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{base_url}/api/tags")
                models = [m['name'] for m in r.json().get('models', [])]
                qwen = next((m for m in models if 'qwen' in m.lower()), None)
                if qwen:
                    logger.info(f"Ollama detectado en {base_url} con modelo: {qwen}")
                    return (base_url, qwen)
                else:
                    available = ', '.join(models[:5]) if models else '(ninguno)'
                    logger.info(f"Ollama activo en {base_url} pero sin modelo Qwen. Modelos: {available}")
        except Exception as e:
            logger.debug(f"Ollama no disponible en {base_url}: {e}")
        return (None, None)

    def _init_langchain(self, llm, provider_name: str) -> bool:
        """
        Inicializa agente SQL de LangChain con el LLM proporcionado.
        Retorna True si la inicialización fue exitosa.
        """
        try:
            db_url = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"

            db = SQLDatabase.from_uri(
                db_url,
                schema="iug",
                view_support=True,
                include_tables=[
                    'v_estadisticas_localidad',
                    'v_top_oportunidades',
                    'v_precios_por_tipo',
                    'v_ranking_zonas',
                    'v_inmuebles_contexto',
                    'v_catalogo_caracteristicas',
                    'v_inmuebles_caracteristicas',
                    'v_caracteristicas_por_localidad',
                    'inmueble_caracteristica',
                    'dotacion_salud',
                    'dotacion_educacion',
                    'dotaciones_poi',
                ]
            )

            self.llm = llm
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=db,
                verbose=True,
                agent_executor_kwargs={'handle_parsing_errors': True}
            )
            self.provider_name = provider_name
            logger.info(f"LLM Agent inicializado con {provider_name}")
            return True

        except Exception as e:
            logger.error(f"Error inicializando LangChain con {provider_name}: {e}")
            self.llm = None
            self.sql_agent = None
            return False

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Ejecuta una tool específica con parámetros

        Args:
            tool_name: Nombre de la tool
            params: Parámetros para la tool

        Returns:
            Resultado de la tool
        """
        if tool_name not in AVAILABLE_TOOLS:
            raise ValueError(f"Tool '{tool_name}' no existe. Disponibles: {list(AVAILABLE_TOOLS.keys())}")

        # Verificar caché
        cache_key = f"{tool_name}_{str(params)}"
        cached_result = llm_cache.get(cache_key)
        if cached_result is not None:
            return {
                'tool': tool_name,
                'result': cached_result,
                'cached': True
            }

        # Ejecutar tool
        tool_info = AVAILABLE_TOOLS[tool_name]
        tool_function = tool_info['function']

        async with self.db_pool.acquire() as conn:
            try:
                result = await tool_function(conn, **params)

                # Guardar en caché
                llm_cache.set(cache_key, result)

                return {
                    'tool': tool_name,
                    'result': result,
                    'cached': False
                }

            except Exception as e:
                logger.error(f"Error ejecutando tool '{tool_name}': {e}")
                raise

    async def query_with_sql_agent(
        self,
        question: str
    ) -> Dict[str, Any]:
        """
        Procesa pregunta usando LangChain SQL Agent

        Args:
            question: Pregunta en lenguaje natural

        Returns:
            Respuesta del agente con texto y propiedades opcionales
        """
        if not self.sql_agent:
            return {
                'error': 'SQL Agent no disponible. Requiere GOOGLE_API_KEY (o OPENAI_API_KEY) y LangChain.',
                'suggestion': 'Usar tools predefinidas en su lugar.'
            }

        # Verificar caché para respuesta de texto
        cached_answer = llm_cache.get(question)

        if cached_answer is not None:
            answer = cached_answer
            cached = True
        else:
            contexto = (
                "CONTEXTO: Los nombres de localidad están en MAYÚSCULAS (SUBA, CHAPINERO, USAQUEN, KENNEDY, etc). "
                "Usa UPPER() o ILIKE para comparar localidades. "
                "v_inmuebles_caracteristicas tiene columnas booleanas de amenidades: "
                "tiene_piscina, tiene_gimnasio, tiene_parqueadero, tiene_vigilancia, "
                "tiene_ascensor, tiene_salon_comunal, tiene_bbq, tiene_cancha, tiene_jacuzzi, tiene_deposito. "
                "v_catalogo_caracteristicas lista todas las amenidades con frecuencia. "
                "v_caracteristicas_por_localidad tiene distribución de amenidades por localidad. "
                "Responde en español.\n\n"
            )
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = self.sql_agent.invoke({'input': contexto + question})
                    if isinstance(response, dict):
                        answer = response.get('output', str(response))
                    else:
                        answer = str(response)
                    answer = self._postprocess_answer(answer, question)
                    llm_cache.set(question, answer)
                    cached = False
                    break
                except Exception as e:
                    retryable = 'Response' in str(e) or 'parsing' in str(e).lower()
                    if attempt < max_retries and retryable:
                        logger.warning(f"SQL Agent intento {attempt+1} falló, reintentando: {e}")
                        time.sleep(1.5)
                        continue
                    logger.error(f"Error en SQL Agent: {e}")
                    return {
                        'error': str(e),
                        'question': question
                    }

        # Buscar propiedades para mostrar como cards
        properties = await self._search_properties_for_cards(question)

        result = {
            'question': question,
            'answer': answer,
            'cached': cached
        }
        if properties:
            result['properties'] = properties

        return result

    def _looks_like_raw_sql(self, text: str) -> bool:
        """Detecta si la respuesta parece output SQL crudo en vez de lenguaje natural."""
        if not isinstance(text, str):
            return True
        for pattern in RAW_SQL_PATTERNS:
            if re.search(pattern, text):
                return True
        if text.count(',') > 5 and 'None' in text and text.strip().startswith('('):
            return True
        return False

    def _postprocess_answer(self, raw_answer: str, original_question: str) -> str:
        """Si la respuesta parece SQL crudo, usa el LLM para reformatearla."""
        if not self._looks_like_raw_sql(raw_answer):
            return raw_answer
        if not self.llm:
            return raw_answer

        reformat_prompt = (
            "El siguiente texto es el resultado crudo de una consulta SQL que se debe presentar "
            "al usuario como respuesta conversacional en español.\n\n"
            f"Pregunta original del usuario: {original_question}\n\n"
            f"Resultado crudo:\n{raw_answer}\n\n"
            "Reescribe este resultado como una respuesta conversacional en español. "
            "Si hay datos tabulares, preséntalos de forma legible. "
            "Si hay valores None, omítelos o indica que no hay dato. "
            "Formatea los precios en pesos colombianos (ej: $250.000.000). "
            "No incluyas SQL, código ni formato técnico. Se conciso."
        )
        try:
            response = self.llm.invoke(reformat_prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.warning(f"Error reformateando respuesta: {e}")
            return raw_answer

    async def _search_properties_for_cards(
        self,
        question: str
    ) -> List[Dict[str, Any]]:
        """
        Busca propiedades relevantes a la pregunta para mostrar como cards.
        Extrae keywords de localidad y tipo de inmueble de la pregunta.
        """
        question_lower = question.lower()

        # Palabras que indican preguntas sobre POIs/infraestructura, NO propiedades
        poi_keywords = [
            'hospital', 'hospitales', 'clinica', 'clinicas', 'clínica', 'clínicas',
            'colegio', 'colegios', 'escuela', 'escuelas', 'universidad', 'universidades',
            'parque', 'parques', 'iglesia', 'iglesias', 'estacion', 'estaciones',
            'estación', 'centro comercial', 'centros comerciales', 'supermercado',
            'banco', 'bancos', 'farmacia', 'farmacias', 'museo', 'museos',
            'biblioteca', 'bibliotecas', 'cai', 'policia', 'policía',
            'transmilenio', 'sitp', 'metro', 'bomberos',
        ]
        is_poi_query = any(kw in question_lower for kw in poi_keywords)

        # Extraer tipo de inmueble
        tipos_map = {
            'apartamento': 'Apartamento', 'apartamentos': 'Apartamento',
            'casa': 'Casa', 'casas': 'Casa',
            'lote': 'Lote', 'lotes': 'Lote',
            'local': 'Local', 'locales': 'Local',
            'oficina': 'Oficina', 'oficinas': 'Oficina',
        }
        tipo = None
        for keyword, value in tipos_map.items():
            if re.search(r'\b' + keyword + r'\b', question_lower):
                tipo = value
                break

        # Solo mostrar cards de propiedades si:
        # 1. Se menciona un tipo de inmueble explícito, O
        # 2. Hay intención de búsqueda de propiedades Y NO es una pregunta sobre POIs
        search_intent_keywords = [
            'busco', 'buscar', 'encontrar', 'muéstrame', 'mostrar',
            'oportunidad', 'oportunidades', 'inversión', 'comprar',
            'barato', 'económico', 'propiedad', 'propiedades', 'inmueble', 'inmuebles',
        ]
        has_search_intent = any(kw in question_lower for kw in search_intent_keywords)

        if is_poi_query and not tipo:
            return []
        if not tipo and not has_search_intent:
            return []

        # Extraer localidad
        localidad = None
        for loc in LOCALIDADES:
            if loc.lower() in question_lower:
                localidad = loc
                break

        # Construir query parametrizada
        conditions = []
        params = []
        param_count = 0

        if tipo:
            param_count += 1
            conditions.append(f"tipo_inmueble = ${param_count}")
            params.append(tipo)

        if localidad:
            param_count += 1
            conditions.append(f"UPPER(nombre_localidad) = ${param_count}")
            params.append(localidad)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT id_inmueble, tipo_inmueble, precio, ubicacion, area,
                   habitaciones, banos, image, descripcion, iurb,
                   nombre_localidad, latitud, longitud
            FROM iug.v_inmuebles_contexto
            WHERE {where_clause}
              AND image IS NOT NULL
              AND image != ''
            ORDER BY iurb DESC NULLS LAST
            LIMIT 10
        """

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                properties = []
                for r in rows:
                    prop = dict(r)
                    for key in ['precio', 'area', 'iurb', 'latitud', 'longitud']:
                        if key in prop and prop[key] is not None:
                            prop[key] = float(prop[key])
                    properties.append(prop)
                return properties
        except Exception as e:
            logger.error(f"Error buscando propiedades para cards: {e}")
            return []

    async def analyze_query_for_clarification(
        self,
        question: str,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Pre-procesa la query del usuario para detectar si necesita clarificacion.
        Usa Gemini para analizar la pregunta y decidir si proceder o preguntar.
        """
        if not self.llm:
            return {"action": "proceed", "enriched_query": question}

        # Formatear historial (ultimos 6 mensajes)
        recent = conversation_history[-6:] if conversation_history else []
        history_str = ""
        for msg in recent:
            role = "Usuario" if msg["role"] == "user" else "Asistente"
            history_str += f"{role}: {msg['content']}\n"
        if not history_str:
            history_str = "(Sin historial previo)"

        prompt = CLARIFICATION_PROMPT.format(
            localidades=", ".join(LOCALIDADES),
            history=history_str,
            query=question
        )

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            content = content.strip()

            # Limpiar markdown fences si Gemini las agrega
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                content = content.rsplit("```", 1)[0]
                content = content.strip()

            result = json_module.loads(content)

            if result.get("action") not in ("proceed", "clarify"):
                result["action"] = "proceed"
                result["enriched_query"] = question

            return result

        except (json_module.JSONDecodeError, Exception) as e:
            logger.warning(f"Error analizando query para clarificacion: {e}")
            return {"action": "proceed", "enriched_query": question}

    async def chat(
        self,
        message: str,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Flujo conversacional completo:
        1. Pre-procesa: verifica si se necesita clarificacion
        2. Si clarify: retorna pregunta de clarificacion
        3. Si proceed: ejecuta SQL agent + post-procesa + busca propiedades
        """
        # Paso 1: Analizar si necesita clarificacion
        analysis = await self.analyze_query_for_clarification(message, conversation_history)

        if analysis["action"] == "clarify":
            return {
                "type": "clarification",
                "message": analysis.get("clarification_message", "¿Podrías darme más detalles?"),
                "detected_context": analysis.get("detected_context", {}),
            }

        # Paso 2: Ejecutar SQL agent con query enriquecida
        enriched_query = analysis.get("enriched_query", message)
        result = await self.query_with_sql_agent(enriched_query)

        if "error" in result:
            return {
                "type": "error",
                "message": result["error"],
            }

        # Paso 3: Construir respuesta
        response = {
            "type": "answer",
            "message": result["answer"],
            "cached": result.get("cached", False),
        }

        if result.get("properties"):
            response["properties"] = result["properties"]

        return response

    async def analyze_property(
        self,
        id_inmueble: int
    ) -> Dict[str, Any]:
        """
        Genera análisis completo de un inmueble específico

        Args:
            id_inmueble: ID del inmueble

        Returns:
            Análisis completo con contexto, comparables, recomendaciones
        """
        # Usar tools para obtener datos
        contexto = await self.execute_tool('get_inmuebles_contexto', {'id_inmueble': id_inmueble, 'limite': 1})

        if not contexto['result']:
            return {'error': f'Inmueble {id_inmueble} no encontrado'}

        inmueble = contexto['result'][0]

        # Buscar similares para comparación
        similares = await self.execute_tool('buscar_inmuebles_similares', {
            'precio_referencia': float(inmueble['precio']),
            'area_referencia': float(inmueble['area']),
            'tipo_inmueble': inmueble['tipo_inmueble'],
            'limite': 5
        })

        # Estadísticas de la localidad
        stats_localidad = await self.execute_tool('get_estadisticas_localidad', {
            'nombre_localidad': inmueble['nombre_localidad']
        })

        # Generar análisis
        analisis = {
            'inmueble': inmueble,
            'similares': similares['result'],
            'estadisticas_localidad': stats_localidad['result'][0] if stats_localidad['result'] else None,
            'evaluacion': self._evaluar_inmueble(inmueble, similares['result'])
        }

        return analisis

    def _evaluar_inmueble(
        self,
        inmueble: Dict,
        similares: List[Dict]
    ) -> Dict[str, Any]:
        """
        Evalúa un inmueble comparado con similares

        Returns:
            Dict con evaluación y recomendaciones
        """
        if not similares:
            return {'mensaje': 'No hay inmuebles similares para comparar'}

        # Calcular promedios de similares
        precio_promedio_similares = sum(s['precio'] for s in similares) / len(similares)
        iurb_promedio_similares = sum(s['iurb'] for s in similares) / len(similares)

        # Comparar
        diferencia_precio_pct = ((inmueble['precio'] - precio_promedio_similares) / precio_promedio_similares) * 100
        diferencia_iurb = inmueble['iurb'] - iurb_promedio_similares

        # Categorizar oportunidad
        if diferencia_precio_pct < -10 and diferencia_iurb > 0:
            categoria = "Excelente Oportunidad"
            mensaje = f"Precio {abs(diferencia_precio_pct):.1f}% menor que similares con mejor I_URB"
        elif diferencia_precio_pct < 0 and diferencia_iurb >= 0:
            categoria = "Buena Oportunidad"
            mensaje = f"Precio {abs(diferencia_precio_pct):.1f}% menor que similares con I_URB comparable"
        elif diferencia_precio_pct > 10 and diferencia_iurb < 0:
            categoria = "Sobrevalorado"
            mensaje = f"Precio {diferencia_precio_pct:.1f}% mayor que similares con peor I_URB"
        else:
            categoria = "Precio de Mercado"
            mensaje = "Precio y calidad alineados con el mercado"

        return {
            'categoria': categoria,
            'mensaje': mensaje,
            'precio_promedio_similares': round(precio_promedio_similares),
            'diferencia_precio_pct': round(diferencia_precio_pct, 2),
            'iurb_promedio_similares': round(iurb_promedio_similares, 2),
            'diferencia_iurb': round(diferencia_iurb, 2),
            'total_similares': len(similares)
        }

    def get_available_tools(self) -> Dict[str, Dict]:
        """
        Retorna lista de tools disponibles con sus descripciones
        """
        return {
            name: {
                'description': info['description'],
                'parameters': info['parameters']
            }
            for name, info in AVAILABLE_TOOLS.items()
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del caché
        """
        return llm_cache.get_stats()

    def clear_cache(self):
        """
        Limpia el caché
        """
        llm_cache.clear()
