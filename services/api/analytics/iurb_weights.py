"""
Mejora #10: Pesos empiricos del IUG via correlacion con precios.

Los pesos actuales del IUG son fijos en 20% cada uno (V115). Esta es
una eleccion arbitraria. La OECD Handbook on Composite Indicators
(2008) recomienda derivar pesos endogenamente:

    w_k = |Corr(I_k, ln(P/m^2))| / sum_j |Corr(I_j, ln(P/m^2))|

Asi, los indicadores que mas explican la varianza de precios reciben
mas peso.

Tres metodos implementados:
1. correlation_weights: Correlacion absoluta normalizada
2. regression_weights: Coeficientes estandarizados de regresion
3. pca_weights: Loadings del primer componente principal

Este modulo NO modifica el calculo del IUG. Calcula y compara los
pesos teoricos para evaluacion.

Referencia: OECD/EU/JRC (2008), Capitulo 6, "Weighting".
"""
import logging
import math
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)


SUBINDICES = ['iacc', 'iseg', 'ihed', 'idot', 'ipnu']


async def _fetch_data(
    conn: asyncpg.Connection,
    tipo_inmueble: Optional[str] = None,
) -> tuple:
    """Obtiene matriz de subindices y target log-precio."""
    where = ["is_outlier = FALSE",
             "precio > 0", "area_construida > 0",
             "iacc IS NOT NULL", "iseg IS NOT NULL",
             "ihed IS NOT NULL", "idot IS NOT NULL", "ipnu IS NOT NULL"]
    params = []

    if tipo_inmueble:
        where.append("tipo_inmueble = $1")
        params.append(tipo_inmueble)
    else:
        where.append("tipo_inmueble IN ('Apartamento', 'Casa')")

    query = f"""
        SELECT iacc, iseg, ihed, idot, ipnu, precio, area_construida
        FROM iug.inmueble
        WHERE {' AND '.join(where)}
    """
    rows = await conn.fetch(query, *params)

    if len(rows) < 30:
        return None, None, len(rows)

    X = np.array([[float(r[s]) for s in SUBINDICES] for r in rows])
    y = np.array([math.log(float(r['precio']) / float(r['area_construida']))
                  for r in rows])
    return X, y, len(rows)


def correlation_weights(X: np.ndarray, y: np.ndarray) -> dict:
    """
    Pesos por correlacion absoluta con precio.

    w_k = |corr(I_k, y)| / sum |corr(I_j, y)|
    """
    correlations = {}
    for i, name in enumerate(SUBINDICES):
        x_i = X[:, i]
        if np.std(x_i) < 1e-10:
            correlations[name] = 0.0
        else:
            correlations[name] = abs(float(np.corrcoef(x_i, y)[0, 1]))

    total = sum(correlations.values())
    if total < 1e-10:
        weights = {k: 1.0 / len(SUBINDICES) for k in SUBINDICES}
    else:
        weights = {k: round(v / total, 4) for k, v in correlations.items()}

    return {
        'metodo': 'correlation_weights',
        'pesos': weights,
        'correlaciones_absolutas': {k: round(v, 4) for k, v in correlations.items()},
        'referencia': 'OECD Handbook (2008), Cap 6.1',
    }


def regression_weights(X: np.ndarray, y: np.ndarray) -> dict:
    """
    Pesos por coeficientes estandarizados de regresion.

    Modelo: y = sum(beta_k * I_k_estandarizado) + e
    w_k = |beta_k| / sum |beta_j|

    Diferencia con correlation: aisla el efecto controlando por las
    otras variables.
    """
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)
    y_std = (y - y.mean()) / (y.std() + 1e-10)

    model = LinearRegression().fit(X_std, y_std)
    coefs = model.coef_

    abs_coefs = np.abs(coefs)
    total = abs_coefs.sum()
    if total < 1e-10:
        weights = {k: 1.0 / len(SUBINDICES) for k in SUBINDICES}
    else:
        weights = {SUBINDICES[i]: round(float(abs_coefs[i] / total), 4)
                   for i in range(len(SUBINDICES))}

    return {
        'metodo': 'regression_weights',
        'pesos': weights,
        'coeficientes_estandarizados': {
            SUBINDICES[i]: round(float(coefs[i]), 4)
            for i in range(len(SUBINDICES))
        },
        'r2': round(float(model.score(X_std, y_std)), 4),
        'referencia': 'OECD Handbook (2008), Cap 6.3',
    }


