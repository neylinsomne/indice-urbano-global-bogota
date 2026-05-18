"""
Router para consultas LLM inteligentes
Expone tools y agente SQL sin registrar resultados (solo caché)
"""
import asyncio
import hashlib
import json

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import asyncpg
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from db.postgre import get_db_pool
from db.redis_cache import cache_get, cache_set
from llm.agent import InmobiliarioLLMAgent
from services.auth_service import get_current_user, require_admin
from rag.intent_parser import parse as parse_intent
from rag.geocoding import geocode_address
from rag.spatial_search import search as run_spatial_search
from rag.conversation_memory import (
    append_turn, load_memory, merge_context_into_query,
)
from rag.assistant_router import (
    detect_handler, smalltalk_reply, quick_explain,
)

logger = logging.getLogger(__name__)

# Limitar concurrencia de llamadas LLM para evitar saturar API externas
_llm_semaphore = asyncio.Semaphore(3)

# Rate limiter aplicado por IP. Las llamadas LLM cuestan tokens externos
# y son un vector caro de DoS, así que limitamos agresivamente.
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/llm",
    tags=["llm"],
    responses={404: {"description": "Not found"}}
)

# Instancia global del agente (se inicializa en startup)
llm_agent: Optional[InmobiliarioLLMAgent] = None


# ============================================
# Modelos Pydantic
# ============================================

class ToolExecutionRequest(BaseModel):
    """Request para ejecutar una tool específica"""
    tool_name: str = Field(..., description="Nombre de la tool a ejecutar")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parámetros para la tool")

    class Config:
        json_schema_extra = {
            "example": {
                "tool_name": "get_top_oportunidades",
                "params": {
                    "limite": 5,
                    "tipo_inmueble": "Apartamento",
                    "iurb_min": 3.5
                }
            }
        }


class NaturalQueryRequest(BaseModel):
    """Request para pregunta en lenguaje natural"""
    question: str = Field(..., description="Pregunta en lenguaje natural")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "¿Cuáles son las mejores zonas de Bogotá según el indicador de accesibilidad?"
            }
        }


class SearchNaturalRequest(BaseModel):
    """
    Búsqueda inmobiliaria multi-dimensional en lenguaje natural.
    Soporta combinaciones de proximidad (centros médicos, parques, TM,
    colegios, etc.), filtros de inmueble (precio, área, hab, tipo),
    umbrales de IUG, dirección física y amenidades.
    """
    query: str = Field(..., min_length=2, max_length=500,
                       description="Pregunta o requerimiento en lenguaje natural")
    limit: int = Field(20, ge=1, le=50, description="Máximo de resultados")
    use_llm: bool = Field(True, description="Si True, complementa rule-based con Gemini")
    session_id: Optional[str] = Field(
        None, max_length=80,
        description="ID de sesión para memoria conversacional persistente"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Apto en Chapinero cerca a hospital y parque, menos de 600M, mínimo 80m2",
                "limit": 15,
                "use_llm": True,
                "session_id": "user-42-2026-05-13",
            }
        }


class ChatMessage(BaseModel):
    """Mensaje individual en historial de conversacion"""
    role: str = Field(..., description="'user' o 'assistant'")
    content: str = Field(..., description="Contenido del mensaje")


class ChatRequest(BaseModel):
    """Request para chat conversacional"""
    message: str = Field(..., description="Mensaje actual del usuario")
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        description="Mensajes previos de la conversacion"
    )


class PropertyAnalysisRequest(BaseModel):
    """Request para análisis completo de inmueble"""
    id_inmueble: int = Field(..., description="ID del inmueble a analizar")


# ============================================
# Lifecycle
# ============================================

@router.on_event("startup")
async def startup_llm():
    """Inicializa agente LLM al arrancar (auto-detecta proveedor)"""
    global llm_agent
    db_pool = await get_db_pool()
    llm_agent = InmobiliarioLLMAgent(db_pool)
    await llm_agent.initialize()
    logger.info(f"✓ LLM Agent listo (proveedor: {llm_agent.provider_name or 'solo tools'})")


# ============================================
# Endpoints
# ============================================

