"""
Mejora #9: Normalizacion unificada (min-max global vs PERCENT_RANK).

Los subindices del IUG usan dos metodos de normalizacion:
- I_DIM, I_DOT, I_HED: PERCENT_RANK por tipo => uniforme [0,5]
- I_ACC, I_SEG: min-max por tipo
- I_PNU: escala directa 1-5

Mezclar estos metodos hace que los subindices uniformes contribuyan
mas varianza al IUG compuesto, sesgo independiente de los pesos.

Este modulo calcula y compara 3 esquemas de normalizacion:
1. Min-max global (recomendado para comparabilidad absoluta)
2. ECDF + transformacion gaussiana (preserva forma)
3. Min-max por tipo (actual de I_ACC, I_SEG)

Permite ver como cambian los rankings de inmuebles bajo cada esquema.
"""
import logging
from typing import Optional

import numpy as np
import asyncpg
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)

SUBINDICES = ['iacc', 'iseg', 'ihed', 'idot', 'ipnu']


def normalizar_minmax_global(X: np.ndarray) -> np.ndarray:
    """Min-max global a [0, 5]."""
    X_min = X.min(axis=0)
    X_max = X.max(axis=0)
    rango = X_max - X_min
    rango[rango < 1e-10] = 1.0
    return 5.0 * (X - X_min) / rango


def normalizar_ecdf_gaussiano(X: np.ndarray) -> np.ndarray:
    """
    Transformacion ECDF -> normal estandar -> escalar a [0,5].

    Mapea cualquier distribucion a una normal, util para mezclar
    indicadores de formas heterogeneas.
    """
    n, p = X.shape
    X_norm = np.zeros_like(X)

    for j in range(p):
        col = X[:, j]
        # ECDF: rank / (n+1) para evitar 0 y 1 exactos
        ranks = sp_stats.rankdata(col, method='average') / (n + 1)
        # Inversa normal estandar
        z = sp_stats.norm.ppf(ranks)
        # Escalar a [0, 5] via min-max
        z_min, z_max = z.min(), z.max()
        if z_max - z_min < 1e-10:
            X_norm[:, j] = 2.5
        else:
            X_norm[:, j] = 5.0 * (z - z_min) / (z_max - z_min)

    return X_norm


def normalizar_percent_rank_global(X: np.ndarray) -> np.ndarray:
    """PERCENT_RANK global (sin particionar por tipo)."""
    n, p = X.shape
    X_norm = np.zeros_like(X)
    for j in range(p):
        ranks = sp_stats.rankdata(X[:, j], method='average')
        X_norm[:, j] = 5.0 * (ranks - 1) / (n - 1)
    return X_norm


def comparar_distribuciones(X: np.ndarray, X_norm: np.ndarray, nombres: list) -> dict:
    """Compara estadisticos de las distribuciones original y normalizada."""
    return {
        nombre: {
            'original': {
                'min': round(float(X[:, i].min()), 3),
                'max': round(float(X[:, i].max()), 3),
                'mean': round(float(X[:, i].mean()), 3),
                'std': round(float(X[:, i].std()), 3),
                'skewness': round(float(sp_stats.skew(X[:, i])), 3),
            },
            'normalizado': {
                'min': round(float(X_norm[:, i].min()), 3),
                'max': round(float(X_norm[:, i].max()), 3),
                'mean': round(float(X_norm[:, i].mean()), 3),
                'std': round(float(X_norm[:, i].std()), 3),
                'skewness': round(float(sp_stats.skew(X_norm[:, i])), 3),
            },
        }
        for i, nombre in enumerate(nombres)
    }


