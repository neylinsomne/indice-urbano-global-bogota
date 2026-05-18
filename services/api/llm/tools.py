"""
Tools/Functions para que el LLM acceda a datos
Cada tool representa una consulta específica optimizada
"""
from typing import List, Dict, Any, Optional
import asyncpg
import logging

logger = logging.getLogger(__name__)


async def get_estadisticas_localidad(
    conn: asyncpg.Connection,
    nombre_localidad: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Obtiene estadísticas de inmuebles por localidad

    Args:
        nombre_localidad: Filtrar por localidad específica (None = todas)

    Returns:
        Lista de estadísticas por localidad
    """
    query = """
        SELECT
            nombre_localidad,
            total_inmuebles,
            precio_promedio,
            precio_minimo,
            precio_maximo,
            iurb_promedio,
            iacc_promedio,
            iseg_promedio,
            ihed_promedio,
            ipnu_promedio,
            precio_por_iurb_promedio,
            total_apartamentos,
            total_casas
        FROM iug.v_estadisticas_localidad
    """

    if nombre_localidad:
        query += " WHERE nombre_localidad ILIKE $1"
        rows = await conn.fetch(query, f"%{nombre_localidad}%")
    else:
        rows = await conn.fetch(query)

    return [dict(row) for row in rows]


async def get_top_oportunidades(
    conn: asyncpg.Connection,
    limite: int = 10,
    tipo_inmueble: Optional[str] = None,
    iurb_min: float = 3.0
) -> List[Dict[str, Any]]:
    """
    Obtiene los inmuebles con mejor relación precio/I_URB (mejores oportunidades)

    Args:
        limite: Número máximo de resultados
        tipo_inmueble: Filtrar por tipo (Apartamento, Casa, etc.)
        iurb_min: I_URB mínimo requerido

    Returns:
        Lista de mejores oportunidades
    """
    query = """
        SELECT
            id_inmueble,
            tipo_inmueble,
            precio,
            ubicacion,
            area,
            habitaciones,
            banos,
            iurb,
            iacc,
            iseg,
            ihed,
            ipnu,
            precio_por_iurb,
            latitud,
            longitud,
            percentil_oportunidad
        FROM iug.v_top_oportunidades
        WHERE iurb >= $1
    """

    params = [iurb_min]

    if tipo_inmueble:
        query += " AND tipo_inmueble = $2"
        params.append(tipo_inmueble)
        query += " ORDER BY precio_por_iurb ASC LIMIT $3"
        params.append(limite)
    else:
        query += " ORDER BY precio_por_iurb ASC LIMIT $2"
        params.append(limite)

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_precios_por_tipo(
    conn: asyncpg.Connection
) -> List[Dict[str, Any]]:
    """
    Obtiene estadísticas de precios agrupadas por tipo de inmueble

    Returns:
        Lista con estadísticas (promedio, mediana, percentiles) por tipo
    """
    query = """
        SELECT
            tipo_inmueble,
            total,
            precio_promedio,
            precio_p25,
            precio_mediana,
            precio_p75,
            precio_min,
            precio_max,
            area_promedio,
            precio_m2_promedio
        FROM iug.v_precios_por_tipo
        ORDER BY total DESC
    """

    rows = await conn.fetch(query)
    return [dict(row) for row in rows]


async def get_ranking_zonas(
    conn: asyncpg.Connection,
    ordenar_por: str = 'iurb'
) -> List[Dict[str, Any]]:
    """
    Obtiene ranking de localidades por indicador

    Args:
        ordenar_por: Indicador para ordenar (iurb, iacc, iseg, ihed, ipnu)

    Returns:
        Lista de localidades ordenadas por el indicador
    """
    columna_ranking = f"ranking_{ordenar_por}"

    query = f"""
        SELECT
            nombre_localidad,
            iurb_promedio,
            iacc_promedio,
            iseg_promedio,
            ihed_promedio,
            ipnu_promedio,
            total_inmuebles,
            {columna_ranking} as ranking
        FROM iug.v_ranking_zonas
        ORDER BY {columna_ranking} ASC
    """

    rows = await conn.fetch(query)
    return [dict(row) for row in rows]


async def get_inmuebles_contexto(
    conn: asyncpg.Connection,
    id_inmueble: Optional[int] = None,
    localidad: Optional[str] = None,
    limite: int = 10
) -> List[Dict[str, Any]]:
    """
    Obtiene inmuebles con contexto completo (dotaciones, transporte, seguridad)

    Args:
        id_inmueble: Filtrar por ID específico
        localidad: Filtrar por localidad
        limite: Máximo de resultados

    Returns:
        Lista de inmuebles con contexto completo
    """
    query = """
        SELECT
            id_inmueble,
            tipo_inmueble,
            precio,
            ubicacion,
            area,
            habitaciones,
            banos,
            iurb,
            iacc,
            iseg,
            ihed,
            ipnu,
            precio_por_iurb,
            latitud,
            longitud,
            nombre_localidad,
            salud_500m,
            educacion_500m,
            recreacion_500m,
            transmilenio_500m,
            tasa_hurto_localidad
        FROM iug.v_inmuebles_contexto
        WHERE 1=1
    """

    params = []
    param_count = 1

    if id_inmueble:
        query += f" AND id_inmueble = ${param_count}"
        params.append(id_inmueble)
        param_count += 1

    if localidad:
        query += f" AND nombre_localidad ILIKE ${param_count}"
        params.append(f"%{localidad}%")
        param_count += 1

    query += f" ORDER BY iurb DESC LIMIT ${param_count}"
    params.append(limite)

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_dotaciones_por_zona(
    conn: asyncpg.Connection,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radio_km: float = 2.0
) -> List[Dict[str, Any]]:
    """
    Obtiene conteo de dotaciones por zona (grid 1km x 1km)

    Args:
        lat: Latitud del centro (opcional)
        lon: Longitud del centro (opcional)
        radio_km: Radio de búsqueda en km desde el centro

    Returns:
        Lista de zonas con conteo de dotaciones
    """
    query = """
        SELECT
            lat_centro,
            lon_centro,
            total_salud,
            total_educacion,
            total_comercio,
            total_cultura,
            total_recreacion,
            total_dotaciones
        FROM iug.v_dotaciones_por_zona
        WHERE total_dotaciones > 0
    """

    params = []

    if lat and lon:
        # Filtrar por distancia al punto
        query += """
            AND ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_Point($1, $2), 4326)::geography,
                $3
            )
        """
        params = [lon, lat, radio_km * 1000]  # Convertir km a metros

    query += " ORDER BY total_dotaciones DESC LIMIT 50"

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def buscar_inmuebles_similares(
    conn: asyncpg.Connection,
    precio_referencia: float,
    area_referencia: float,
    tipo_inmueble: str,
    margen_precio: float = 0.20,
    margen_area: float = 0.15,
    limite: int = 10
) -> List[Dict[str, Any]]:
    """
    Busca inmuebles similares en precio y área (útil para regresión/comparables)

    Args:
        precio_referencia: Precio de referencia
        area_referencia: Área de referencia (m²)
        tipo_inmueble: Tipo de inmueble
        margen_precio: Margen de variación en precio (0.20 = ±20%)
        margen_area: Margen de variación en área (0.15 = ±15%)
        limite: Máximo de resultados

    Returns:
        Lista de inmuebles similares
    """
    precio_min = precio_referencia * (1 - margen_precio)
    precio_max = precio_referencia * (1 + margen_precio)
    area_min = area_referencia * (1 - margen_area)
    area_max = area_referencia * (1 + margen_area)

    query = """
        SELECT
            id_inmueble,
            tipo_inmueble,
            precio,
            ubicacion,
            area,
            habitaciones,
            banos,
            iurb,
            precio_por_iurb,
            ST_Y(geom) as latitud,
            ST_X(geom) as longitud,
            ABS(precio - $1) as diferencia_precio,
            ABS(area - $2) as diferencia_area
        FROM iug.inmueble
        WHERE tipo_inmueble = $3
          AND precio BETWEEN $4 AND $5
          AND area BETWEEN $6 AND $7
          AND iurb IS NOT NULL
        ORDER BY
            ABS(precio - $1) + ABS(area - $2)  -- Minimizar diferencias combinadas
        LIMIT $8
    """

    rows = await conn.fetch(
        query,
        precio_referencia,
        area_referencia,
        tipo_inmueble,
        precio_min,
        precio_max,
        area_min,
        area_max,
        limite
    )

    return [dict(row) for row in rows]


async def buscar_por_caracteristicas(
    conn: asyncpg.Connection,
    caracteristicas: List[str],
    tipo_inmueble: Optional[str] = None,
    localidad: Optional[str] = None,
    precio_max: Optional[float] = None,
    limite: int = 10
) -> List[Dict[str, Any]]:
    """
    Busca inmuebles que tengan las características/amenidades especificadas

    Args:
        caracteristicas: Lista de amenidades requeridas (ej: ['piscina', 'gimnasio'])
        tipo_inmueble: Filtrar por tipo (Apartamento, Casa, etc.)
        localidad: Filtrar por localidad
        precio_max: Precio máximo
        limite: Máximo resultados

    Returns:
        Lista de inmuebles que tienen TODAS las características solicitadas
    """
    if not caracteristicas:
        return []

    caract_conditions = []
    params = []
    param_idx = 1

    for caract in caracteristicas:
        caract_conditions.append(
            f"""EXISTS (
                SELECT 1 FROM iug.inmueble_caracteristica ic
                WHERE ic.id_inmueble = i.id_inmueble
                  AND ic.nombre ILIKE ${param_idx}
                  AND ic.valor_bool = TRUE
            )"""
        )
        params.append(f"%{caract}%")
        param_idx += 1

    query = f"""
        SELECT
            i.id_inmueble,
            i.tipo_inmueble,
            i.precio,
            i.ubicacion,
            i.area,
            i.habitaciones,
            i.banos,
            i.iurb,
            ST_Y(i.geom) AS latitud,
            ST_X(i.geom) AS longitud,
            l.nombre AS nombre_localidad,
            (SELECT array_agg(ic2.nombre)
             FROM iug.inmueble_caracteristica ic2
             WHERE ic2.id_inmueble = i.id_inmueble AND ic2.valor_bool = TRUE
            ) AS todas_caracteristicas
        FROM iug.inmueble i
        LEFT JOIN iug.localidad l ON ST_Contains(l.geom, i.geom)
        WHERE {' AND '.join(caract_conditions)}
    """

    if tipo_inmueble:
        query += f" AND i.tipo_inmueble = ${param_idx}"
        params.append(tipo_inmueble)
        param_idx += 1

    if localidad:
        query += f" AND l.nombre ILIKE ${param_idx}"
        params.append(f"%{localidad}%")
        param_idx += 1

    if precio_max:
        query += f" AND i.precio <= ${param_idx}"
        params.append(precio_max)
        param_idx += 1

    query += f" ORDER BY i.iurb DESC NULLS LAST LIMIT ${param_idx}"
    params.append(limite)

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_catalogo_caracteristicas(
    conn: asyncpg.Connection,
    buscar: Optional[str] = None,
    min_inmuebles: int = 5
) -> List[Dict[str, Any]]:
    """
    Lista las características/amenidades disponibles con su frecuencia

    Args:
        buscar: Texto para filtrar características (ej: 'parq' encuentra 'parqueadero')
        min_inmuebles: Mínimo de inmuebles con la característica

    Returns:
        Lista de características con total_inmuebles
    """
    query = """
        SELECT
            nombre AS caracteristica,
            COUNT(*) AS total_inmuebles
        FROM iug.inmueble_caracteristica
        WHERE valor_bool = TRUE
    """

    params = []
    param_idx = 1

    if buscar:
        query += f" AND nombre ILIKE ${param_idx}"
        params.append(f"%{buscar}%")
        param_idx += 1

    query += f"""
        GROUP BY nombre
        HAVING COUNT(*) >= ${param_idx}
        ORDER BY total_inmuebles DESC
    """
    params.append(min_inmuebles)

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_caracteristicas_por_zona(
    conn: asyncpg.Connection,
    caracteristica: str,
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    Muestra qué localidades tienen más inmuebles con una característica específica

    Args:
        caracteristica: Nombre del amenity (ej: 'piscina')
        top_n: Número de localidades a mostrar

    Returns:
        Lista de localidades con conteo y porcentaje
    """
    query = """
        SELECT
            l.nombre AS nombre_localidad,
            COUNT(CASE WHEN ic.id_inmueble IS NOT NULL THEN 1 END) AS inmuebles_con_caracteristica,
            COUNT(DISTINCT i.id_inmueble) AS total_inmuebles_localidad,
            ROUND(
                100.0 * COUNT(CASE WHEN ic.id_inmueble IS NOT NULL THEN 1 END) /
                NULLIF(COUNT(DISTINCT i.id_inmueble), 0), 2
            ) AS pct_con_caracteristica
        FROM iug.localidad l
        JOIN iug.inmueble i ON ST_Contains(l.geom, i.geom)
        LEFT JOIN iug.inmueble_caracteristica ic
            ON i.id_inmueble = ic.id_inmueble
            AND ic.nombre ILIKE $1
            AND ic.valor_bool = TRUE
        GROUP BY l.nombre
        HAVING COUNT(CASE WHEN ic.id_inmueble IS NOT NULL THEN 1 END) > 0
        ORDER BY pct_con_caracteristica DESC
        LIMIT $2
    """

    rows = await conn.fetch(query, f"%{caracteristica}%", top_n)
    return [dict(row) for row in rows]


