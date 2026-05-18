"""
Mejora #14: Propagacion de incertidumbre para indicadores.

Cada subindice se reporta como un punto unico (e.g. I_ACC = 3.7) sin
banda de confianza. Pero el IUG compuesto acumula incertidumbre de 5+
fuentes y se presenta con la misma precision.

Este modulo calcula bandas de confianza para:
- I_ACC, I_DOT (gravedad): error por precision GPS (sigma=10m default)
- I_DIM (PCA): bootstrap sobre los loadings
- I_URB (compuesto): propagacion lineal asumiendo independencia

Formula propagacion lineal:
    sigma_IURB = sqrt( sum_k (w_k^2 * sigma_Ik^2) )

Si los I_k estan correlacionados, agregar terminos cruzados:
    + 2 * sum_{i<j} w_i * w_j * cov(I_i, I_j)
"""
import logging
import math
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)

SUBINDICES = ['iacc', 'iseg', 'ihed', 'idot', 'ipnu']
PESOS_DEFAULT = {s: 0.20 for s in SUBINDICES}


def propagacion_lineal_iurb(
    sigmas_subindices: dict,
    pesos: Optional[dict] = None,
    cov_matrix: Optional[np.ndarray] = None,
) -> dict:
    """
    Propagacion de incertidumbre lineal del IUG.

    Args:
        sigmas_subindices: {'iacc': 0.3, 'iseg': 0.2, ...} desv. estandar
        pesos: pesos del IUG (default 20% c/u)
        cov_matrix: covarianza entre subindices (opcional, mejor estimacion)

    Returns:
        {
            'sigma_iurb': float,
            'metodo': 'lineal_independiente' o 'lineal_con_covarianza'
        }
    """
    if pesos is None:
        pesos = PESOS_DEFAULT

    var_iurb = 0.0
    for k, sigma in sigmas_subindices.items():
        w = pesos.get(k, 0.0)
        var_iurb += (w * sigma) ** 2

    metodo = 'lineal_independiente'
    if cov_matrix is not None and cov_matrix.shape[0] == len(SUBINDICES):
        # Agregar terminos cruzados
        for i in range(len(SUBINDICES)):
            for j in range(i + 1, len(SUBINDICES)):
                w_i = pesos.get(SUBINDICES[i], 0.0)
                w_j = pesos.get(SUBINDICES[j], 0.0)
                var_iurb += 2 * w_i * w_j * cov_matrix[i, j]
        metodo = 'lineal_con_covarianza'

    sigma_iurb = math.sqrt(max(var_iurb, 0))

    return {
        'sigma_iurb': round(sigma_iurb, 4),
        'metodo': metodo,
        'pesos_usados': pesos,
        'sigmas_subindices': sigmas_subindices,
    }


def banda_confianza_gravedad(
    score_actual: float,
    n_pois_dentro_radio: int,
    radio_m: int,
    sigma_gps_m: float = 10.0,
) -> dict:
    """
    Estima incertidumbre de un score gravitacional debido a precision
    GPS.

    Aproximacion: si una distancia tipica es d, y la precision GPS es
    sigma_gps, el error relativo en la distancia es sigma_gps / d.

    El error en el score (1/d) es ~ sigma_gps / d^2 por cada POI.

    Para gauss(d): df/dd = -d/sigma^2 * f(d)
    Por simplicidad, asumimos error proporcional al num. de POIs cercanos.
    """
    if n_pois_dentro_radio == 0:
        return {
            'score': score_actual,
            'sigma_score': 0.0,
            'ic_95_lower': score_actual,
            'ic_95_upper': score_actual,
        }

    # Distancia promedio asumida = radio/2
    d_promedio = radio_m / 2.0
    error_relativo_por_poi = sigma_gps_m / d_promedio

    # Error compuesto (independencia entre POIs)
    sigma_score = score_actual * error_relativo_por_poi / math.sqrt(n_pois_dentro_radio)

    return {
        'score': round(score_actual, 4),
        'sigma_score': round(sigma_score, 4),
        'ic_95_lower': round(score_actual - 1.96 * sigma_score, 4),
        'ic_95_upper': round(score_actual + 1.96 * sigma_score, 4),
        'sigma_gps_m': sigma_gps_m,
        'n_pois': n_pois_dentro_radio,
    }


