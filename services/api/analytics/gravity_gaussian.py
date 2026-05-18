"""
Mejora #1: Funcion de gravedad gaussiana unificada.

Reemplaza las tres funciones de decaimiento incompatibles del sistema
actual (Manhattan lineal en I_ACC, inverso 1/d en I_DOT, lineal
euclidiano en I_SEG) por una unica funcion gaussiana:

    f(d) = exp(-d^2 / (2 * sigma^2))

donde sigma se calibra para que f(r) = 0.05 (5% utilidad residual
en el radio nominal):

    sigma = r / sqrt(2 * ln(20)) ~ r / 2.448

Justificacion: Fotheringham et al. (1989), Wilson (1971), datos EOD
Bogota 2019 (distribucion normal de viajes a pie con sigma~320m).

Este modulo NO modifica el pipeline. Calcula scores gaussianos para
una muestra y los compara con los scores actuales para evaluar
diferencias.
"""
import math
import logging
from typing import Optional
from dataclasses import dataclass, field

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)


# Radios calibrados (m) por capa, segun Tabla 'Parametros sigma' del .tex
RADIOS_DEFAULT = {
    'sitp': 800,
    'transmilenio': 1500,
    'metro': 1500,
    'cai': 800,
    'salud': 1000,
    'educacion': 1500,
    'abastecimiento': 800,
    'cultura': 2000,
    'recreacion': 1500,
}


def calibrar_sigma(radio_m: float, utilidad_residual: float = 0.05) -> float:
    """
    Calibra sigma para que f(radio) = utilidad_residual.

    f(r) = exp(-r^2 / (2*sigma^2)) = u
    => sigma = r / sqrt(2 * ln(1/u))

    Para u=0.05: sigma = r / 2.448
    """
    return radio_m / math.sqrt(2.0 * math.log(1.0 / utilidad_residual))


def gauss_decay(distancia_m: float, sigma_m: float) -> float:
    """f(d) = exp(-d^2 / (2*sigma^2))"""
    if distancia_m < 0:
        return 0.0
    return math.exp(-(distancia_m ** 2) / (2.0 * sigma_m ** 2))


def manhattan_decay(distancia_m: float, radio_m: float) -> float:
    """Funcion actual de I_ACC: max(0, 1 - d/r)"""
    return max(0.0, 1.0 - distancia_m / radio_m)


def inverso_decay(distancia_m: float, piso_m: float = 50.0) -> float:
    """Funcion actual de I_DOT: 1 / max(d, piso)"""
    return 1.0 / max(distancia_m, piso_m)


@dataclass
class GravityComparisonResult:
    """Resultado de comparar las 3 funciones para una capa."""
    capa: str
    radio_m: int
    sigma_m: float
    n_pois: int
    score_gaussiano: float
    score_manhattan: float
    score_inverso: float
    pois_dentro_radio: int
    pois_aporte_significativo: int  # Aporte > 0.01 al score gaussiano
    advertencias: list = field(default_factory=list)


async def calcular_score_gaussiano(
    conn: asyncpg.Connection,
    geom_inmueble_wkt: str,
    tabla_pois: str,
    radio_m: int,
    sigma_m: Optional[float] = None,
) -> dict:
    """
    Calcula score gaussiano para un inmueble usando una tabla de POIs.

    Args:
        conn: Conexion asyncpg
        geom_inmueble_wkt: Geometria WKT del inmueble (POINT)
        tabla_pois: 'iug.dotacion_salud', 'iug.osm_transport', etc.
        radio_m: Radio de busqueda (filtra POIs lejanos)
        sigma_m: Si None, se calibra desde radio_m

    Returns:
        {
            'score_gaussiano': float,
            'score_manhattan': float,
            'score_inverso': float,
            'n_pois': int,
            'distancias': [float, ...]
        }
    """
    if sigma_m is None:
        sigma_m = calibrar_sigma(radio_m)

    # Validar nombre de tabla (prevenir SQL injection)
    if not tabla_pois.replace('_', '').replace('.', '').isalnum():
        raise ValueError(f"Nombre de tabla invalido: {tabla_pois}")

    # Obtener distancias a TODOS los POIs dentro del radio
    schema, table = tabla_pois.split('.') if '.' in tabla_pois else ('iug', tabla_pois)
    query = f"""
        SELECT ST_Distance($1::geography, geom::geography) AS dist_m
        FROM {schema}.{table}
        WHERE geom IS NOT NULL
          AND ST_DWithin($1::geography, geom::geography, $2)
    """
    rows = await conn.fetch(query, geom_inmueble_wkt, radio_m)
    distancias = [float(r['dist_m']) for r in rows]

    if not distancias:
        return {
            'score_gaussiano': 0.0,
            'score_manhattan': 0.0,
            'score_inverso': 0.0,
            'n_pois': 0,
            'distancias': [],
        }

    score_gauss = sum(gauss_decay(d, sigma_m) for d in distancias)
    score_manh = sum(manhattan_decay(d, radio_m) for d in distancias)
    score_inv = sum(inverso_decay(d) for d in distancias)

    return {
        'score_gaussiano': round(score_gauss, 4),
        'score_manhattan': round(score_manh, 4),
        'score_inverso': round(score_inv, 4),
        'n_pois': len(distancias),
        'distancias': sorted(distancias)[:10],  # Top 10 mas cercanos
    }


