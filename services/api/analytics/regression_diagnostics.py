"""
Mejora #4: Diagnosticos de regresion (VIF + Moran I + residuos).

El modelo hedonico actual reporta R^2 y CV-RMSE pero no:
- VIF (Variance Inflation Factor) para detectar multicolinealidad
- I de Moran sobre residuos para detectar autocorrelacion espacial
- Tests de normalidad de residuos (Shapiro-Wilk)
- Heterocedasticidad (Breusch-Pagan)

Este modulo calcula esos diagnosticos sobre el modelo entrenado
sin re-entrenar nada.

Referencias:
- Anselin (1995) para I de Moran local
- Anselin & Bera (1998) para VIF en regresion espacial
"""
import logging
import math
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)


def compute_vif(X: np.ndarray, feature_names: list) -> dict:
    """
    Variance Inflation Factor por feature.

    VIF_i = 1 / (1 - R^2_i) donde R^2_i es el R^2 de regresar
    feature_i contra todas las demas.

    Interpretacion:
        VIF < 5: Aceptable
        VIF 5-10: Moderado
        VIF > 10: Multicolinealidad severa, eliminar o combinar

    Returns:
        {feature: {'vif': float, 'severity': str}}
    """
    from sklearn.linear_model import LinearRegression

    n, p = X.shape
    if p < 2:
        return {feature_names[0]: {'vif': 1.0, 'severity': 'ninguno'}}

    result = {}
    for i, name in enumerate(feature_names):
        X_other = np.delete(X, i, axis=1)
        X_target = X[:, i]
        try:
            reg = LinearRegression().fit(X_other, X_target)
            r2 = reg.score(X_other, X_target)
            vif = 1.0 / max(1.0 - r2, 1e-10)

            if vif < 5:
                severity = 'aceptable'
            elif vif < 10:
                severity = 'moderado'
            else:
                severity = 'severo'

            result[name] = {
                'vif': round(float(vif), 3),
                'r2_against_others': round(float(r2), 4),
                'severity': severity,
            }
        except Exception as e:
            result[name] = {'vif': None, 'error': str(e)}

    return result


def moran_i_residuos(
    residuos: np.ndarray,
    coordenadas: np.ndarray,
    k_vecinos: int = 5,
) -> dict:
    """
    I de Moran sobre los residuos del modelo.

    H0: residuos espacialmente independientes (no autocorrelacion).
    Si I significativamente positivo => modelo esta dejando varianza
    espacial sin capturar => considerar GWR o Spatial Lag Model.

    Args:
        residuos: vector de residuos del modelo (n,)
        coordenadas: matriz (n, 2) con [lat, lon]
        k_vecinos: numero de vecinos en la matriz de pesos

    Returns:
        {
            'I': float,
            'expected_I': float,
            'variance': float,
            'z_score': float,
            'p_value': float,
            'interpretation': str,
        }
    """
    from sklearn.neighbors import NearestNeighbors
    from scipy import stats as sp_stats

    n = len(residuos)
    if n < 10:
        return {'error': f'n={n} insuficiente (min 10)'}

    # Matriz de pesos espaciales W (k-vecinos mas cercanos, fila-normalizada)
    knn = NearestNeighbors(n_neighbors=k_vecinos + 1)
    knn.fit(coordenadas)
    distances, indices = knn.kneighbors(coordenadas)

    # Construir W (densa para n pequeño)
    W = np.zeros((n, n))
    for i in range(n):
        for j_idx in range(1, k_vecinos + 1):  # excluir self
            j = indices[i, j_idx]
            W[i, j] = 1.0 / k_vecinos  # fila-normalizada

    # I de Moran
    z = residuos - residuos.mean()
    sum_W = W.sum()

    numerator = sum(W[i, j] * z[i] * z[j]
                    for i in range(n)
                    for j in range(n)
                    if W[i, j] > 0)
    denominator = (z ** 2).sum()

    if denominator < 1e-10 or sum_W < 1e-10:
        return {'error': 'varianza nula en residuos'}

    I = (n / sum_W) * (numerator / denominator)
    E_I = -1.0 / (n - 1)

    # Varianza bajo H0 (aproximacion para muestras grandes)
    S0 = sum_W
    S1 = 0.5 * sum((W[i, j] + W[j, i]) ** 2
                   for i in range(n)
                   for j in range(n))
    S2 = sum((W[i, :].sum() + W[:, i].sum()) ** 2 for i in range(n))

    var_I = ((n ** 2 * S1 - n * S2 + 3 * S0 ** 2) /
             ((n - 1) * (n + 1) * S0 ** 2)) - E_I ** 2

    z_score = (I - E_I) / math.sqrt(max(var_I, 1e-10))
    p_value = 2 * (1 - sp_stats.norm.cdf(abs(z_score)))

    if p_value < 0.05:
        if I > E_I:
            interp = 'Autocorrelacion espacial POSITIVA significativa. Considerar SLM/GWR.'
        else:
            interp = 'Autocorrelacion espacial NEGATIVA significativa (raro).'
    else:
        interp = 'Sin autocorrelacion espacial significativa. Modelo OLS adecuado.'

    return {
        'I_moran': round(float(I), 4),
        'expected_I': round(float(E_I), 4),
        'variance': round(float(var_I), 6),
        'z_score': round(float(z_score), 3),
        'p_value': round(float(p_value), 6),
        'interpretation': interp,
        'n': n,
        'k_vecinos': k_vecinos,
    }