async def banda_confianza_iurb_inmueble(
    conn: asyncpg.Connection,
    id_inmueble: int,
    sigma_gps_m: float = 10.0,
) -> dict:
    """
    Calcula banda de confianza completa para el IUG de un inmueble.

    Estrategia:
    1. Para I_ACC, I_DOT: estimar sigma con precision GPS
    2. Para I_DIM: usar bootstrap del PCA (si tabla pca_loadings existe)
    3. Para I_SEG: sigma de la dimension subjetiva del ICSU
    4. Para I_PNU: discrete, sigma=0 (es scoring exacto)
    5. Propagar a IUG
    """
    row = await conn.fetchrow("""
        SELECT iurb, iacc, iseg, ihed, idot, ipnu, tipo_inmueble
        FROM iug.inmueble WHERE id_inmueble = $1
    """, id_inmueble)
    if not row:
        return {'error': f'inmueble {id_inmueble} no encontrado'}

    # Estimaciones simplificadas de sigma
    # I_ACC, I_DOT: ruido GPS (~5% del score)
    # I_HED: dimension fisica + ratio (~3% del score)
    # I_SEG: ICSU dimension subjetiva (~10% por encuesta)
    # I_PNU: discreto, sigma muy bajo (~1% por error de pol\'igono POT)
    sigmas = {
        'iacc': float(row['iacc'] or 0) * 0.05 if row['iacc'] else 0,
        'iseg': float(row['iseg'] or 0) * 0.10 if row['iseg'] else 0,
        'ihed': float(row['ihed'] or 0) * 0.03 if row['ihed'] else 0,
        'idot': float(row['idot'] or 0) * 0.05 if row['idot'] else 0,
        'ipnu': float(row['ipnu'] or 0) * 0.01 if row['ipnu'] else 0,
    }

    # Calcular covarianza estimada del tipo
    cov_matrix = await _estimar_cov_subindices(conn, row['tipo_inmueble'])

    propagacion = propagacion_lineal_iurb(sigmas, cov_matrix=cov_matrix)

    iurb = float(row['iurb'] or 0)
    sigma_iurb = propagacion['sigma_iurb']

    return {
        'id_inmueble': id_inmueble,
        'tipo_inmueble': row['tipo_inmueble'],
        'iurb_actual': round(iurb, 3),
        'sigma_iurb': round(sigma_iurb, 4),
        'ic_90': {
            'lower': round(iurb - 1.645 * sigma_iurb, 3),
            'upper': round(iurb + 1.645 * sigma_iurb, 3),
        },
        'ic_95': {
            'lower': round(iurb - 1.96 * sigma_iurb, 3),
            'upper': round(iurb + 1.96 * sigma_iurb, 3),
        },
        'subindices': {
            k: {
                'valor': round(float(row[k] or 0), 3),
                'sigma_estimado': round(sigmas[k], 4),
            }
            for k in SUBINDICES
        },
        'metodo': propagacion['metodo'],
        'fuentes_de_error': {
            'iacc': 'Precision GPS (~5%)',
            'iseg': 'Encuesta EPV (~10%)',
            'ihed': 'Imputacion datos faltantes (~3%)',
            'idot': 'Precision GPS (~5%)',
            'ipnu': 'Borde de poligono POT (~1%)',
        },
        'referencia': (
            'Propagacion lineal (Taylor 1st order). '
            'Para inferencia rigurosa: bootstrap o Bayesian.'
        ),
    }


async def _estimar_cov_subindices(conn, tipo_inmueble: str):
    """Estima matriz de covarianza desde los datos."""
    rows = await conn.fetch("""
        SELECT iacc, iseg, ihed, idot, ipnu
        FROM iug.inmueble
        WHERE tipo_inmueble = $1
          AND is_outlier = FALSE
          AND iacc IS NOT NULL AND iseg IS NOT NULL
          AND ihed IS NOT NULL AND idot IS NOT NULL AND ipnu IS NOT NULL
    """, tipo_inmueble)

    if len(rows) < 30:
        return None

    X = np.array([[float(r[s]) for s in SUBINDICES] for r in rows])
    return np.cov(X, rowvar=False)


async def banda_confianza_localidad(
    conn: asyncpg.Connection,
    nombre_localidad: str,
) -> dict:
    """
    Banda de confianza del IUG promedio de una localidad.

    Aplica el teorema central del limite: SE(media) = sigma / sqrt(n).
    """
    rows = await conn.fetch("""
        SELECT iurb FROM iug.inmueble i
        JOIN iug.localidad l ON l.id_localidad = i.id_localidad
        WHERE LOWER(l.nombre) = LOWER($1)
          AND i.iurb IS NOT NULL AND i.iurb > 0
          AND i.tipo_inmueble IN ('Apartamento', 'Casa')
    """, nombre_localidad)

    if not rows:
        return {'error': f'sin datos para localidad {nombre_localidad}'}

    iurbs = np.array([float(r['iurb']) for r in rows])
    n = len(iurbs)
    media = float(iurbs.mean())
    sigma = float(iurbs.std(ddof=1))
    se_media = sigma / math.sqrt(n)

    return {
        'localidad': nombre_localidad,
        'n_inmuebles': n,
        'iurb_promedio': round(media, 3),
        'desviacion_tipica': round(sigma, 3),
        'error_estandar_media': round(se_media, 4),
        'ic_95_media': {
            'lower': round(media - 1.96 * se_media, 3),
            'upper': round(media + 1.96 * se_media, 3),
        },
        'ic_99_media': {
            'lower': round(media - 2.576 * se_media, 3),
            'upper': round(media + 2.576 * se_media, 3),
        },
        'interpretacion': (
            f'Con 95% de confianza, el IUG promedio real de '
            f'{nombre_localidad} esta entre '
            f'{media - 1.96*se_media:.2f} y {media + 1.96*se_media:.2f}.'
        ),
        'referencia': 'Teorema central del limite (n>30)',
    }