async def comparar_funciones_inmueble(
    conn: asyncpg.Connection,
    id_inmueble: int,
    capas: Optional[dict] = None,
) -> dict:
    """
    Compara las 3 funciones de decaimiento para todas las capas
    relevantes de un inmueble.

    Returns:
        {
            'id_inmueble': int,
            'capas': {
                'sitp': GravityComparisonResult,
                ...
            },
            'resumen': {
                'score_gaussiano_total': float,
                'score_manhattan_total': float,
                'diferencia_relativa': float
            }
        }
    """
    if capas is None:
        # Capas a comparar: tabla -> radio
        capas = {
            'sitp': ('iug.osm_transport', 800),
            'cai': ('iug.cai_policia', 800),
            'salud': ('iug.dotacion_salud', 1000),
            'educacion': ('iug.dotacion_educacion', 1500),
            'recreacion': ('iug.dotacion_recreacion', 1500),
        }

    # Obtener geometria del inmueble
    row = await conn.fetchrow(
        "SELECT ST_AsText(geom) AS wkt FROM iug.inmueble WHERE id_inmueble = $1",
        id_inmueble,
    )
    if not row or not row['wkt']:
        raise ValueError(f"Inmueble {id_inmueble} sin geometria")

    geom_wkt = row['wkt']

    resultados = {}
    total_gauss = 0.0
    total_manh = 0.0

    for nombre_capa, (tabla, radio) in capas.items():
        try:
            r = await calcular_score_gaussiano(conn, geom_wkt, tabla, radio)
            sigma = calibrar_sigma(radio)
            resultados[nombre_capa] = {
                'capa': nombre_capa,
                'tabla': tabla,
                'radio_m': radio,
                'sigma_m': round(sigma, 1),
                **r,
            }
            total_gauss += r['score_gaussiano']
            total_manh += r['score_manhattan']
        except Exception as e:
            logger.warning(f"Error en capa {nombre_capa}: {e}")
            resultados[nombre_capa] = {'error': str(e)}

    diff_rel = ((total_gauss - total_manh) / total_manh * 100) if total_manh > 0 else 0.0

    return {
        'id_inmueble': id_inmueble,
        'metodologia': 'gaussiana_vs_actual',
        'referencia': 'Fotheringham et al. (1989); Wilson (1971)',
        'capas': resultados,
        'resumen': {
            'score_gaussiano_total': round(total_gauss, 4),
            'score_manhattan_actual_total': round(total_manh, 4),
            'diferencia_relativa_pct': round(diff_rel, 2),
            'interpretacion': (
                'Score gaussiano mayor que actual' if diff_rel > 5 else
                'Score gaussiano menor que actual' if diff_rel < -5 else
                'Scores similares (~5%)'
            ),
        },
    }


def tabla_calibracion_sigma() -> list:
    """Genera tabla de sigma calibrado para todos los radios estandar."""
    return [
        {
            'capa': capa,
            'radio_m': radio,
            'sigma_m': round(calibrar_sigma(radio), 1),
            'utilidad_en_radio': 0.05,
        }
        for capa, radio in RADIOS_DEFAULT.items()
    ]
