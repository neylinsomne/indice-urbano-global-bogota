"""
Router de I_URB (Indicador Urbanístico Global)

Endpoints:
- GET /api/iurb/{id_inmueble}: Obtener I_URB e indicadores completos
- POST /api/iurb/calcular: Calcular I_URB para coordenadas nuevas
- GET /api/iurb/oportunidades: Buscar mejores oportunidades precio/I_URB
- POST /api/iurb/estudio-individual: Generar informe completo (regresión + score)
- GET /api/iurb/estadisticas: Estadísticas generales
- POST /api/iurb/recalcular: Recalcular I_URB masivo
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import asyncpg
import logging

from db.postgre import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iurb", tags=["iurb"])


# ============================================
# Modelos Pydantic
# ============================================

class IndicadoresResponse(BaseModel):
    """Respuesta con todos los indicadores de un inmueble"""
    id_inmueble: int
    ubicacion: Optional[str]
    tipo_inmueble: Optional[str]
    precio: Optional[float]
    area: Optional[float]

    # Indicadores
    iurb: Optional[float] = Field(None, description="Indicador Urbanístico Global (0-5)")
    iacc: Optional[float] = Field(None, description="Accesibilidad (0-5)")
    iseg: Optional[float] = Field(None, description="Seguridad (0-5)")
    ihed: Optional[float] = Field(None, description="Calidad Hedónica (0-5)")
    ipnu: Optional[float] = Field(None, description="Potencial Normativo (0-5)")

    # Análisis
    precio_por_iurb: Optional[float] = Field(None, description="Ratio precio/I_URB")
    precio_m2: Optional[float] = Field(None, description="Precio por m²")
    categoria_oportunidad: Optional[str] = Field(None, description="Categoría de oportunidad")
    interpretacion: Optional[str] = Field(None, description="Interpretación I_URB")


class CoordenadasInput(BaseModel):
    """Input para calcular I_URB de coordenadas nuevas"""
    latitud: float = Field(..., ge=-90, le=90, description="Latitud WGS84")
    longitud: float = Field(..., ge=-180, le=180, description="Longitud WGS84")
    tipo_inmueble: Optional[str] = Field("Apartamento", description="Tipo de inmueble")


class EstudioIndividualInput(BaseModel):
    """Input para estudio individual completo"""
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    tipo_inmueble: str = Field(..., description="Apartamento, Casa, etc.")
    area: float = Field(..., gt=0, description="Área en m²")
    habitaciones: Optional[int] = Field(None, ge=0)
    banos: Optional[int] = Field(None, ge=0)
    estrato: Optional[int] = Field(None, ge=1, le=6)


class OportunidadResponse(BaseModel):
    """Respuesta de búsqueda de oportunidades"""
    id_inmueble: int
    ubicacion: str
    tipo_inmueble: str
    precio: float
    iurb: float
    precio_por_iurb: float
    categoria_oportunidad: str
    percentil_ratio: float


class EstadisticasResponse(BaseModel):
    """Estadísticas generales de I_URB"""
    total_inmuebles: int
    con_iurb: int
    cobertura_pct: float
    promedio: Optional[float]
    mediana: Optional[float]
    desviacion: Optional[float]
    minimo: Optional[float]
    maximo: Optional[float]


# ============================================
# Endpoints
# ============================================

@router.get("/detalle/{id_inmueble}", response_model=IndicadoresResponse)
async def obtener_iurb(
    id_inmueble: int,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene I_URB e indicadores completos de un inmueble existente

    Retorna:
    - Todos los indicadores (I_URB, I_ACC, I_SEG, I_HED, I_PNU)
    - Ratio precio/I_URB
    - Categoría de oportunidad
    - Interpretación
    """
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                i.id_inmueble,
                i.ubicacion,
                i.tipo_inmueble,
                i.precio,
                i.area,
                ROUND(i.iurb::numeric, 2) as iurb,
                ROUND(i.iacc::numeric, 2) as iacc,
                ROUND(i.iseg::numeric, 2) as iseg,
                ROUND(i.ihed::numeric, 2) as ihed,
                ROUND(i.ipnu::numeric, 2) as ipnu,
                ROUND(i.precio_por_iurb::numeric, 2) as precio_por_iurb,
                ROUND((i.precio / NULLIF(i.area, 0))::numeric, 0) as precio_m2,
                CASE
                    WHEN i.iurb >= 4.5 THEN 'Excelente'
                    WHEN i.iurb >= 4.0 THEN 'Muy Bueno'
                    WHEN i.iurb >= 3.5 THEN 'Bueno'
                    WHEN i.iurb >= 3.0 THEN 'Regular'
                    WHEN i.iurb >= 2.5 THEN 'Por Debajo del Promedio'
                    ELSE 'Deficiente'
                END as interpretacion,
                ao.categoria_oportunidad
            FROM iug.inmueble i
            LEFT JOIN iug.analisis_oportunidades ao ON i.id_inmueble = ao.id_inmueble
            WHERE i.id_inmueble = $1
        """, id_inmueble)

    if not row:
        raise HTTPException(404, f"Inmueble {id_inmueble} no encontrado")

    return dict(row)


@router.post("/calcular")
async def calcular_iurb_coordenadas(
    input_data: CoordenadasInput,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Calcula I_URB para coordenadas específicas (inmueble nuevo)

    Útil para estudio individual: usuario proporciona lat/lon de su propiedad
    y obtiene los indicadores calculados en tiempo real.

    Returns:
    - Indicadores calculados (I_ACC, I_SEG, I_HED, I_PNU, I_URB)
    - Información de zonas POT
    - Comparación con promedio del sector
    """
    async with db.acquire() as conn:
        # Crear punto temporal
        point_wkt = f"POINT({input_data.longitud} {input_data.latitud})"

        # Calcular indicadores en una sola query
        result = await conn.fetchrow("""
            WITH punto AS (
                SELECT ST_SetSRID(ST_GeomFromText($1), 4326) as geom
            ),
            indicadores AS (
                SELECT
                    -- I_ACC: Calcular gravity score
                    COALESCE(
                        ROUND(iug.calcular_score_gravity(p.geom, 800, 1500)::numeric, 2),
                        0
                    ) as iacc_raw,

                    -- I_SEG: Score promedio de localidad
                    COALESCE(
                        (SELECT ROUND(AVG(iseg)::numeric, 2)
                         FROM iug.inmueble i2
                         WHERE ST_DWithin(i2.geom::geography, p.geom::geography, 1000)
                         AND iseg IS NOT NULL),
                        3.0
                    ) as iseg_estimado,

                    -- I_HED: Score promedio de área cercana
                    COALESCE(
                        (SELECT ROUND(AVG(ihed)::numeric, 2)
                         FROM iug.inmueble i2
                         WHERE ST_DWithin(i2.geom::geography, p.geom::geography, 500)
                         AND ihed IS NOT NULL),
                        3.0
                    ) as ihed_estimado,

                    -- I_PNU: Calcular desde POT
                    COALESCE(
                        ROUND((
                            0.4 * iug.score_tratamiento(t.nombre) +
                            0.4 * iug.score_edificabilidad(e.rango) +
                            0.2 * iug.score_area_actividad(a.codigo)
                        )::numeric, 2),
                        NULL
                    ) as ipnu,

                    -- Info POT
                    t.nombre as tratamiento,
                    e.rango as edificabilidad,
                    a.codigo as area_actividad,
                    a.nombre as area_actividad_nombre

                FROM punto p
                LEFT JOIN iug.pot_tratamiento t ON ST_Within(p.geom, t.geom)
                LEFT JOIN iug.pot_edificabilidad e ON ST_Within(p.geom, e.geom)
                LEFT JOIN iug.pot_area_actividad a ON ST_Within(p.geom, a.geom)
            )
            SELECT
                iacc_raw,
                iseg_estimado,
                ihed_estimado,
                ipnu,
                -- Calcular I_URB
                ROUND((
                    COALESCE(iacc_raw * 0.25, 0) +
                    COALESCE(iseg_estimado * 0.20, 0) +
                    COALESCE(ihed_estimado * 0.25, 0) +
                    COALESCE(ipnu * 0.30, 0)
                ) / (
                    (CASE WHEN iacc_raw IS NOT NULL THEN 0.25 ELSE 0 END) +
                    (CASE WHEN iseg_estimado IS NOT NULL THEN 0.20 ELSE 0 END) +
                    (CASE WHEN ihed_estimado IS NOT NULL THEN 0.25 ELSE 0 END) +
                    (CASE WHEN ipnu IS NOT NULL THEN 0.30 ELSE 0 END)
                )::numeric, 2) as iurb,
                tratamiento,
                edificabilidad,
                area_actividad,
                area_actividad_nombre
            FROM indicadores
        """, point_wkt)

    if not result:
        raise HTTPException(500, "Error calculando indicadores")

    # Interpretación
    iurb = result['iurb']
    if iurb >= 4.5:
        interpretacion = "Excelente"
    elif iurb >= 4.0:
        interpretacion = "Muy Bueno"
    elif iurb >= 3.5:
        interpretacion = "Bueno"
    elif iurb >= 3.0:
        interpretacion = "Regular"
    else:
        interpretacion = "Por Debajo del Promedio"

    return {
        "coordenadas": {
            "latitud": input_data.latitud,
            "longitud": input_data.longitud
        },
        "tipo_inmueble": input_data.tipo_inmueble,
        "indicadores": {
            "iurb": result['iurb'],
            "iacc": result['iacc_raw'],
            "iseg": result['iseg_estimado'],
            "ihed": result['ihed_estimado'],
            "ipnu": result['ipnu']
        },
        "interpretacion": interpretacion,
        "pot": {
            "tratamiento": result['tratamiento'],
            "edificabilidad": result['edificabilidad'],
            "area_actividad": result['area_actividad'],
            "area_actividad_nombre": result['area_actividad_nombre']
        }
    }