@router.get("/tools")
async def listar_tools(user: dict = Depends(get_current_user)):
    """
    Lista todas las tools disponibles con sus descripciones.
    Requiere autenticación.
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    return {
        "tools": llm_agent.get_available_tools(),
        "total": len(llm_agent.get_available_tools())
    }


@router.post("/tool/execute")
async def ejecutar_tool(request: ToolExecutionRequest, user: dict = Depends(get_current_user)):
    """
    Ejecuta una tool específica con parámetros

    **Usa caché:** Resultados se cachean por 30 minutos

    **Tools disponibles:**
    - `get_estadisticas_localidad`: Estadísticas por localidad
    - `get_top_oportunidades`: Mejores oportunidades (precio/I_URB)
    - `get_precios_por_tipo`: Precios por tipo de inmueble
    - `get_ranking_zonas`: Ranking de zonas por indicador
    - `get_inmuebles_contexto`: Inmuebles con contexto completo
    - `get_dotaciones_por_zona`: Dotaciones por zona geográfica
    - `buscar_inmuebles_similares`: Inmuebles similares (para comparables)
    - `get_estadisticas_generales`: Estadísticas globales del sistema

    **Ejemplo:**
    ```json
    {
        "tool_name": "get_top_oportunidades",
        "params": {
            "limite": 10,
            "tipo_inmueble": "Apartamento",
            "iurb_min": 3.5
        }
    }
    ```
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    try:
        result = await llm_agent.execute_tool(request.tool_name, request.params)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Error ejecutando tool: {e}")
        raise HTTPException(status_code=500, detail=f"Error ejecutando tool: {str(e)}")


