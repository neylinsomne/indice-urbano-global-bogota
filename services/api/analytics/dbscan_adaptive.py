"""
Mejora #12: DBSCAN adaptativo con auto-tune de eps.

El DBSCAN actual usa eps=1.5 fijo. Pero la densidad optima varia
por grupo (ciudad, tipo_inmueble). Este modulo:

1. Calibra eps automaticamente via k-distance graph (Ester et al., 1996)
2. Compara con Isolation Forest (alternativa robusta para n>1000)
3. Reporta diferencias en outliers detectados

Referencia: Ester et al. (1996), Liu et al. (2008) para Isolation Forest.
"""
import logging
import math
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)


def k_distance_graph(X: np.ndarray, k: int = 4) -> dict:
    """
    Calcula la distancia al k-esimo vecino para cada punto.
    Encuentra el "codo" como eps optimo.

    Algoritmo:
    1. Para cada punto, calcular distancia al k-esimo vecino
    2. Ordenar las distancias
    3. Encontrar el codo (punto de maxima curvatura)
    4. Ese es el eps recomendado

    Heuristica para k: 2 * dim - 1 (Ester et al., 1996).
    Para 3 features (precio_m2, area, estrato), k=5.
    """
    from sklearn.neighbors import NearestNeighbors

    n = len(X)
    if n < k + 1:
        return {'error': f'n={n} insuficiente para k={k}'}

    nn = NearestNeighbors(n_neighbors=k + 1)
    nn.fit(X)
    distances, _ = nn.kneighbors(X)

    # k-th distance (excluyendo el self que es distancia 0)
    k_distances = distances[:, k]
    sorted_dists = np.sort(k_distances)

    # Encontrar codo: punto de maxima curvatura
    # Aproximacion: derivada segunda discreta
    if len(sorted_dists) < 3:
        eps_recomendado = float(np.median(sorted_dists))
    else:
        diffs1 = np.diff(sorted_dists)
        diffs2 = np.diff(diffs1)
        if len(diffs2) > 0:
            elbow_idx = np.argmax(diffs2) + 1
            eps_recomendado = float(sorted_dists[elbow_idx])
        else:
            eps_recomendado = float(np.median(sorted_dists))

    return {
        'k': k,
        'eps_recomendado': round(eps_recomendado, 4),
        'eps_p25': round(float(np.percentile(k_distances, 25)), 4),
        'eps_p50': round(float(np.percentile(k_distances, 50)), 4),
        'eps_p75': round(float(np.percentile(k_distances, 75)), 4),
        'eps_p95': round(float(np.percentile(k_distances, 95)), 4),
        'sorted_distances_sample': sorted_dists[::max(1, len(sorted_dists)//20)].tolist()[:20],
        'referencia': 'Ester, M. et al. (1996). KDD-96, pp. 226-231.',
    }


def dbscan_calibrado(X: np.ndarray, k: int = 5) -> dict:
    """
    Ejecuta DBSCAN con eps calibrado automaticamente.
    """
    from sklearn.cluster import DBSCAN

    calibration = k_distance_graph(X, k=k)
    if 'error' in calibration:
        return calibration

    eps = calibration['eps_recomendado']
    min_samples = k

    db = DBSCAN(eps=eps, min_samples=min_samples)
    labels = db.fit_predict(X)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_outliers = int((labels == -1).sum())

    return {
        'metodo': 'DBSCAN_adaptativo',
        'eps_usado': eps,
        'min_samples_usado': min_samples,
        'n_observaciones': len(X),
        'n_clusters_encontrados': n_clusters,
        'n_outliers_detectados': n_outliers,
        'pct_outliers': round(n_outliers / len(X) * 100, 2),
        'calibracion_k_distance': calibration,
    }


def isolation_forest_outliers(X: np.ndarray, contamination: float = 0.05) -> dict:
    """
    Isolation Forest como alternativa robusta a DBSCAN.

    Ventajas:
    - No requiere eps
    - Funciona en alta dimensionalidad
    - O(n log n) en tiempo

    Referencia: Liu, F. T., Ting, K. M., & Zhou, Z. H. (2008).
    """
    from sklearn.ensemble import IsolationForest

    if len(X) < 10:
        return {'error': f'n={len(X)} insuficiente'}

    iso = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100,
    )
    labels = iso.fit_predict(X)
    scores = iso.score_samples(X)

    n_outliers = int((labels == -1).sum())

    return {
        'metodo': 'IsolationForest',
        'contamination_esperada': contamination,
        'n_observaciones': len(X),
        'n_outliers_detectados': n_outliers,
        'pct_outliers': round(n_outliers / len(X) * 100, 2),
        'score_min': round(float(scores.min()), 4),
        'score_max': round(float(scores.max()), 4),
        'score_threshold_outlier': round(float(np.percentile(scores, contamination * 100)), 4),
        'referencia': 'Liu, F. T., Ting, K. M., & Zhou, Z. H. (2008). ICDM',
    }


async def comparar_metodos_outliers(
    conn: asyncpg.Connection,
    tipo_inmueble: str,
) -> dict:
    """
    Compara DBSCAN actual (eps fijo), DBSCAN calibrado e Isolation
    Forest sobre los inmuebles de un tipo.
    """
    rows = await conn.fetch("""
        SELECT id_inmueble,
               (precio / NULLIF(area_construida, 0)) AS precio_m2,
               area_construida,
               estrato,
               is_outlier
        FROM iug.inmueble
        WHERE tipo_inmueble = $1
          AND precio > 0 AND area_construida > 0
          AND estrato BETWEEN 1 AND 6
    """, tipo_inmueble)

    if len(rows) < 30:
        return {'error': f'n={len(rows)} insuficiente'}

    X_raw = np.array([[float(r['precio_m2']),
                       float(r['area_construida']),
                       float(r['estrato'])] for r in rows])

    # Outliers actuales (DBSCAN eps=1.5 fijo)
    outliers_actual = sum(1 for r in rows if r['is_outlier'])

    # Estandarizar para los nuevos metodos
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    return {
        'tipo_inmueble': tipo_inmueble,
        'n_observaciones': len(X),
        'metodos': {
            'dbscan_actual_v21': {
                'eps': 1.5,
                'min_samples': 5,
                'n_outliers': outliers_actual,
                'pct_outliers': round(outliers_actual / len(X) * 100, 2),
            },
            'dbscan_calibrado': dbscan_calibrado(X, k=5),
            'isolation_forest': isolation_forest_outliers(X, contamination=0.05),
        },
        'recomendacion': (
            'IsolationForest si n>1000. DBSCAN calibrado para '
            'datasets pequeños donde la densidad varia por grupo.'
        ),
    }