def shapiro_wilk_residuos(residuos: np.ndarray) -> dict:
    """
    Test de normalidad de Shapiro-Wilk.

    H0: residuos normalmente distribuidos.
    Si p < 0.05: rechazar normalidad. Considerar transformaciones.
    """
    from scipy import stats as sp_stats

    if len(residuos) < 3:
        return {'error': 'n < 3 insuficiente'}
    if len(residuos) > 5000:
        # Shapiro no es confiable con n>5000. Usar D'Agostino.
        stat, p = sp_stats.normaltest(residuos)
        test_name = 'DAgostino-Pearson'
    else:
        stat, p = sp_stats.shapiro(residuos)
        test_name = 'Shapiro-Wilk'

    return {
        'test': test_name,
        'statistic': round(float(stat), 4),
        'p_value': round(float(p), 6),
        'normal': bool(p > 0.05),
        'interpretation': (
            'Residuos NORMALES (p>0.05)' if p > 0.05
            else 'Residuos NO normales (p<0.05). Considerar Box-Cox o robusto.'
        ),
    }


def breusch_pagan_residuos(residuos: np.ndarray, X: np.ndarray) -> dict:
    """
    Test de heterocedasticidad de Breusch-Pagan.

    H0: varianza de residuos es constante (homocedasticidad).
    Si p < 0.05: heterocedasticidad presente. Usar errores robustos.
    """
    from sklearn.linear_model import LinearRegression
    from scipy import stats as sp_stats

    n = len(residuos)
    if n < 10 or X.shape[1] < 1:
        return {'error': 'datos insuficientes'}

    # Regresion auxiliar: residuos^2 ~ X
    reg = LinearRegression().fit(X, residuos ** 2)
    r2 = reg.score(X, residuos ** 2)

    # Estadistico LM = n * R^2_aux ~ chi^2(p)
    lm_stat = n * r2
    df = X.shape[1]
    p_value = 1 - sp_stats.chi2.cdf(lm_stat, df)

    return {
        'test': 'Breusch-Pagan',
        'lm_statistic': round(float(lm_stat), 4),
        'df': df,
        'p_value': round(float(p_value), 6),
        'homocedastico': bool(p_value > 0.05),
        'interpretation': (
            'Homocedasticidad OK (p>0.05)' if p_value > 0.05
            else 'HETEROCEDASTICIDAD detectada. Usar errores estandar robustos (HC3).'
        ),
    }