@router.post("/query")
@limiter.limit("10/minute")
async def consulta_natural(
    request: Request,
    body: NaturalQueryRequest,
    user: dict = Depends(get_current_user),
):
    """
    Procesa pregunta en lenguaje natural usando SQL Agent

    **Requiere:** Variable de entorno `OPENAI_API_KEY`

    **Usa caché:** Preguntas idénticas se responden desde caché

    El agente SQL puede:
    - Consultar vistas optimizadas (v_estadisticas_localidad, v_top_oportunidades, etc.)
    - Generar queries SQL dinámicamente
    - Razonar sobre los datos para responder preguntas complejas

    **Ejemplos de preguntas:**
    - "¿Cuál es el precio promedio de apartamentos en Chapinero?"
    - "Muéstrame las 5 mejores oportunidades en Usaquén"
    - "¿Qué localidad tiene mejor indicador de seguridad?"
    - "Compara los precios de casas vs apartamentos"

    **Nota:** Si no está configurado OPENAI_API_KEY, usar `/tool/execute` con tools predefinidas
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    try:
        async with _llm_semaphore:
            result = await llm_agent.query_with_sql_agent(body.question)

        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en consulta natural: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando pregunta: {str(e)}")


@router.post("/search-natural")
@limiter.limit("12/minute")
async def busqueda_multi_dimensional(
    request: Request,
    body: SearchNaturalRequest,
    user: dict = Depends(get_current_user),
):
    """
    Búsqueda inmobiliaria multi-dimensional en lenguaje natural.

    Pipeline:
      1. **Intent parser** (rule-based + Gemini Flash opcional) extrae:
         categorías POI, distancias, filtros del inmueble, umbrales IUG,
         dirección física, amenidades.
      2. **Geocoding** (Nominatim + Redis) resuelve dirección a (lat,lon)
         si la query menciona "Cra 7 #80-23" o similar.
      3. **Spatial search**: SQL con LATERAL JOINs a tablas POI, scoring
         híbrido (IUG + proximidad + dirección).
      4. **Relaxation automática**: si los HARD requirements dan 0
         resultados, re-corre marcando todo SOFT y reporta el ajuste.
      5. **Explicación** humana por cada resultado.

    Cache Redis por 1h sobre la firma (query, limit, use_llm).

    Ejemplos:
      - "Apto en Chapinero cerca a hospital y parque, menos de 600M"
      - "Casa cerca a colegio y supermercado, IUG > 3.5"
      - "Inmueble a 500m de la Carrera 7 # 80-23, 3 habitaciones"
      - "Apartamento muy seguro con buena dotación, mínimo 80m2"
    """
    raw_query = body.query.strip()

    # ── 0. Memoria conversacional (si viene session_id)
    memory = await load_memory(body.session_id) if body.session_id else None
    prev_intent = memory.last_intent if memory else None
    enriched_query = (
        merge_context_into_query(raw_query, prev_intent)
        if prev_intent else raw_query
    )

    # ── 1. Router: ¿qué ayudante atiende?
    handler = detect_handler(raw_query)

    # ── 1a. Smalltalk: respuesta inmediata, sin DB ni LLM
    if handler == "smalltalk":
        reply = smalltalk_reply(raw_query)
        if memory is not None:
            await append_turn(body.session_id, "user", raw_query)
            await append_turn(body.session_id, "assistant", reply)
        return {
            "kind": "smalltalk",
            "content": reply,
            "results": [], "count": 0,
            "suggestions": [], "intent": None,
            "cached": False, "handler": "smalltalk",
        }

    # ── 1b. Explain: si la pregunta tiene respuesta pre-canónica, la
    # devolvemos sin LLM (latencia ~5ms). Si no, dejamos que llegue al
    # SQL Agent vía el endpoint /llm/chat por el frontend.
    if handler == "explain":
        canned = quick_explain(raw_query)
        if canned:
            if memory is not None:
                await append_turn(body.session_id, "user", raw_query)
                await append_turn(body.session_id, "assistant", canned[:300])
            return {
                "kind": "explain",
                "content": canned,
                "results": [], "count": 0,
                "suggestions": [
                    {"letter": "A", "label": "Buscar inmuebles con esta dimensión",
                     "prompt": "apartamento con buen IUG en Bogotá",
                     "reason": "Aplica el indicador en una búsqueda concreta."},
                ],
                "intent": None,
                "cached": True,
                "handler": "explain",
            }
        # Para explain sin canned, devolvemos un placeholder que el frontend
        # redirige a /llm/chat (donde está el SQL Agent + Gemini).
        return {
            "kind": "explain_fallback",
            "content": "",  # frontend lo ignora y llama a /llm/chat
            "results": [], "count": 0,
            "suggestions": [], "intent": None,
            "cached": False,
            "handler": "explain_fallback",
        }

    # ── 2. Search / compare / acm: caching + intent parser
    cache_key = "rag:search:" + hashlib.sha1(
        json.dumps({"q": enriched_query.lower().strip(),
                    "l": body.limit, "u": body.use_llm}, sort_keys=True).encode()
    ).hexdigest()

    cached = await cache_get(cache_key)
    if cached and not memory:
        # Si NO hay sesión, devolvemos cache directo.
        # Con memoria queremos guardar el turn igualmente.
        cached["cached"] = True
        return cached

    # 2a. Intent (sobre la query enriquecida si aplica)
    intent = await parse_intent(enriched_query, use_llm=body.use_llm)

    # 2b. Geocoding
    if intent.address_anchor and intent.address_anchor.lat is None:
        coords = await geocode_address(intent.address_anchor.raw)
        if coords:
            intent.address_anchor.lat = coords[0]
            intent.address_anchor.lon = coords[1]
        else:
            intent.notes.append("address_no_geocode")
            intent.address_anchor = None

    # 2c. Búsqueda espacial
    pool = await get_db_pool()
    result = await run_spatial_search(pool, intent, limit=body.limit)
    result["handler"] = handler
    result["kind"] = handler  # frontend usa kind como discriminator
    result["content"] = ""    # para uniformidad con explain/smalltalk
    if enriched_query != raw_query:
        result["context_used"] = True
        result["enriched_query"] = enriched_query

    # 2d. Cache + memoria
    if not result.get("error"):
        await cache_set(cache_key, result, ttl=3600)
    if memory is not None:
        result_ids = [r.get("id_inmueble") for r in result.get("results", []) if r.get("id_inmueble")]
        await append_turn(
            body.session_id, "user", raw_query,
            intent_snapshot=intent.to_dict(),
            result_ids=result_ids,
        )
        # Resumen corto para el trail del assistant
        summary = (
            f"Devolví {result['count']} inmuebles"
            + (" tras relajar criterios" if result.get("relaxed") else "")
            + "."
        )
        await append_turn(body.session_id, "assistant", summary)
    result["cached"] = False
    return result


@router.post("/chat")
@limiter.limit("15/minute")
async def chat_conversacional(
    request: Request,
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Endpoint conversacional con soporte de historial.

    A diferencia de /query (single-shot), este endpoint:
    - Analiza el contexto de la conversacion previa
    - Detecta si necesita pedir clarificacion al usuario
    - Enriquece la consulta con contexto del historial
    - Post-procesa respuestas SQL crudas a lenguaje natural

    Tipos de respuesta (campo `type`):
    - `answer`: Respuesta completa con posibles property cards
    - `clarification`: Pregunta de clarificacion (no se ejecuto SQL)
    - `error`: Error en el procesamiento
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    try:
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in body.conversation_history
        ]

        async with _llm_semaphore:
            result = await llm_agent.chat(body.message, history)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en chat conversacional: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando mensaje: {str(e)}"
        )


@router.post("/analyze/property")
async def analizar_inmueble(request: PropertyAnalysisRequest, user: dict = Depends(get_current_user)):
    """
    Genera análisis completo de un inmueble específico

    **Incluye:**
    - Contexto completo del inmueble (dotaciones, transporte, seguridad)
    - Inmuebles similares para comparación (mismo tipo, precio, área)
    - Estadísticas de la localidad
    - Evaluación automática (Excelente Oportunidad, Buena, Sobrevalorado, etc.)
    - Diferencia de precio vs mercado (%)
    - Diferencia de I_URB vs similares

    **Usa caché:** Análisis se cachean por 30 minutos

    **Ejemplo:**
    ```json
    {
        "id_inmueble": 12345
    }
    ```

    **Respuesta incluye:**
    - `inmueble`: Datos completos del inmueble con contexto
    - `similares`: Lista de 5 inmuebles comparables
    - `estadisticas_localidad`: Promedios de la localidad
    - `evaluacion`: Análisis automático con recomendaciones
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    try:
        result = await llm_agent.analyze_property(request.id_inmueble)

        if 'error' in result:
            raise HTTPException(status_code=404, detail=result['error'])

        return result

    except Exception as e:
        logger.error(f"Error analizando inmueble: {e}")
        raise HTTPException(status_code=500, detail=f"Error en análisis: {str(e)}")