def pca_weights(X: np.ndarray, y: np.ndarray) -> dict:
    """
    Pesos por loadings del primer componente principal.

    Asume que el PC1 captura la 'calidad urbana general'. Sus
    loadings son los pesos.

    Nota: NO usa el precio. Es endogeno a la estructura de los
    indicadores.
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)

    pca = PCA(n_components=2)
    pca.fit(X_std)

    loadings = pca.components_[0]
    abs_loadings = np.abs(loadings)
    total = abs_loadings.sum()

    weights = {SUBINDICES[i]: round(float(abs_loadings[i] / total), 4)
               for i in range(len(SUBINDICES))}

    return {
        'metodo': 'pca_weights',
        'pesos': weights,
        'loadings_pc1': {SUBINDICES[i]: round(float(loadings[i]), 4)
                         for i in range(len(SUBINDICES))},
        'varianza_explicada_pc1': round(float(pca.explained_variance_ratio_[0]), 4),
        'varianza_explicada_pc2': round(float(pca.explained_variance_ratio_[1]), 4),
        'referencia': 'OECD Handbook (2008), Cap 6.2',
    }


def benefit_of_doubt_weights(X: np.ndarray) -> dict:
    """
    Pesos Benefit-of-the-Doubt (BOD): cada inmueble recibe los
    pesos que MAXIMIZAN su propio score, sujeto a:
    - w_k >= 0.05
    - sum(w_k) = 1

    Para reportar pesos agregados, se promedian los pesos optimos
    de los 100 inmuebles con mayor score.

    Referencia: Cherchye et al. (2007), OECD Handbook (2008).
    """
    n, p = X.shape
    if n == 0:
        return {'error': 'sin datos'}

    # Min-max normalizar para que todos los I_k esten en [0, 1]
    X_norm = (X - X.min(axis=0)) / (X.max(axis=0) - X.min(axis=0) + 1e-10)

    # Para cada inmueble, encontrar el I_k mas alto (proxy de BOD)
    # BOD asigna mas peso a la dimension donde el inmueble destaca.
    # Aproximacion simple: peso proporcional al ranking del inmueble
    # en cada dimension.
    rankings = np.argsort(np.argsort(-X_norm, axis=0), axis=0) / n
    # Los inmuebles top-100 por iurb actual (suma uniforme):
    iurb_uniforme = X_norm.sum(axis=1)
    top_idx = np.argsort(-iurb_uniforme)[:min(100, n)]

    # Pesos promedio del top-100: cada uno ponderado por su ranking
    # invertido (mejor ranking => mas peso)
    weights_per_inmueble = (1 - rankings[top_idx])
    weights_per_inmueble /= weights_per_inmueble.sum(axis=1, keepdims=True)
    avg_weights = weights_per_inmueble.mean(axis=0)
    avg_weights /= avg_weights.sum()

    return {
        'metodo': 'benefit_of_doubt',
        'pesos': {SUBINDICES[i]: round(float(avg_weights[i]), 4)
                  for i in range(len(SUBINDICES))},
        'n_top_inmuebles_usados': len(top_idx),
        'nota': 'Pesos promedio de los top-100 inmuebles. BOD '
                'real es por-inmueble, esto es agregado.',
        'referencia': 'Cherchye et al. (2007); OECD Handbook (2008)',
    }


async def comparar_pesos_iurb(
    conn: asyncpg.Connection,
    tipo_inmueble: Optional[str] = None,
) -> dict:
    """
    Compara los 4 metodos de derivacion de pesos contra los
    pesos uniformes actuales (0.20 c/u).

    Returns:
        {
            'pesos_actuales': {iacc: 0.2, ...},
            'pesos_correlation': {...},
            'pesos_regression': {...},
            'pesos_pca': {...},
            'pesos_bod': {...},
            'comparacion_iurb_promedio': {...}
        }
    """
    X, y, n = await _fetch_data(conn, tipo_inmueble)
    if X is None:
        return {'error': f'Insuficientes datos: n={n} (min 30)'}

    pesos_actuales = {k: 0.20 for k in SUBINDICES}

    corr = correlation_weights(X, y)
    reg = regression_weights(X, y)
    pca = pca_weights(X, y)
    bod = benefit_of_doubt_weights(X)

    # Comparar IUG promedio bajo cada esquema
    iurb_actual = (X * 0.20).sum(axis=1).mean()
    iurb_corr = sum(X[:, i] * corr['pesos'][SUBINDICES[i]]
                    for i in range(len(SUBINDICES))).mean()
    iurb_reg = sum(X[:, i] * reg['pesos'][SUBINDICES[i]]
                   for i in range(len(SUBINDICES))).mean()
    iurb_pca = sum(X[:, i] * pca['pesos'][SUBINDICES[i]]
                   for i in range(len(SUBINDICES))).mean()
    iurb_bod = sum(X[:, i] * bod['pesos'][SUBINDICES[i]]
                   for i in range(len(SUBINDICES))).mean()

    return {
        'tipo_inmueble': tipo_inmueble or 'vivienda (Apto + Casa)',
        'n_observaciones': n,
        'pesos_actuales_v115': pesos_actuales,
        'metodos': {
            'correlation': corr,
            'regression': reg,
            'pca': pca,
            'benefit_of_doubt': bod,
        },
        'iurb_promedio_por_metodo': {
            'actual_uniforme': round(float(iurb_actual), 3),
            'correlation': round(float(iurb_corr), 3),
            'regression': round(float(iurb_reg), 3),
            'pca': round(float(iurb_pca), 3),
            'benefit_of_doubt': round(float(iurb_bod), 3),
        },
        'recomendacion': _recomendar_metodo_pesos(corr, reg, pca, bod),
    }


def _recomendar_metodo_pesos(corr, reg, pca, bod) -> str:
    """Sugerencia textual del mejor metodo segun caracteristicas."""
    r2_reg = reg.get('r2', 0)
    var_pc1 = pca.get('varianza_explicada_pc1', 0)

    if r2_reg > 0.5:
        return ('Recomendado: regression_weights. '
                f'R^2 = {r2_reg:.2f} indica que los subindices explican '
                'bien el precio.')
    elif var_pc1 > 0.6:
        return ('Recomendado: pca_weights. '
                f'PC1 explica {var_pc1:.1%} de la varianza, indicando '
                'una dimension dominante de calidad urbana.')
    else:
        return ('Recomendado: benefit_of_doubt. '
                'No hay un metodo claro; BOD permite que cada inmueble '
                'sea evaluado en su mejor dimension.')