async def comparar_esquemas_normalizacion(
    conn: asyncpg.Connection,
    tipo_inmueble: Optional[str] = None,
) -> dict:
    """
    Compara los 3 esquemas y reporta:
    - Distribuciones resultantes
    - IURB calculado bajo cada esquema
    - Spearman entre rankings (estabilidad)
    """
    where = ["is_outlier = FALSE",
             "iacc IS NOT NULL", "iseg IS NOT NULL",
             "ihed IS NOT NULL", "idot IS NOT NULL", "ipnu IS NOT NULL"]
    params = []
    if tipo_inmueble:
        where.append("tipo_inmueble = $1")
        params.append(tipo_inmueble)
    else:
        where.append("tipo_inmueble IN ('Apartamento', 'Casa')")

    rows = await conn.fetch(
        f"SELECT id_inmueble, iacc, iseg, ihed, idot, ipnu, iurb "
        f"FROM iug.inmueble WHERE {' AND '.join(where)}",
        *params,
    )
    if len(rows) < 30:
        return {'error': f'n={len(rows)} insuficiente'}

    ids = [r['id_inmueble'] for r in rows]
    X = np.array([[float(r[s]) for s in SUBINDICES] for r in rows])
    iurb_actual = np.array([float(r['iurb']) for r in rows])

    # Aplicar 3 esquemas
    X_minmax = normalizar_minmax_global(X)
    X_ecdf = normalizar_ecdf_gaussiano(X)
    X_pr = normalizar_percent_rank_global(X)

    # IURB con pesos uniformes
    iurb_minmax = X_minmax.mean(axis=1)
    iurb_ecdf = X_ecdf.mean(axis=1)
    iurb_pr = X_pr.mean(axis=1)

    # Rankings: rho de Spearman
    rho_actual_minmax, _ = sp_stats.spearmanr(iurb_actual, iurb_minmax)
    rho_actual_ecdf, _ = sp_stats.spearmanr(iurb_actual, iurb_ecdf)
    rho_actual_pr, _ = sp_stats.spearmanr(iurb_actual, iurb_pr)
    rho_minmax_ecdf, _ = sp_stats.spearmanr(iurb_minmax, iurb_ecdf)

    # Top 10 inmuebles bajo cada esquema (cuantos coinciden)
    top10_actual = set(np.argsort(-iurb_actual)[:10])
    top10_minmax = set(np.argsort(-iurb_minmax)[:10])
    top10_ecdf = set(np.argsort(-iurb_ecdf)[:10])
    top10_pr = set(np.argsort(-iurb_pr)[:10])

    return {
        'tipo_inmueble': tipo_inmueble or 'vivienda (Apto + Casa)',
        'n_observaciones': len(rows),
        'esquemas': {
            'min_max_global': {
                'descripcion': 'min-max global a [0, 5]',
                'distribuciones': comparar_distribuciones(X, X_minmax, SUBINDICES),
                'iurb_promedio': round(float(iurb_minmax.mean()), 3),
                'iurb_std': round(float(iurb_minmax.std()), 3),
            },
            'ecdf_gaussiano': {
                'descripcion': 'ECDF -> N(0,1) -> [0, 5]. Preserva forma.',
                'distribuciones': comparar_distribuciones(X, X_ecdf, SUBINDICES),
                'iurb_promedio': round(float(iurb_ecdf.mean()), 3),
                'iurb_std': round(float(iurb_ecdf.std()), 3),
            },
            'percent_rank_global': {
                'descripcion': 'PERCENT_RANK global (sin tipo). Uniforme.',
                'distribuciones': comparar_distribuciones(X, X_pr, SUBINDICES),
                'iurb_promedio': round(float(iurb_pr.mean()), 3),
                'iurb_std': round(float(iurb_pr.std()), 3),
            },
        },
        'estabilidad_rankings': {
            'spearman_actual_vs_minmax': round(float(rho_actual_minmax), 4),
            'spearman_actual_vs_ecdf': round(float(rho_actual_ecdf), 4),
            'spearman_actual_vs_pr': round(float(rho_actual_pr), 4),
            'spearman_minmax_vs_ecdf': round(float(rho_minmax_ecdf), 4),
        },
        'top10_overlap': {
            'actual_vs_minmax': len(top10_actual & top10_minmax),
            'actual_vs_ecdf': len(top10_actual & top10_ecdf),
            'actual_vs_pr': len(top10_actual & top10_pr),
            'minmax_vs_ecdf': len(top10_minmax & top10_ecdf),
        },
        'recomendacion': (
            'Si rho_actual_vs_minmax > 0.95: cambio seguro (preserva rankings). '
            'Si < 0.85: el esquema actual y min-max producen ordenamientos '
            'sustancialmente distintos; revisar antes de migrar.'
        ),
    }