@router.get("/cache/stats")
async def obtener_estadisticas_cache(admin: dict = Depends(require_admin)):
    """
    Obtiene estadísticas del caché LLM

    **Retorna:**
    - `size`: Número de entries en caché
    - `max_size`: Tamaño máximo del caché
    - `hit_count`: Número de hits (consultas respondidas desde caché)
    - `miss_count`: Número de misses (consultas a DB)
    - `hit_rate`: Tasa de aciertos (%)
    - `ttl_minutes`: Tiempo de vida de entries (minutos)

    **Útil para:**
    - Monitorear eficiencia del caché
    - Ajustar tamaño de caché según uso
    - Identificar consultas más frecuentes
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    return llm_agent.get_cache_stats()


@router.post("/cache/clear")
async def limpiar_cache(admin: dict = Depends(require_admin)):
    """
    Limpia completamente el caché LLM

    **Uso:**
    - Después de actualizar datos en la BD
    - Para forzar re-cálculo de estadísticas
    - Debugging/testing

    **Nota:** El caché se reconstruirá automáticamente con las siguientes consultas
    """
    if not llm_agent:
        raise HTTPException(status_code=503, detail="LLM Agent no inicializado")

    llm_agent.clear_cache()

    return {
        "message": "Caché limpiado exitosamente",
        "cache_stats": llm_agent.get_cache_stats()
    }


@router.get("/examples")
async def obtener_ejemplos(user: dict = Depends(get_current_user)):
    """
    Retorna ejemplos de uso para cada tipo de endpoint

    **Útil para:**
    - Aprender a usar la API
    - Testing inicial
    - Generar documentación
    """
    return {
        "tools": [
            {
                "descripcion": "Obtener estadísticas de Chapinero",
                "endpoint": "/api/llm/tool/execute",
                "body": {
                    "tool_name": "get_estadisticas_localidad",
                    "params": {"nombre_localidad": "Chapinero"}
                }
            },
            {
                "descripcion": "Top 5 oportunidades en apartamentos",
                "endpoint": "/api/llm/tool/execute",
                "body": {
                    "tool_name": "get_top_oportunidades",
                    "params": {
                        "limite": 5,
                        "tipo_inmueble": "Apartamento",
                        "iurb_min": 3.5
                    }
                }
            },
            {
                "descripcion": "Ranking de zonas por accesibilidad",
                "endpoint": "/api/llm/tool/execute",
                "body": {
                    "tool_name": "get_ranking_zonas",
                    "params": {"ordenar_por": "iacc"}
                }
            }
        ],
        "natural_queries": [
            {
                "descripcion": "Pregunta sobre precios",
                "endpoint": "/api/llm/query",
                "body": {
                    "question": "¿Cuál es el precio promedio de apartamentos en Usaquén?"
                }
            },
            {
                "descripcion": "Comparación de zonas",
                "endpoint": "/api/llm/query",
                "body": {
                    "question": "¿Qué localidad tiene mejor indicador de seguridad y cuánto cuesta vivir ahí?"
                }
            }
        ],
        "property_analysis": [
            {
                "descripcion": "Análisis completo de inmueble",
                "endpoint": "/api/llm/analyze/property",
                "body": {
                    "id_inmueble": 12345
                }
            }
        ]
    }
