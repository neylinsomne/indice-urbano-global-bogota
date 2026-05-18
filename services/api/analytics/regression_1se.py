"""
Mejora #11: Seleccion de modelo por regla 1-SE (Hastie et al., 2009).

El sistema actual selecciona el mejor modelo por menor CV-RMSE puro.
Esto ignora la parsimonia: un modelo con 13 features y CV-RMSE=0.193
es preferido a uno con 5 features y CV-RMSE=0.195, aunque la
diferencia sea estadisticamente nula.

La regla 1-SE selecciona el modelo MAS SIMPLE cuyo CV-RMSE este dentro
de 1 error estandar del mejor modelo:

    Seleccionar modelo m tal que:
        CV-RMSE_m <= CV-RMSE* + SE*

donde * es el modelo con mejor CV-RMSE.

Implementa tambien Score multi-criterio:
    Score_m = -CV-RMSE_m + lambda1/p_m - lambda2 * SE_m

Referencia: Hastie, T., Tibshirani, R. & Friedman, J. (2009).
The Elements of Statistical Learning, Cap. 7.
"""
import logging
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)


def regla_1se(
    modelos: dict,
    metric_key: str = 'cv_rmse_mean',
    se_key: str = 'cv_rmse_std',
    n_features_key: str = 'n_features',
) -> dict:
    """
    Aplica la regla 1-SE para seleccion de modelos.

    Args:
        modelos: dict {nombre: {cv_rmse_mean, cv_rmse_std, n_features}}
        metric_key: clave del CV-RMSE
        se_key: clave del SE del CV
        n_features_key: clave del num. de features activos

    Returns:
        {
            'mejor_cv_rmse': nombre del modelo con menor RMSE,
            'mejor_1se': nombre del modelo seleccionado por 1-SE,
            'umbral_1se': float,
            'modelos_aceptables': [nombres dentro del umbral],
        }
    """
    if not modelos:
        return {'error': 'sin modelos para evaluar'}

    nombres = list(modelos.keys())
    rmses = [modelos[n].get(metric_key, float('inf')) for n in nombres]
    ses = [modelos[n].get(se_key, 0.0) for n in nombres]
    pfeats = [modelos[n].get(n_features_key, 999) for n in nombres]

    idx_best = int(np.argmin(rmses))
    rmse_best = rmses[idx_best]
    se_best = ses[idx_best]

    umbral = rmse_best + se_best

    # Modelos aceptables: dentro del umbral
    aceptables_idx = [i for i, r in enumerate(rmses) if r <= umbral]
    aceptables_nombres = [nombres[i] for i in aceptables_idx]

    # De los aceptables, elegir el mas simple (menor n_features)
    if not aceptables_idx:
        idx_1se = idx_best
    else:
        idx_1se = min(aceptables_idx, key=lambda i: pfeats[i])

    return {
        'mejor_por_cv_rmse': nombres[idx_best],
        'mejor_por_1se': nombres[idx_1se],
        'cv_rmse_mejor': round(rmse_best, 4),
        'se_mejor': round(se_best, 4),
        'umbral_1se': round(umbral, 4),
        'modelos_aceptables': aceptables_nombres,
        'todos': [
            {
                'modelo': nombres[i],
                'cv_rmse': round(rmses[i], 4),
                'se': round(ses[i], 4),
                'n_features': pfeats[i],
                'dentro_1se': i in aceptables_idx,
                'es_seleccionado': i == idx_1se,
            }
            for i in range(len(nombres))
        ],
        'cambio_de_seleccion': nombres[idx_best] != nombres[idx_1se],
        'referencia': 'Hastie, Tibshirani, Friedman (2009), Cap. 7.10',
    }


