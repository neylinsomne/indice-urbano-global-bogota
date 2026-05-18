"""
Router de Búsqueda Avanzada

Combina:
1. RAG para búsquedas semánticas en dotaciones
2. AHP personalizado para pesos según preferencias del usuario
3. Queries inteligentes en lenguaje natural

Endpoints:
- POST /api/busqueda/natural: Búsqueda en lenguaje natural
- POST /api/busqueda/embeddings/generar: Generar embeddings
- GET /api/busqueda/dotaciones/similar: Búsqueda por similitud
- GET /api/ahp/cuestionario/{tipo}: Obtener cuestionario AHP
- POST /api/ahp/calcular-pesos: Calcular pesos desde respuestas
- POST /api/ahp/idot-personalizado: Calcular IDOT con pesos personalizados
- GET /api/ahp/comparar-perfiles: Comparar diferentes perfiles AHP
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import asyncpg
import logging

from db.postgre import get_db_pool
from rag.embeddings import get_embeddings_manager, search_similar_dotaciones
from rag.query_processor import process_natural_query, QUERY_EXAMPLES
from ahp.questionnaire import (
    get_cuestionario_dotaciones,
    get_cuestionario_transporte,
    get_cuestionario_indicadores,
    procesar_respuestas,
    RespuestasUsuario,
    CRITERIOS_DOTACIONES,
    CRITERIOS_TRANSPORTE,
    CRITERIOS_INDICADORES_PRINCIPALES
)
from ahp.dotaciones_ahp import (
    calcular_pesos_dotaciones,
    aplicar_pesos_personalizados,
    comparar_perfiles_ahp
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/busqueda", tags=["busqueda-avanzada"])


# ============================================
# Modelos Pydantic
# ============================================

class BusquedaNaturalInput(BaseModel):
    """Input para búsqueda en lenguaje natural"""
    query: str = Field(
        ...,
        description="Query en lenguaje natural",
        example="cerca a colegios y hospitales"
    )
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)
    radio_max: int = Field(2000, ge=100, le=10000, description="Radio máximo en metros")


class BusquedaNaturalResponse(BaseModel):
    """Respuesta de búsqueda natural"""
    query_original: str
    query_procesada: Dict
    resultados: List[Dict]
    total_encontrados: int


class IDOTPersonalizadoInput(BaseModel):
    """Input para cálculo de IDOT personalizado"""
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    pesos: Dict[str, float] = Field(
        ...,
        description="Pesos AHP (salud, educacion, comercio, cultura, recreacion)",
        example={
            "salud": 0.35,
            "educacion": 0.30,
            "comercio": 0.15,
            "cultura": 0.10,
            "recreacion": 0.10
        }
    )
    radios: Optional[Dict[str, int]] = Field(
        None,
        description="Radios personalizados por categoría (metros)"
    )


# ============================================
# Endpoints RAG
# ============================================

@router.post("/natural", response_model=BusquedaNaturalResponse)
async def busqueda_natural(
    input_data: BusquedaNaturalInput,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Búsqueda inteligente en lenguaje natural

    Procesa queries como:
    - "cerca a colegios y hospitales"
    - "zonas con universidades y parques a 500 metros"
    - "sectores cerca de centros comerciales"

    Si se proporcionan coordenadas, busca dotaciones cercanas.
    Si no, hace búsqueda semántica usando embeddings.
    """
    # Procesar query
    query_info = process_natural_query(input_data.query)

    if not query_info['categorias']:
        raise HTTPException(
            400,
            f"No se pudieron identificar categorías en la query. Ejemplos: {QUERY_EXAMPLES[:3]}"
        )

    async with db.acquire() as conn:
        # Si hay coordenadas, búsqueda geoespacial
        if input_data.latitud and input_data.longitud:
            manager = get_embeddings_manager()
            resultados_dict = await manager.search_nearby_with_categories(
                lat=input_data.latitud,
                lon=input_data.longitud,
                categorias=query_info['categorias'],
                radius_m=min(query_info['radio_metros'], input_data.radio_max),
                conn=conn
            )

            # Aplanar resultados
            resultados = []
            for cat, dots in resultados_dict.items():
                for dot in dots:
                    dot['categoria_buscada'] = cat
                    resultados.append(dot)

        else:
            # Búsqueda semántica sin coordenadas
            resultados = await search_similar_dotaciones(
                query=input_data.query,
                conn=conn,
                top_k=50
            )

    return BusquedaNaturalResponse(
        query_original=input_data.query,
        query_procesada=query_info,
        resultados=resultados,
        total_encontrados=len(resultados)
    )