@router.get("/oportunidades", response_model=List[OportunidadResponse])
async def buscar_oportunidades(
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar por tipo"),
    iurb_min: float = Query(3.5, ge=0, le=5, description="I_URB mínimo"),
    precio_max: Optional[float] = Query(None, description="Precio máximo"),
    limit: int = Query(20, ge=1, le=100, description="Número de resultados"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Busca mejores oportunidades basadas en ratio precio/I_URB

    Estrategia:
    - Bajo precio_por_iurb = Buena oportunidad (alta calidad, precio razonable)
    - Alto I_URB = Ubicación premium
    - Percentil bajo = Mejor relación precio/calidad

    Params:
    - tipo_inmueble: Filtrar por tipo (Apartamento, Casa, etc.)
    - iurb_min: I_URB mínimo requerido (default 3.5)
    - precio_max: Precio máximo
    - limit: Número de resultados (max 100)
    """
    query = """
        SELECT
            id_inmueble,
            ubicacion,
            tipo_inmueble,
            precio,
            iurb,
            precio_por_iurb,
            categoria_oportunidad,
            percentil_ratio
        FROM iug.analisis_oportunidades
        WHERE iurb >= $1
    """

    params = [iurb_min]
    param_count = 1

    if tipo_inmueble:
        param_count += 1
        query += f" AND tipo_inmueble = ${param_count}"
        params.append(tipo_inmueble)

    if precio_max:
        param_count += 1
        query += f" AND precio <= ${param_count}"
        params.append(precio_max)

    query += f" ORDER BY precio_por_iurb ASC LIMIT ${param_count + 1}"
    params.append(limit)

    async with db.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [dict(row) for row in rows]


@router.post("/estudio-individual")
async def estudio_individual(
    input_data: EstudioIndividualInput,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Genera informe completo para estudio individual

    Combina:
    1. Valor estimado por regresión lineal del mercado
    2. I_URB y sub-indicadores de la ubicación
    3. Comparación con inmuebles similares
    4. Recomendaciones

    Input: Usuario proporciona características de su propiedad
    Output: Informe completo con valoración y análisis
    """
    async with db.acquire() as conn:
        # 1. Calcular indicadores de ubicación
        point_wkt = f"POINT({input_data.longitud} {input_data.latitud})"

        indicadores = await conn.fetchrow("""
            WITH punto AS (
                SELECT ST_SetSRID(ST_GeomFromText($1), 4326) as geom
            )
            SELECT
                ROUND(COALESCE(iug.calcular_score_gravity(p.geom, 800, 1500), 0)::numeric, 2) as iacc,
                ROUND(COALESCE((
                    SELECT AVG(iseg)
                    FROM iug.inmueble i2
                    WHERE ST_DWithin(i2.geom::geography, p.geom::geography, 1000)
                    AND iseg IS NOT NULL
                ), 3.0)::numeric, 2) as iseg,
                ROUND(COALESCE((
                    SELECT AVG(ihed)
                    FROM iug.inmueble i2
                    WHERE ST_DWithin(i2.geom::geography, p.geom::geography, 500)
                    AND ihed IS NOT NULL
                ), 3.0)::numeric, 2) as ihed,
                ROUND(COALESCE((
                    0.4 * iug.score_tratamiento(t.nombre) +
                    0.4 * iug.score_edificabilidad(e.rango) +
                    0.2 * iug.score_area_actividad(a.codigo)
                ), 2.5)::numeric, 2) as ipnu
            FROM punto p
            LEFT JOIN iug.pot_tratamiento t ON ST_Within(p.geom, t.geom)
            LEFT JOIN iug.pot_edificabilidad e ON ST_Within(p.geom, e.geom)
            LEFT JOIN iug.pot_area_actividad a ON ST_Within(p.geom, a.geom)
        """, point_wkt)

        # Calcular I_URB
        iacc = indicadores['iacc']
        iseg = indicadores['iseg']
        ihed = indicadores['ihed']
        ipnu = indicadores['ipnu']

        iurb = round(
            (iacc * 0.25 + iseg * 0.20 + ihed * 0.25 + ipnu * 0.30) /
            (0.25 + 0.20 + 0.25 + 0.30),
            2
        )

        # 2. Estimar precio por regresión lineal simple
        # (Modelo básico: precio = f(area, habitaciones, iurb, tipo))
        precio_estimado = await conn.fetchval("""
            WITH similares AS (
                SELECT
                    precio,
                    area,
                    iurb
                FROM iug.inmueble
                WHERE tipo_inmueble = $1
                  AND area BETWEEN $2 * 0.8 AND $2 * 1.2
                  AND precio IS NOT NULL
                  AND iurb IS NOT NULL
                  AND habitaciones = $3
                LIMIT 50
            )
            SELECT
                ROUND(AVG(precio / area) * $2)::bigint as precio_estimado
            FROM similares
        """, input_data.tipo_inmueble, input_data.area, input_data.habitaciones or 2)

        # 3. Comparar con mercado local
        comparacion = await conn.fetchrow("""
            SELECT
                COUNT(*) as n_similares,
                ROUND(AVG(precio)::numeric, 0) as precio_promedio,
                ROUND(AVG(precio_por_iurb)::numeric, 0) as ratio_promedio,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY precio)::numeric, 0) as precio_mediana
            FROM iug.analisis_oportunidades
            WHERE tipo_inmueble = $1
              AND iurb BETWEEN $2 - 0.5 AND $2 + 0.5
        """, input_data.tipo_inmueble, iurb)

    # Generar recomendaciones
    recomendaciones = []

    if iurb >= 4.5:
        recomendaciones.append("Ubicación premium con excelente calidad urbana")
    elif iurb >= 4.0:
        recomendaciones.append("Muy buena ubicación con alto potencial")
    elif iurb < 3.0:
        recomendaciones.append("Ubicación con limitaciones. Considerar mejoras en accesibilidad")

    if ipnu >= 4.0:
        recomendaciones.append("Alto potencial de desarrollo según POT")

    if iacc < 2.5:
        recomendaciones.append("Accesibilidad limitada a transporte público")

    if iseg < 2.5:
        recomendaciones.append("Zona con indicadores de seguridad por debajo del promedio")

    return {
        "resumen": {
            "tipo_inmueble": input_data.tipo_inmueble,
            "area": input_data.area,
            "habitaciones": input_data.habitaciones,
            "banos": input_data.banos
        },
        "valoracion": {
            "precio_estimado": precio_estimado or 0,
            "precio_m2_estimado": round((precio_estimado or 0) / input_data.area, 0) if input_data.area > 0 else 0,
            "metodo": "Regresión basada en inmuebles similares"
        },
        "indicadores": {
            "iurb": iurb,
            "iacc": iacc,
            "iseg": iseg,
            "ihed": ihed,
            "ipnu": ipnu,
            "interpretacion": "Excelente" if iurb >= 4.5 else "Muy Bueno" if iurb >= 4.0 else "Bueno" if iurb >= 3.5 else "Regular"
        },
        "comparacion_mercado": {
            "inmuebles_similares": comparacion['n_similares'],
            "precio_promedio": float(comparacion['precio_promedio']) if comparacion['precio_promedio'] else 0,
            "precio_mediana": float(comparacion['precio_mediana']) if comparacion['precio_mediana'] else 0,
            "ratio_promedio": float(comparacion['ratio_promedio']) if comparacion['ratio_promedio'] else 0
        },
        "recomendaciones": recomendaciones
    }


@router.get("/estadisticas", response_model=EstadisticasResponse)
async def estadisticas_iurb(
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Estadísticas generales de I_URB en toda la base de datos

    Incluye:
    - Cobertura (% inmuebles con I_URB)
    - Promedio, mediana, desviación
    - Rangos min/max
    """
    async with db.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_inmuebles,
                COUNT(iurb) as con_iurb,
                ROUND(COUNT(iurb)::numeric / COUNT(*)::numeric * 100, 1) as cobertura_pct,
                ROUND(AVG(iurb)::numeric, 2) as promedio,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as mediana,
                ROUND(STDDEV(iurb)::numeric, 2) as desviacion,
                ROUND(MIN(iurb)::numeric, 2) as minimo,
                ROUND(MAX(iurb)::numeric, 2) as maximo
            FROM iug.inmueble
        """)

    return dict(stats)


@router.post("/recalcular")
async def recalcular_iurb_masivo(
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Recalcula I_URB para todos los inmuebles (operación pesada)

    Se ejecuta en background. Útil después de:
    - Actualizar indicadores base (I_ACC, I_SEG, etc.)
    - Cambiar pesos de la fórmula
    - Batch masivo de nuevos inmuebles
    """
    async def recalcular():
        try:
            async with db.acquire() as conn:
                # Ejecutar script de cálculo
                await conn.execute("""
                    UPDATE iug.inmueble
                    SET iurb = (
                        COALESCE(iacc * 0.25, 0) +
                        COALESCE(iseg * 0.20, 0) +
                        COALESCE(ihed * 0.25, 0) +
                        COALESCE(ipnu * 0.30, 0)
                    ) / (
                        (CASE WHEN iacc IS NOT NULL THEN 0.25 ELSE 0 END) +
                        (CASE WHEN iseg IS NOT NULL THEN 0.20 ELSE 0 END) +
                        (CASE WHEN ihed IS NOT NULL THEN 0.25 ELSE 0 END) +
                        (CASE WHEN ipnu IS NOT NULL THEN 0.30 ELSE 0 END)
                    )
                    WHERE (
                        (CASE WHEN iacc IS NOT NULL THEN 1 ELSE 0 END) +
                        (CASE WHEN iseg IS NOT NULL THEN 1 ELSE 0 END) +
                        (CASE WHEN ihed IS NOT NULL THEN 1 ELSE 0 END) +
                        (CASE WHEN ipnu IS NOT NULL THEN 1 ELSE 0 END)
                    ) >= 2
                """)

                # Refresh vista materializada
                await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY iug.analisis_oportunidades")

            logger.info("I_URB recalculado exitosamente")

        except Exception as e:
            logger.error(f"Error recalculando I_URB: {e}", exc_info=True)

    background_tasks.add_task(recalcular)

    return {
        "status": "processing",
        "message": "Recálculo de I_URB iniciado en background"
    }
