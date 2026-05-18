"""
Aplicación de pesos AHP personalizados a cálculo de IDOT (dotaciones)

Permite calcular IDOT con pesos personalizados según preferencias del usuario.
"""
from typing import Dict, Optional
import asyncpg
import logging

logger = logging.getLogger(__name__)

# Pesos por defecto (todos iguales)
PESOS_DEFAULT_DOTACIONES = {
    'salud': 0.20,
    'educacion': 0.20,
    'comercio': 0.20,
    'cultura': 0.20,
    'recreacion': 0.20
}

# Mapeo de categorías generales a categorías específicas en BD
CATEGORIA_MAPPING = {
    'salud': ['ips', 'farmacia'],
    'educacion': ['colegio', 'universidad'],
    'comercio': ['centro_comercial', 'plaza_mercado'],
    'cultura': ['biblioteca', 'teatro'],
    'recreacion': ['parque', 'cancha_futbol']
}


async def calcular_pesos_dotaciones(
    lat: float,
    lon: float,
    pesos: Dict[str, float],
    conn: asyncpg.Connection,
    radios: Optional[Dict[str, int]] = None
) -> Dict:
    """
    Calcula IDOT personalizado para una ubicación usando pesos AHP del usuario

    Args:
        lat: Latitud
        lon: Longitud
        pesos: Dict con pesos AHP (salud, educacion, comercio, cultura, recreacion)
        conn: Conexión PostgreSQL
        radios: Dict con radios personalizados por categoría (metros)

    Returns:
        Dict con:
        - idot_personalizado: Score total (0-5)
        - scores_por_categoria: Scores individuales
        - dotaciones_cercanas: Número de dotaciones por categoría
        - pesos_aplicados: Pesos usados
    """
    if radios is None:
        # Radios por defecto
        radios = {
            'salud': 1000,
            'educacion': 800,
            'comercio': 1500,
            'cultura': 2000,
            'recreacion': 500
        }

    point_wkt = f"POINT({lon} {lat})"

    scores_categoria = {}
    conteos_categoria = {}

    # Calcular score por cada categoría general
    for cat_general, cat_especificas in CATEGORIA_MAPPING.items():
        radio = radios.get(cat_general, 1000)

        # Contar dotaciones de esta categoría
        count = await conn.fetchval("""
            SELECT COUNT(*)
            FROM iug.dotaciones_poi
            WHERE categoria = ANY($1)
              AND ST_DWithin(
                  geom::geography,
                  ST_SetSRID(ST_GeomFromText($2), 4326)::geography,
                  $3
              )
        """, cat_especificas, point_wkt, radio)

        conteos_categoria[cat_general] = count

        # Score simple basado en cantidad (normalizado a 0-5)
        # 0 dotaciones = 0, 5+ dotaciones = 5
        score = min(5.0, count * 1.0)  # Ajustar factor según necesidad
        scores_categoria[cat_general] = score

    # Calcular IDOT ponderado
    idot = 0.0
    total_peso = 0.0

    for cat, score in scores_categoria.items():
        peso = pesos.get(cat, 0.2)  # Default 0.2 si no está especificado
        idot += score * peso
        total_peso += peso

    # Normalizar si pesos no suman exactamente 1.0
    if total_peso > 0:
        idot /= total_peso

    return {
        'idot_personalizado': round(idot, 2),
        'scores_por_categoria': {k: round(v, 2) for k, v in scores_categoria.items()},
        'dotaciones_cercanas': conteos_categoria,
        'pesos_aplicados': pesos,
        'radios_usados': radios
    }


async def aplicar_pesos_personalizados(
    id_inmueble: int,
    pesos: Dict[str, float],
    conn: asyncpg.Connection
) -> Dict:
    """
    Recalcula IDOT para un inmueble existente con pesos personalizados

    Args:
        id_inmueble: ID del inmueble
        pesos: Pesos AHP personalizados
        conn: Conexión PostgreSQL

    Returns:
        Dict con IDOT nuevo y comparación con el original
    """
    # Obtener coordenadas del inmueble
    row = await conn.fetchrow("""
        SELECT
            ST_Y(geom) as lat,
            ST_X(geom) as lon,
            idot as idot_original
        FROM iug.inmueble
        WHERE id_inmueble = $1
    """, id_inmueble)

    if not row:
        raise ValueError(f"Inmueble {id_inmueble} no encontrado")

    # Calcular IDOT personalizado
    resultado = await calcular_pesos_dotaciones(
        lat=row['lat'],
        lon=row['lon'],
        pesos=pesos,
        conn=conn
    )

    # Comparar con original
    idot_original = float(row['idot_original']) if row['idot_original'] else None

    return {
        **resultado,
        'idot_original': idot_original,
        'diferencia': round(resultado['idot_personalizado'] - (idot_original or 0), 2),
        'id_inmueble': id_inmueble
    }


async def comparar_perfiles_ahp(
    lat: float,
    lon: float,
    conn: asyncpg.Connection
) -> Dict:
    """
    Compara IDOT usando diferentes perfiles de pesos AHP

    Args:
        lat: Latitud
        lon: Longitud
        conn: Conexión PostgreSQL

    Returns:
        Dict con IDOT calculado con diferentes perfiles
    """
    # Perfil 1: Pesos iguales
    perfil_equilibrado = {
        'salud': 0.20,
        'educacion': 0.20,
        'comercio': 0.20,
        'cultura': 0.20,
        'recreacion': 0.20
    }

    # Perfil 2: Prioridad salud y educación (familiar)
    perfil_familiar = {
        'salud': 0.30,
        'educacion': 0.30,
        'comercio': 0.15,
        'cultura': 0.10,
        'recreacion': 0.15
    }

    # Perfil 3: Prioridad comercio y cultura (urbano)
    perfil_urbano = {
        'salud': 0.15,
        'educacion': 0.10,
        'comercio': 0.30,
        'cultura': 0.30,
        'recreacion': 0.15
    }

    # Perfil 4: Prioridad recreación (deportivo)
    perfil_deportivo = {
        'salud': 0.20,
        'educacion': 0.10,
        'comercio': 0.15,
        'cultura': 0.10,
        'recreacion': 0.45
    }

    perfiles = {
        'equilibrado': perfil_equilibrado,
        'familiar': perfil_familiar,
        'urbano': perfil_urbano,
        'deportivo': perfil_deportivo
    }

    resultados = {}

    for nombre_perfil, pesos_perfil in perfiles.items():
        resultado = await calcular_pesos_dotaciones(lat, lon, pesos_perfil, conn)
        resultados[nombre_perfil] = resultado['idot_personalizado']

    return {
        'latitud': lat,
        'longitud': lon,
        'idot_por_perfil': resultados,
        'perfiles_disponibles': {
            'equilibrado': 'Todas las dotaciones tienen igual importancia',
            'familiar': 'Prioridad a salud y educación (ideal para familias)',
            'urbano': 'Prioridad a comercio y cultura (vida urbana activa)',
            'deportivo': 'Prioridad a recreación y deportes'
        }
    }