def score_multi_criterio(
    modelos: dict,
    lambda_parsimonia: float = 0.01,
    lambda_estabilidad: float = 0.5,
) -> dict:
    """
    Selecciona modelo por score multi-criterio:

        Score_m = -CV-RMSE_m + lambda1 * (1/p_m) - lambda2 * SE_m

    Permite balancear precision, parsimonia y estabilidad.
    """
    nombres = list(modelos.keys())
    if not nombres:
        return {'error': 'sin modelos'}

    scores = []
    for n in nombres:
        m = modelos[n]
        cv_rmse = m.get('cv_rmse_mean', float('inf'))
        se = m.get('cv_rmse_std', 0)
        n_feats = max(m.get('n_features', 1), 1)

        score = -cv_rmse + lambda_parsimonia * (1.0 / n_feats) - lambda_estabilidad * se
        scores.append(score)

    idx_mejor = int(np.argmax(scores))

    return {
        'lambda_parsimonia': lambda_parsimonia,
        'lambda_estabilidad': lambda_estabilidad,
        'mejor_modelo': nombres[idx_mejor],
        'mejor_score': round(scores[idx_mejor], 4),
        'todos': [
            {
                'modelo': nombres[i],
                'score': round(scores[i], 4),
                'cv_rmse': round(modelos[nombres[i]].get('cv_rmse_mean', 0), 4),
                'se': round(modelos[nombres[i]].get('cv_rmse_std', 0), 4),
                'n_features': modelos[nombres[i]].get('n_features', 0),
            }
            for i in range(len(nombres))
        ],
        'referencia': 'Multi-criterio inspirado en Hastie et al. (2009)',
    }


async def aplicar_1se_a_modelos_actuales(
    conn: asyncpg.Connection,
    tipo_inmueble: str,
) -> dict:
    """
    Aplica la regla 1-SE a los modelos ya entrenados en
    iug.regression_market_summary.

    Compara la seleccion actual (best_model por CV-RMSE puro) con
    la seleccion 1-SE.
    """
    row = await conn.fetchrow("""
        SELECT tipo_inmueble, best_model,
               r2_ols, r2_ridge, r2_lasso, r2_elastic_net,
               cv_mean_ols
        FROM iug.regression_market_summary
        WHERE tipo_inmueble = $1
    """, tipo_inmueble)

    if not row:
        return {'error': f'sin modelo entrenado para {tipo_inmueble}'}

    # Buscar metrics detallados de cada modelo
    models_rows = await conn.fetch("""
        SELECT model_type, metrics, n_samples, feature_names
        FROM iug.regression_model
        WHERE tipo_inmueble = $1
    """, tipo_inmueble)

    if not models_rows:
        return {'error': 'sin metrics detallados'}

    import json
    modelos = {}
    for m in models_rows:
        try:
            metrics = json.loads(m['metrics']) if isinstance(m['metrics'], str) else m['metrics']
            features = json.loads(m['feature_names']) if isinstance(m['feature_names'], str) else m['feature_names']

            modelos[m['model_type']] = {
                'cv_rmse_mean': metrics.get('cv_rmse_mean', 0),
                'cv_rmse_std': metrics.get('cv_rmse_std', 0),
                'n_features': len([f for f in features if not f.startswith('_')]),
                'r2': metrics.get('r2', 0),
            }
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parsing metrics for {m['model_type']}: {e}")

    if not modelos:
        return {'error': 'no se pudieron parsear metricas'}

    seleccion_1se = regla_1se(modelos)
    seleccion_multi = score_multi_criterio(modelos)

    return {
        'tipo_inmueble': tipo_inmueble,
        'seleccion_actual_v110': row['best_model'],
        'metodos_alternativos': {
            'regla_1se': seleccion_1se,
            'score_multi_criterio': seleccion_multi,
        },
        'modelos_disponibles': modelos,
        'recomendacion': (
            f"Cambiar de '{row['best_model']}' a '{seleccion_1se['mejor_por_1se']}' "
            "para mayor parsimonia."
            if seleccion_1se['cambio_de_seleccion'] else
            f"Mantener '{row['best_model']}'. Es el mas simple dentro del umbral 1-SE."
        ),
    }