async def diagnostico_completo_tipo(
    conn: asyncpg.Connection,
    tipo_inmueble: str,
) -> dict:
    """
    Ejecuta los 4 diagnosticos sobre los datos del modelo activo
    para un tipo de inmueble.
    """
    # Obtener features y target del tipo
    rows = await conn.fetch("""
        SELECT id_inmueble,
               area_construida, habitaciones, banos, garajes, estrato,
               iacc, iseg, ihed, ipnu, idot,
               precio,
               ST_Y(geom) AS lat, ST_X(geom) AS lon
        FROM iug.inmueble
        WHERE tipo_inmueble = $1
          AND is_outlier = FALSE
          AND precio > 0 AND area_construida > 0
          AND geom IS NOT NULL
    """, tipo_inmueble)

    if len(rows) < 30:
        return {'error': f'Insuficientes datos: n={len(rows)}'}

    feature_names = ['area_construida', 'habitaciones', 'banos',
                     'garajes', 'estrato', 'iacc', 'iseg',
                     'ihed', 'ipnu', 'idot']

    # Preparar matrices
    X_list, y_list, coords_list = [], [], []
    for r in rows:
        try:
            row = [float(r[f]) if r[f] is not None else 0.0
                   for f in feature_names]
            pm2 = float(r['precio']) / float(r['area_construida'])
            X_list.append(row)
            y_list.append(math.log(pm2))
            coords_list.append([float(r['lat']), float(r['lon'])])
        except (TypeError, ValueError):
            continue

    X = np.array(X_list)
    y = np.array(y_list)
    coords = np.array(coords_list)

    # Modelo OLS para residuos
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LinearRegression().fit(X_scaled, y)
    y_pred = model.predict(X_scaled)
    residuos = y - y_pred

    return {
        'tipo_inmueble': tipo_inmueble,
        'n_observaciones': len(X),
        'r2_ols': round(float(model.score(X_scaled, y)), 4),
        'rmse': round(float(np.sqrt(np.mean(residuos ** 2))), 4),
        'diagnosticos': {
            'multicolinealidad_VIF': compute_vif(X_scaled, feature_names),
            'autocorrelacion_Moran_I': moran_i_residuos(residuos, coords),
            'normalidad_residuos': shapiro_wilk_residuos(residuos),
            'heterocedasticidad_BP': breusch_pagan_residuos(residuos, X_scaled),
        },
        'recomendaciones': _generar_recomendaciones(
            compute_vif(X_scaled, feature_names),
            moran_i_residuos(residuos, coords),
            shapiro_wilk_residuos(residuos),
            breusch_pagan_residuos(residuos, X_scaled),
        ),
    }


def _generar_recomendaciones(vif: dict, moran: dict, normal: dict, bp: dict) -> list:
    """Genera lista de recomendaciones segun los diagnosticos."""
    recs = []

    # VIF
    severos = [k for k, v in vif.items()
               if isinstance(v, dict) and v.get('severity') == 'severo']
    if severos:
        recs.append(f"Multicolinealidad severa en: {', '.join(severos)}. "
                    "Considerar Ridge o eliminar variables redundantes.")

    # Moran
    if isinstance(moran, dict) and moran.get('p_value', 1) < 0.05:
        recs.append("Autocorrelacion espacial detectada. "
                    "Implementar Spatial Lag Model o GWR (Mejora #5).")

    # Normalidad
    if isinstance(normal, dict) and not normal.get('normal', True):
        recs.append("Residuos no normales. Aplicar transformacion Box-Cox "
                    "o usar regresion robusta (HuberRegressor).")

    # Heterocedasticidad
    if isinstance(bp, dict) and not bp.get('homocedastico', True):
        recs.append("Heterocedasticidad presente. Usar errores estandar "
                    "robustos HC3 (sm.OLS().fit(cov_type='HC3')).")

    if not recs:
        recs.append("Diagnosticos OK. Modelo cumple supuestos OLS.")

    return recs