@router.post("/embeddings/generar")
async def generar_embeddings(
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Genera embeddings para todas las dotaciones (operación pesada)

    Se ejecuta en background. Necesario ejecutar una vez antes de usar
    búsquedas semánticas.

    Requiere: pip install sentence-transformers
    """
    async def generar():
        try:
            async with db.acquire() as conn:
                manager = get_embeddings_manager()
                embeddings = await manager.generate_embeddings_from_db(conn)
                logger.info(f"Embeddings generados: {len(embeddings)} dotaciones")
        except Exception as e:
            logger.error(f"Error generando embeddings: {e}", exc_info=True)

    background_tasks.add_task(generar)

    return {
        "status": "processing",
        "message": "Generación de embeddings iniciada en background"
    }


@router.get("/dotaciones/similar")
async def buscar_dotaciones_similares(
    query: str = Query(..., description="Texto de búsqueda", example="hospitales y clínicas"),
    limit: int = Query(20, ge=1, le=100),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Busca dotaciones similares usando embeddings semánticos

    Requiere haber ejecutado /embeddings/generar primero.
    """
    async with db.acquire() as conn:
        resultados = await search_similar_dotaciones(query, conn, top_k=limit)

    return {
        "query": query,
        "resultados": resultados,
        "total": len(resultados)
    }


@router.get("/ejemplos")
async def obtener_ejemplos_queries():
    """
    Devuelve ejemplos de queries soportadas para ayudar al usuario
    """
    return {
        "ejemplos_queries_naturales": QUERY_EXAMPLES,
        "categorias_soportadas": list(process_natural_query.CATEGORIA_KEYWORDS.keys()),
        "palabras_distancia": list(process_natural_query.DISTANCIA_KEYWORDS.keys())
    }


# ============================================
# Endpoints AHP
# ============================================

@router.get("/ahp/cuestionario/{tipo}")
async def obtener_cuestionario_ahp(
    tipo: str = Path(
        ...,
        description="Tipo de cuestionario: dotaciones, transporte, indicadores"
    )
):
    """
    Obtiene cuestionario AHP según tipo

    Tipos disponibles:
    - dotaciones: Para personalizar pesos de IDOT (salud, educación, etc.)
    - transporte: Para personalizar pesos de I_ACC (TransMilenio, SITP, vías)
    - indicadores: Para personalizar pesos de I_URB (I_ACC, I_SEG, I_HED, I_PNU)

    Retorna lista de preguntas de comparación pareada en escala Saaty (1-9).
    """
    if tipo == "dotaciones":
        preguntas = get_cuestionario_dotaciones()
        criterios = CRITERIOS_DOTACIONES
    elif tipo == "transporte":
        preguntas = get_cuestionario_transporte()
        criterios = CRITERIOS_TRANSPORTE
    elif tipo == "indicadores":
        preguntas = get_cuestionario_indicadores()
        criterios = CRITERIOS_INDICADORES_PRINCIPALES
    else:
        raise HTTPException(400, "Tipo de cuestionario inválido")

    return {
        "tipo": tipo,
        "total_preguntas": len(preguntas),
        "criterios": [c.dict() for c in criterios],
        "preguntas": [p.dict() for p in preguntas],
        "instrucciones": (
            "Para cada pregunta, selecciona qué criterio es más importante y cuánto. "
            "Usa la escala de 1 (igual importancia) a 9 (extremadamente más importante)."
        ),
        "escala_saaty": {
            "1": "Igual importancia",
            "3": "Moderadamente más importante",
            "5": "Fuertemente más importante",
            "7": "Muy fuertemente más importante",
            "9": "Extremadamente más importante"
        }
    }


@router.post("/ahp/calcular-pesos")
async def calcular_pesos_desde_respuestas(
    tipo: str = Query(..., regex="^(dotaciones|transporte|indicadores)$"),
    respuestas: RespuestasUsuario = ...
):
    """
    Calcula pesos AHP a partir de respuestas del usuario

    Args:
        tipo: Tipo de cuestionario
        respuestas: Dict con question_id -> valor en escala Saaty

    Returns:
        Pesos calculados + validación de consistencia
    """
    if tipo == "dotaciones":
        criterios = CRITERIOS_DOTACIONES
    elif tipo == "transporte":
        criterios = CRITERIOS_TRANSPORTE
    elif tipo == "indicadores":
        criterios = CRITERIOS_INDICADORES_PRINCIPALES
    else:
        raise HTTPException(400, "Tipo inválido")

    try:
        resultado = procesar_respuestas(criterios, respuestas)

        return {
            "tipo": tipo,
            "pesos": resultado['pesos'],
            "consistency_ratio": resultado['consistency_ratio'],
            "is_consistent": resultado['is_consistent'],
            "mensaje": (
                "Pesos calculados exitosamente. Matriz consistente." if resultado['is_consistent']
                else f"ADVERTENCIA: Matriz inconsistente (CR={resultado['consistency_ratio']:.3f}). "
                     "Considera revisar tus respuestas para mayor coherencia."
            )
        }

    except Exception as e:
        raise HTTPException(400, f"Error procesando respuestas: {str(e)}")


@router.post("/ahp/idot-personalizado")
async def calcular_idot_personalizado(
    input_data: IDOTPersonalizadoInput,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Calcula IDOT personalizado según pesos AHP del usuario

    Permite al usuario ver cómo cambia el score de dotaciones según
    qué le importa más (salud, educación, comercio, cultura, recreación).

    Ideal para usar después de obtener pesos del cuestionario AHP.
    """
    # Validar que pesos sumen aproximadamente 1.0
    suma_pesos = sum(input_data.pesos.values())
    if not (0.99 <= suma_pesos <= 1.01):
        raise HTTPException(
            400,
            f"Los pesos deben sumar 1.0 (suma actual: {suma_pesos:.3f})"
        )

    async with db.acquire() as conn:
        resultado = await calcular_pesos_dotaciones(
            lat=input_data.latitud,
            lon=input_data.longitud,
            pesos=input_data.pesos,
            conn=conn,
            radios=input_data.radios
        )

    return resultado


@router.get("/ahp/comparar-perfiles")
async def comparar_perfiles(
    latitud: float = Query(..., ge=-90, le=90),
    longitud: float = Query(..., ge=-180, le=180),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Compara IDOT usando diferentes perfiles AHP predefinidos

    Útil para que el usuario vea cómo diferentes prioridades afectan
    el score de una ubicación.

    Perfiles incluidos:
    - equilibrado: Todas las dotaciones igual importancia
    - familiar: Prioridad a salud y educación
    - urbano: Prioridad a comercio y cultura
    - deportivo: Prioridad a recreación
    """
    async with db.acquire() as conn:
        resultado = await comparar_perfiles_ahp(latitud, longitud, conn)

    return resultado


@router.post("/ahp/inmueble-personalizado/{id_inmueble}")
async def recalcular_inmueble_con_pesos_personalizados(
    id_inmueble: int,
    pesos: Dict[str, float],
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Recalcula IDOT para un inmueble existente con pesos personalizados

    Permite al usuario ver cómo cambia la calificación de un inmueble
    específico según sus preferencias.
    """
    # Validar pesos
    suma = sum(pesos.values())
    if not (0.99 <= suma <= 1.01):
        raise HTTPException(400, f"Pesos deben sumar 1.0 (suma actual: {suma:.3f})")

    async with db.acquire() as conn:
        resultado = await aplicar_pesos_personalizados(id_inmueble, pesos, conn)

    return resultado


# ============================================
# Endpoint combinado: Búsqueda + AHP
# ============================================

@router.post("/inteligente")
async def busqueda_inteligente_completa(
    query: str = Query(..., example="cerca a colegios y hospitales"),
    pesos_ahp: Optional[Dict[str, float]] = None,
    iurb_min: float = Query(3.0, ge=0, le=5),
    precio_max: Optional[float] = None,
    limit: int = Query(20, ge=1, le=100),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Búsqueda inteligente combinando RAG + AHP + filtros de I_URB

    Flujo:
    1. Procesa query en lenguaje natural (ej: "cerca a colegios y hospitales")
    2. Extrae categorías de dotaciones buscadas
    3. Busca inmuebles que cumplan:
       - Tengan las dotaciones cercanas
       - I_URB >= iurb_min
       - Precio <= precio_max (opcional)
    4. Si se proporcionan pesos AHP, rankea usando IDOT personalizado

    Ejemplo de uso completo:
    - Usuario completa cuestionario AHP → obtiene pesos personalizados
    - Usuario hace query: "cerca a colegios y hospitales"
    - Sistema busca inmuebles que cumplan y los rankea según sus preferencias
    """
    # Procesar query
    query_info = process_natural_query(query)

    if not query_info['categorias']:
        raise HTTPException(400, "No se identificaron categorías en la query")

    async with db.acquire() as conn:
        # Buscar inmuebles que tengan las dotaciones cercanas
        categorias_sql = query_info['categorias']
        radio = query_info['radio_metros']

        # Query base
        sql = """
            WITH inmuebles_con_dotaciones AS (
                SELECT DISTINCT
                    i.id_inmueble,
                    i.ubicacion,
                    i.tipo_inmueble,
                    i.precio,
                    i.area,
                    i.iurb,
                    i.iacc,
                    i.iseg,
                    i.ihed,
                    i.ipnu,
                    i.idot,
                    i.precio_por_iurb,
                    ST_Y(i.geom) as latitud,
                    ST_X(i.geom) as longitud
                FROM iug.inmueble i
                WHERE i.iurb >= $1
                  AND i.geom IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM iug.dotaciones_poi d
                      WHERE d.categoria = ANY($2)
                        AND ST_DWithin(
                            i.geom::geography,
                            d.geom::geography,
                            $3
                        )
                  )
        """

        params = [iurb_min, categorias_sql, radio]
        param_count = 3

        if precio_max:
            param_count += 1
            sql += f" AND i.precio <= ${param_count}"
            params.append(precio_max)

        sql += " ORDER BY i.iurb DESC, i.precio_por_iurb ASC"
        sql += f" LIMIT ${param_count + 1}"
        params.append(limit)

        sql += ")\nSELECT * FROM inmuebles_con_dotaciones"

        rows = await conn.fetch(sql, *params)

        resultados = [dict(row) for row in rows]

        # Si hay pesos AHP, recalcular IDOT personalizado
        if pesos_ahp:
            for resultado in resultados:
                idot_custom = await calcular_pesos_dotaciones(
                    lat=resultado['latitud'],
                    lon=resultado['longitud'],
                    pesos=pesos_ahp,
                    conn=conn
                )
                resultado['idot_personalizado'] = idot_custom['idot_personalizado']
                resultado['idot_original'] = resultado.pop('idot')

            # Re-ordenar por IDOT personalizado
            resultados.sort(key=lambda x: x['idot_personalizado'], reverse=True)

    return {
        "query": query,
        "query_procesada": query_info,
        "pesos_ahp_aplicados": pesos_ahp,
        "filtros": {
            "iurb_min": iurb_min,
            "precio_max": precio_max
        },
        "resultados": resultados,
        "total": len(resultados)
    }