async def get_estadisticas_generales(
    conn: asyncpg.Connection
) -> Dict[str, Any]:
    """
    Obtiene estadísticas generales del sistema

    Returns:
        Dict con métricas globales
    """
    query = """
        SELECT
            COUNT(*) as total_inmuebles,
            COUNT(DISTINCT tipo_inmueble) as tipos_diferentes,
            AVG(precio)::BIGINT as precio_promedio_global,
            AVG(iurb)::NUMERIC(4,2) as iurb_promedio_global,
            AVG(area)::NUMERIC(10,2) as area_promedio_global,
            COUNT(CASE WHEN iurb >= 4.0 THEN 1 END) as inmuebles_excelentes,
            COUNT(CASE WHEN iurb >= 3.0 AND iurb < 4.0 THEN 1 END) as inmuebles_buenos,
            COUNT(CASE WHEN iurb < 3.0 THEN 1 END) as inmuebles_regulares
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
    """

    row = await conn.fetchrow(query)
    return dict(row) if row else {}


# Mapeo de nombres de funciones para el LLM
AVAILABLE_TOOLS = {
    'get_estadisticas_localidad': {
        'function': get_estadisticas_localidad,
        'description': 'Obtiene estadísticas de inmuebles agrupadas por localidad (precio promedio, indicadores, cantidad)',
        'parameters': {
            'nombre_localidad': 'Nombre de la localidad (opcional)'
        }
    },
    'get_top_oportunidades': {
        'function': get_top_oportunidades,
        'description': 'Encuentra las mejores oportunidades (mejor relación precio/calidad)',
        'parameters': {
            'limite': 'Número de resultados',
            'tipo_inmueble': 'Tipo de inmueble (opcional)',
            'iurb_min': 'I_URB mínimo requerido'
        }
    },
    'get_precios_por_tipo': {
        'function': get_precios_por_tipo,
        'description': 'Estadísticas de precios por tipo de inmueble (promedio, mediana, percentiles)',
        'parameters': {}
    },
    'get_ranking_zonas': {
        'function': get_ranking_zonas,
        'description': 'Ranking de localidades por indicador específico',
        'parameters': {
            'ordenar_por': 'Indicador para ordenar (iurb, iacc, iseg, ihed, ipnu)'
        }
    },
    'get_inmuebles_contexto': {
        'function': get_inmuebles_contexto,
        'description': 'Inmuebles con contexto completo (dotaciones cercanas, transporte, seguridad)',
        'parameters': {
            'id_inmueble': 'ID específico (opcional)',
            'localidad': 'Filtrar por localidad (opcional)',
            'limite': 'Máximo de resultados'
        }
    },
    'get_dotaciones_por_zona': {
        'function': get_dotaciones_por_zona,
        'description': 'Conteo de dotaciones por zona geográfica',
        'parameters': {
            'lat': 'Latitud central (opcional)',
            'lon': 'Longitud central (opcional)',
            'radio_km': 'Radio de búsqueda en km'
        }
    },
    'buscar_inmuebles_similares': {
        'function': buscar_inmuebles_similares,
        'description': 'Busca inmuebles similares en precio y área (para análisis comparativos)',
        'parameters': {
            'precio_referencia': 'Precio de referencia',
            'area_referencia': 'Área de referencia (m²)',
            'tipo_inmueble': 'Tipo de inmueble',
            'margen_precio': 'Margen de variación en precio (0.20 = ±20%)',
            'margen_area': 'Margen de variación en área',
            'limite': 'Máximo de resultados'
        }
    },
    'get_estadisticas_generales': {
        'function': get_estadisticas_generales,
        'description': 'Estadísticas generales del sistema completo',
        'parameters': {}
    },
    'buscar_por_caracteristicas': {
        'function': buscar_por_caracteristicas,
        'description': 'Busca inmuebles que tengan características/amenidades específicas (piscina, gimnasio, parqueadero, vigilancia, ascensor, etc.). Combina múltiples amenidades.',
        'parameters': {
            'caracteristicas': 'Lista de amenidades requeridas (ej: ["piscina", "gimnasio"])',
            'tipo_inmueble': 'Tipo de inmueble (opcional)',
            'localidad': 'Nombre de localidad (opcional)',
            'precio_max': 'Precio máximo (opcional)',
            'limite': 'Máximo de resultados'
        }
    },
    'get_catalogo_caracteristicas': {
        'function': get_catalogo_caracteristicas,
        'description': 'Lista todas las características/amenidades disponibles con su frecuencia. Usar para saber qué amenidades existen antes de buscar.',
        'parameters': {
            'buscar': 'Texto para filtrar (opcional)',
            'min_inmuebles': 'Mínimo de inmuebles con la característica'
        }
    },
    'get_caracteristicas_por_zona': {
        'function': get_caracteristicas_por_zona,
        'description': 'Muestra distribución de una amenidad por localidad. Ej: qué zonas tienen más piscina o gimnasio.',
        'parameters': {
            'caracteristica': 'Nombre del amenity (ej: piscina)',
            'top_n': 'Número de localidades a mostrar'
        }
    }
}
