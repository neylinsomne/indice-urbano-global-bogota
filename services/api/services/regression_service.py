"""
Servicio de Analisis de Mercado por Regresion.

Entrena modelos OLS, Ridge, Lasso, Elastic Net y Quantile Regression
por tipo de inmueble. Selecciona automaticamente el mejor modelo por
CV-RMSE, calcula metricas IAAO (COD, PRD, PRB), y genera predicciones
usando el modelo ganador.
"""
import asyncio
import json
import logging
import math
from typing import Optional

import numpy as np
from sklearn.linear_model import (
    LinearRegression, Ridge, RidgeCV, Lasso, LassoCV,
    ElasticNet, ElasticNetCV, QuantileRegressor,
)
from sklearn.model_selection import cross_val_score, RepeatedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

logger = logging.getLogger(__name__)

# ─── Feature sets ─────────────────────────────────────────
# Hedonico: solo lo que tiene el inmueble (fisico + estrato + localidad)
HEDONIC_COLS = [
    'area_construida', 'habitaciones', 'banos', 'garajes',
    'estrato', 'ln_area',
    'area_x_estrato',                # interaccion
    'banos_por_hab',                  # ratio
]

# Completo: hedonico + indicadores urbanos
FULL_COLS = HEDONIC_COLS + [
    'iacc', 'iseg', 'ihed', 'ipnu', 'idot',
]

# Default para backwards-compat
FEATURE_COLS = FULL_COLS

MIN_SAMPLES = 30

FEATURE_LABELS = {
    'area_construida': 'Area construida',
    'habitaciones': 'Habitaciones',
    'banos': 'Banos',
    'garajes': 'Garajes',
    'estrato': 'Estrato',
    'ln_area': 'Ln(Area)',
    'area_x_estrato': 'Area x Estrato',
    'banos_por_hab': 'Banos/Habitaciones',
    'iacc': 'Accesibilidad',
    'iseg': 'Seguridad',
    'ihed': 'Calidad Hedonica',
    'ipnu': 'Potencial Normativo',
    'idot': 'Dotaciones',
}


# ─── Utilidades ──────────────────────────────────────────────

def _compute_vif(X: np.ndarray, feature_names: list) -> dict:
    """Variance Inflation Factor por feature."""
    vif = {}
    n_features = X.shape[1]
    for i, name in enumerate(feature_names):
        if n_features < 2:
            vif[name] = 1.0
            continue
        X_other = np.delete(X, i, axis=1)
        X_target = X[:, i]
        reg = LinearRegression().fit(X_other, X_target)
        r2 = reg.score(X_other, X_target)
        vif[name] = round(1.0 / max(1.0 - r2, 1e-10), 2)
    return vif


def _compute_iaao(actual_prices: np.ndarray, predicted_prices: np.ndarray) -> dict:
    """
    Metricas IAAO (International Association of Assessing Officers).
    - COD: Coefficient of Dispersion (aceptable 5-15%)
    - PRD: Price-Related Differential (aceptable 0.98-1.03)
    - PRB: Price-Related Bias (aceptable -0.05 a +0.05)
    - Ratio mediano (aceptable 0.90-1.10)
    """
    ratios = predicted_prices / np.maximum(actual_prices, 1.0)
    median_ratio = float(np.median(ratios))

    # COD
    cod = float(np.mean(np.abs(ratios - median_ratio)) / max(median_ratio, 1e-10) * 100)

    # PRD
    mean_ratio = float(np.mean(ratios))
    weighted_mean_ratio = float(np.sum(predicted_prices) / max(np.sum(actual_prices), 1.0))
    prd = mean_ratio / max(weighted_mean_ratio, 1e-10)

    # PRB via OLS
    try:
        pct_diff = (ratios - median_ratio) / max(median_ratio, 1e-10)
        ln_value = np.log(np.maximum(actual_prices, 1.0)).reshape(-1, 1)
        ln_centered = ln_value - np.mean(ln_value)
        prb_model = LinearRegression().fit(ln_centered, pct_diff)
        prb = float(prb_model.coef_[0])
    except Exception as e:
        logger.warning(f"PRB computation failed: {e}")
        prb = None

    return {
        'median_ratio': round(median_ratio, 4),
        'cod': round(cod, 2),
        'prd': round(prd, 4),
        'prb': round(prb, 4) if prb is not None else None,
        'cod_ok': 5.0 <= cod <= 15.0,
        'prd_ok': 0.98 <= prd <= 1.03,
        'prb_ok': (-0.05 <= prb <= 0.05) if prb is not None else False,
        'level_ok': 0.90 <= median_ratio <= 1.10,
    }


def _market_label(ratio: float) -> str:
    if ratio > 1.20:
        return "Significativamente por encima del mercado"
    elif ratio > 1.10:
        return "Ligeramente por encima del mercado"
    elif ratio >= 0.90:
        return "En linea con el mercado"
    elif ratio >= 0.80:
        return "Ligeramente por debajo del mercado"
    else:
        return "Significativamente por debajo del mercado"


def _get_top_features(coefs: np.ndarray, names: list, top_n: int = 5) -> list:
    """Top N features by absolute coefficient."""
    abs_coefs = np.abs(coefs)
    total = abs_coefs.sum()
    if total == 0:
        return []
    indices = np.argsort(abs_coefs)[::-1][:top_n]
    result = []
    for idx in indices:
        if abs_coefs[idx] < 1e-8:
            break
        result.append({
            'feature': names[idx],
            'label': FEATURE_LABELS.get(names[idx], names[idx]),
            'coef': round(float(coefs[idx]), 6),
            'abs_pct': round(float(abs_coefs[idx] / total * 100), 1),
            'impact': 'positive' if coefs[idx] > 0 else 'negative',
        })
    return result


def _compute_cross_model_consensus(results: dict, feature_names: list,
                                   threshold: float = 0.05) -> dict:
    """
    Cross-model consensus: variables donde OLS + Lasso + ElasticNet coinciden
    en signo y magnitud. Estas son las senales estructurales del mercado.

    threshold: beta estandarizado minimo para considerar un feature "activo"
    (features por debajo de esto son zeroeados o irrelevantes).
    """
    consensus = {}
    target_models = ['ols', 'lasso', 'elastic_net']

    for feature in feature_names:
        coefs_by_model = {}
        for model_name in target_models:
            if results.get(model_name):
                coef = results[model_name]['coefficients'].get(feature, 0.0)
                coefs_by_model[model_name] = float(coef)

        if not coefs_by_model:
            continue

        active_models = {m: c for m, c in coefs_by_model.items() if abs(c) >= threshold}
        n_active = len(active_models)

        # Sign agreement among active models
        signs = set(1 if c > 0 else -1 for c in active_models.values())
        sign_ok = len(signs) <= 1  # all same sign (or none active)

        # Ridge doesn't zero features, so use it as a stability check:
        # if ridge coef is near zero but OLS is large → multicollinearity signal
        ridge_coef = float(results['ridge']['coefficients'].get(feature, 0.0)) if results.get('ridge') else None
        ridge_near_zero = ridge_coef is not None and abs(ridge_coef) < 0.03

        ols_coef = float(results['ols']['coefficients'].get(feature, 0.0)) if results.get('ols') else 0.0
        multicollinearity_flag = (abs(ols_coef) > 0.1 and ridge_near_zero)

        consensus[feature] = {
            'label': FEATURE_LABELS.get(feature, feature),
            'coefs': {**coefs_by_model},
            'ridge_coef': round(ridge_coef, 6) if ridge_coef is not None else None,
            'n_active': n_active,
            'sign_agreement': sign_ok,
            # True consensus: active in all 3 target models AND same sign
            'consensus': n_active == len(target_models) and sign_ok,
            # Partial: active in at least 2
            'partial_consensus': n_active >= 2 and sign_ok,
            'multicollinearity_flag': multicollinearity_flag,
        }

    # Sort: full consensus first, then partial, then single, by n_active desc
    ordered = sorted(
        consensus.items(),
        key=lambda kv: (kv[1]['consensus'], kv[1]['partial_consensus'], kv[1]['n_active']),
        reverse=True,
    )
    return {k: v for k, v in ordered}


def _compute_psi(train_values: np.ndarray, new_values: np.ndarray,
                 n_bins: int = 10) -> float:
    """
    Population Stability Index para una feature.
    Compara la distribucion de entrenamiento vs datos nuevos.
    PSI < 0.10 = estable | 0.10-0.20 = monitorear | > 0.20 = drift
    """
    if len(train_values) < 10 or len(new_values) < 5:
        return 0.0
    # Bins basados en percentiles del conjunto de entrenamiento
    bins = np.nanpercentile(train_values, np.linspace(0, 100, n_bins + 1))
    bins = np.unique(bins)
    if len(bins) < 2:
        return 0.0

    def bucket_pct(arr):
        counts, _ = np.histogram(arr, bins=bins)
        pct = counts / max(len(arr), 1)
        return np.clip(pct, 1e-4, None)  # avoid log(0)

    e = bucket_pct(train_values)
    a = bucket_pct(new_values)
    # Normalize to sum 1 in case of edge bins
    e = e / e.sum()
    a = a / a.sum()
    psi = float(np.sum((a - e) * np.log(a / e)))
    return round(psi, 4)


# ─── Data fetching ───────────────────────────────────────────

async def _fetch_training_data(conn, tipo_inmueble: str, feature_set: str = 'full'):
    """
    Fetch features (X) and target (y = ln(precio_m2)) for a tipo.

    feature_set:
      - 'hedonic': solo caracteristicas fisicas del inmueble + estrato
      - 'full': hedonico + indicadores urbanos (iacc, iseg, ihed, ipnu, idot)

    Returns (X, y, ids, feature_names_used) or None if insufficient data.
    """
    rows = await conn.fetch("""
        SELECT id_inmueble,
               area_construida, habitaciones, banos, garajes, estrato,
               iacc, iseg, ihed, ipnu, idot,
               precio,
               (precio / NULLIF(area_construida, 0)) AS precio_m2,
               id_localidad, id_barrio
        FROM iug.inmueble
        WHERE tipo_inmueble = $1
          AND is_outlier = FALSE
          AND precio IS NOT NULL AND precio > 0
          AND area_construida IS NOT NULL AND area_construida > 0
    """, tipo_inmueble)

    if len(rows) < MIN_SAMPLES:
        return None

    target_cols = HEDONIC_COLS if feature_set == 'hedonic' else FULL_COLS

    ids = []
    raw_features = []
    targets = []

    for r in rows:
        pm2 = float(r['precio_m2'])
        if pm2 <= 0:
            continue
        ids.append(r['id_inmueble'])
        targets.append(math.log(pm2))

        # Base values
        area = float(r['area_construida']) if r['area_construida'] is not None else np.nan
        hab = float(r['habitaciones']) if r['habitaciones'] is not None else np.nan
        banos = float(r['banos']) if r['banos'] is not None else np.nan
        garajes = float(r['garajes']) if r['garajes'] is not None else 0.0
        estrato = float(r['estrato']) if r['estrato'] is not None else np.nan

        # Engineered features
        ln_area = math.log(area) if area and area > 0 else np.nan
        area_x_estrato = (area * estrato) if not (np.isnan(area) or np.isnan(estrato)) else np.nan
        banos_por_hab = (banos / hab) if hab and hab > 0 and not np.isnan(banos) else np.nan

        # Build feature dict for this row
        feat_dict = {
            'area_construida': area,
            'habitaciones': hab,
            'banos': banos,
            'garajes': garajes,
            'estrato': estrato,
            'ln_area': ln_area,
            'area_x_estrato': area_x_estrato,
            'banos_por_hab': banos_por_hab,
            'iacc': float(r['iacc']) if r['iacc'] is not None else np.nan,
            'iseg': float(r['iseg']) if r['iseg'] is not None else np.nan,
            'ihed': float(r['ihed']) if r['ihed'] is not None else np.nan,
            'ipnu': float(r['ipnu']) if r['ipnu'] is not None else np.nan,
            'idot': float(r['idot']) if r['idot'] is not None else np.nan,
        }

        feat = [feat_dict.get(col, np.nan) for col in target_cols]
        raw_features.append(feat)

    if len(ids) < MIN_SAMPLES:
        return None

    X = np.array(raw_features)
    y = np.array(targets)

    # Impute NaNs with per-column median
    for col_idx in range(X.shape[1]):
        col = X[:, col_idx]
        mask = np.isnan(col)
        if mask.any():
            median_val = np.nanmedian(col)
            if np.isnan(median_val):
                median_val = 0.0
            col[mask] = median_val

    # Drop features that are constant (zero variance)
    feature_names_used = list(target_cols)
    keep_mask = np.std(X, axis=0) > 1e-10
    if not keep_mask.all():
        X = X[:, keep_mask]
        feature_names_used = [f for f, k in zip(feature_names_used, keep_mask) if k]

    if X.shape[1] == 0:
        return None

    # Grupos espaciales para CV espacial
    spatial_groups = np.array([
        int(r['id_localidad']) if r['id_localidad'] is not None else 0
        for r in rows
        if float(r['precio_m2']) > 0
    ])[:len(ids)]

    return X, y, ids, feature_names_used, spatial_groups


# ─── Training pipeline ──────────────────────────────────────

def _train_model(name, estimator, X, y, feature_names, n_cv):
    """Train a single model, return (model_obj, y_pred, result_dict) or None."""
    try:
        estimator.fit(X, y)
        y_pred = estimator.predict(X)
        r2 = r2_score(y, y_pred)
        rmse = math.sqrt(mean_squared_error(y, y_pred))
        mae = mean_absolute_error(y, y_pred)

        # Cross-validation con neg_root_mean_squared_error (metrica primaria SOTA)
        cv_rmse = cross_val_score(
            clone(estimator),
            X, y, cv=n_cv, scoring='neg_root_mean_squared_error',
        )
        cv_r2 = cross_val_score(
            clone(estimator),
            X, y, cv=n_cv, scoring='r2',
        )

        coefs = estimator.coef_ if hasattr(estimator, 'coef_') else np.zeros(X.shape[1])
        intercept = float(estimator.intercept_) if hasattr(estimator, 'intercept_') else 0.0

        metrics = {
            'r2': round(r2, 4),
            'rmse': round(rmse, 4),
            'mae': round(mae, 4),
            'cv_rmse_scores': [round(float(-s), 4) for s in cv_rmse],
            'cv_rmse_mean': round(float(-cv_rmse.mean()), 4),
            'cv_rmse_std': round(float(cv_rmse.std()), 4),
            'cv_r2_mean': round(float(cv_r2.mean()), 4),
            'cv_r2_std': round(float(cv_r2.std()), 4),
        }

        # Alpha for regularized models
        if hasattr(estimator, 'alpha_'):
            metrics['alpha'] = round(float(estimator.alpha_), 6)
        if hasattr(estimator, 'l1_ratio_'):
            metrics['l1_ratio'] = round(float(estimator.l1_ratio_), 4)

        result = {
            'coefficients': {
                'intercept': round(intercept, 6),
                **{n: round(float(c), 6) for n, c in zip(feature_names, coefs)},
            },
            'metrics': metrics,
        }

        return estimator, y_pred, result

    except Exception as e:
        logger.warning(f"{name} failed: {e}")
        return None


async def _train_for_type(conn, tipo_inmueble: str, trigger_reason: str = 'manual'):
    """
    Train all models for one tipo_inmueble.
    Trains BOTH hedonic-only and full (hedonic + indicators) pipelines,
    picks the one with better CV-RMSE.
    Returns summary dict or None.
    """
    # Train both feature sets and pick the best
    data_hedonic = await _fetch_training_data(conn, tipo_inmueble, feature_set='hedonic')
    data_full = await _fetch_training_data(conn, tipo_inmueble, feature_set='full')

    if data_hedonic is None and data_full is None:
        logger.info(f"Regression: skipping {tipo_inmueble} (insufficient data)")
        return None

    # We'll train both and compare
    best_feature_set = None
    best_cv_rmse = float('inf')

    for fs_name, data in [('hedonic', data_hedonic), ('full', data_full)]:
        if data is None:
            continue
        X_raw, y_tmp, _, fn, _sg = data
        scaler_tmp = StandardScaler()
        X_tmp = scaler_tmp.fit_transform(X_raw)
        n_cv_tmp = min(5, len(y_tmp))
        try:
            ols_tmp = LinearRegression().fit(X_tmp, y_tmp)
            cv_tmp = cross_val_score(LinearRegression(), X_tmp, y_tmp,
                                     cv=n_cv_tmp, scoring='neg_root_mean_squared_error')
            cv_rmse_tmp = float(-cv_tmp.mean())
            r2_tmp = ols_tmp.score(X_tmp, y_tmp)
            logger.info(f"  {tipo_inmueble} [{fs_name}]: R2={r2_tmp:.4f}, CV-RMSE={cv_rmse_tmp:.4f}, features={len(fn)}")
            if cv_rmse_tmp < best_cv_rmse:
                best_cv_rmse = cv_rmse_tmp
                best_feature_set = fs_name
        except Exception as e:
            logger.warning(f"  {tipo_inmueble} [{fs_name}] quick-eval failed: {e}")

    chosen_data = data_full if best_feature_set == 'full' else data_hedonic
    if chosen_data is None:
        chosen_data = data_hedonic or data_full
        best_feature_set = 'hedonic' if data_hedonic else 'full'

    logger.info(f"Regression {tipo_inmueble}: selected feature_set='{best_feature_set}'")

    X_raw, y, ids, feature_names, spatial_groups = chosen_data
    n_samples = len(y)

    # Scale features
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    n_cv = min(5, n_samples)
    results = {}
    trained_models = {}  # name -> (model_obj, y_pred)
    loop = asyncio.get_running_loop()

    # ── OLS ──
    out = await loop.run_in_executor(None, _train_model, 'ols', LinearRegression(), X, y, feature_names, n_cv)
    if out:
        model_obj, y_pred, result = out
        # Add VIF (only for OLS since it's the base model)
        result['metrics']['vif'] = _compute_vif(X, feature_names)
        # Add adjusted R2
        r2_val = result['metrics']['r2']
        adj_r2 = 1 - (1 - r2_val) * (n_samples - 1) / max(n_samples - X.shape[1] - 1, 1)
        result['metrics']['adj_r2'] = round(adj_r2, 4)
        results['ols'] = result
        trained_models['ols'] = (model_obj, y_pred)

    # ── Ridge ──
    out = await loop.run_in_executor(
        None, _train_model,
        'ridge',
        RidgeCV(alphas=np.logspace(-3, 4, 20), cv=n_cv),
        X, y, feature_names, n_cv,
    )
    if out:
        results['ridge'] = out[2]
        trained_models['ridge'] = (out[0], out[1])

    # ── Lasso ──
    out = await loop.run_in_executor(
        None, _train_model,
        'lasso',
        LassoCV(alphas=np.logspace(-4, 2, 20), cv=n_cv, max_iter=10000),
        X, y, feature_names, n_cv,
    )
    if out:
        results['lasso'] = out[2]
        trained_models['lasso'] = (out[0], out[1])

    # ── Elastic Net ──
    out = await loop.run_in_executor(
        None, _train_model,
        'elastic_net',
        ElasticNetCV(
            alphas=np.logspace(-4, 2, 10),
            l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],
            cv=n_cv, max_iter=10000,
        ),
        X, y, feature_names, n_cv,
    )
    if out:
        results['elastic_net'] = out[2]
        trained_models['elastic_net'] = (out[0], out[1])

    if not trained_models:
        logger.warning(f"No models trained for {tipo_inmueble}")
        return None

    # ── Select best model by lowest CV-RMSE (SOTA criterion) ──
    model_cv_rmse = {}
    for name, result in results.items():
        if name.startswith('quantile'):
            continue
        cv_rmse = result['metrics'].get('cv_rmse_mean')
        if cv_rmse is not None:
            model_cv_rmse[name] = cv_rmse

    best_model = min(model_cv_rmse, key=model_cv_rmse.get) if model_cv_rmse else 'ols'

    # Use best model's predictions for market ratios
    best_obj, best_pred_ln = trained_models[best_model]
    predicted_pm2 = np.exp(best_pred_ln)
    actual_pm2 = np.exp(y)
    market_ratios = actual_pm2 / np.maximum(predicted_pm2, 1.0)

    # ── IAAO metrics on the best model ──
    iaao = _compute_iaao(actual_pm2, predicted_pm2)

    # ── Cross-validation espacial (detectar leakage por edificio/barrio) ──
    spatial_cv_result = None
    try:
        from services.api.services.spatial_cv import spatial_cross_validate
        n_unique_groups = len(np.unique(spatial_groups))
        if n_unique_groups >= 3 and len(y) >= 30:
            best_cv_standard = (
                results[best_model]['metrics']['cv_rmse_mean'],
                results[best_model]['metrics']['cv_rmse_std'],
                results[best_model]['metrics']['cv_r2_mean'],
            )
            scv = spatial_cross_validate(
                X, y, spatial_groups, clone(best_obj),
                n_splits=min(5, n_unique_groups),
                standard_cv_scores=best_cv_standard,
            )
            spatial_cv_result = {
                'cv_rmse_spatial': round(scv.cv_rmse_spatial, 4),
                'cv_r2_spatial': round(scv.cv_r2_spatial, 4),
                'cv_rmse_standard': round(scv.cv_rmse_standard, 4),
                'leakage_ratio': round(scv.leakage_ratio, 4),
                'leakage_flag': scv.leakage_flag,
                'n_groups': scv.n_groups,
            }
            if scv.leakage_flag:
                logger.warning(
                    f"{tipo_inmueble}: Leakage espacial detectado "
                    f"({scv.leakage_ratio:+.1%}). "
                    "El modelo puede estar memorizando barrios."
                )
    except Exception as e:
        logger.warning(f"Spatial CV failed for {tipo_inmueble}: {e}")

    # ── Cross-model consensus (que variables valora el mercado de forma robusta) ──
    consensus = _compute_cross_model_consensus(results, feature_names)

    # ── Top features from best sparse model (Lasso or ElasticNet) ──
    sparse_model_name = 'lasso' if 'lasso' in trained_models else (
        'elastic_net' if 'elastic_net' in trained_models else best_model
    )
    sparse_obj = trained_models[sparse_model_name][0]
    sparse_coefs = sparse_obj.coef_ if hasattr(sparse_obj, 'coef_') else np.zeros(len(feature_names))
    top_features = _get_top_features(sparse_coefs, feature_names)

    # ── Quantile Regression (Q25, Q50, Q75) ──
    q_models = {}
    for q_name, q_val in [('quantile_25', 0.25), ('quantile_50', 0.50), ('quantile_75', 0.75)]:
        try:
            qr = QuantileRegressor(quantile=q_val, alpha=0.0, solver='highs')
            qr.fit(X, y)
            results[q_name] = {
                'coefficients': {
                    'intercept': round(float(qr.intercept_), 6),
                    **{n: round(float(c), 6) for n, c in zip(feature_names, qr.coef_)},
                },
                'metrics': {'quantile': q_val},
            }
            q_models[q_name] = qr
        except Exception as e:
            logger.warning(f"Quantile {q_name} failed for {tipo_inmueble}: {e}")
            results[q_name] = None

    q25_pm2 = np.exp(q_models['quantile_25'].predict(X)) if 'quantile_25' in q_models else None
    q75_pm2 = np.exp(q_models['quantile_75'].predict(X)) if 'quantile_75' in q_models else None

    # ── Build predictions ──
    predictions = []
    for i in range(n_samples):
        q_pos = 'within_iqr'
        q25_val = float(q25_pm2[i]) if q25_pm2 is not None else None
        q75_val = float(q75_pm2[i]) if q75_pm2 is not None else None

        if q25_val is not None and q75_val is not None:
            if actual_pm2[i] < q25_val:
                q_pos = 'below_q25'
            elif actual_pm2[i] > q75_val:
                q_pos = 'above_q75'

        predictions.append((
            ids[i],
            tipo_inmueble,
            round(float(predicted_pm2[i]), 2),
            round(float(actual_pm2[i]), 2),
            round(float(market_ratios[i]), 4),
            round(q25_val, 2) if q25_val is not None else None,
            round(q75_val, 2) if q75_val is not None else None,
            q_pos,
            json.dumps(top_features),
            best_model,
        ))

    # ── Persist all DB writes atomically ──
    async with conn.transaction():
        # ── Persist models ──
        for model_type, model_data in results.items():
            if model_data is None:
                continue
            await conn.execute("""
                INSERT INTO iug.regression_model
                    (tipo_inmueble, model_type, coefficients, metrics, n_samples, feature_names)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6::jsonb)
                ON CONFLICT (tipo_inmueble, model_type) DO UPDATE SET
                    coefficients = EXCLUDED.coefficients,
                    metrics = EXCLUDED.metrics,
                    n_samples = EXCLUDED.n_samples,
                    feature_names = EXCLUDED.feature_names,
                    trained_at = NOW()
            """,
                tipo_inmueble,
                model_type,
                json.dumps(model_data['coefficients']),
                json.dumps(model_data['metrics']),
                n_samples,
                json.dumps(feature_names),
            )

        # ── Persist predictions ──
        await conn.execute(
            "DELETE FROM iug.regression_prediction WHERE tipo_inmueble = $1",
            tipo_inmueble,
        )

        if predictions:
            await conn.executemany("""
                INSERT INTO iug.regression_prediction
                    (id_inmueble, tipo_inmueble, predicted_precio_m2, actual_precio_m2,
                     market_ratio, quantile_25_pm2, quantile_75_pm2, quantile_position,
                     lasso_top_features, best_model)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
            """, predictions)

        # ── Persist market summary with IAAO ──
        r2_ols_val = results['ols']['metrics']['r2'] if results.get('ols') else None
        r2_ridge_val = results['ridge']['metrics']['r2'] if results.get('ridge') else None
        r2_lasso_val = results['lasso']['metrics']['r2'] if results.get('lasso') else None
        r2_enet_val = results['elastic_net']['metrics']['r2'] if results.get('elastic_net') else None
        cv_ols_val = results['ols']['metrics']['cv_r2_mean'] if results.get('ols') else None

        n_over = int(np.sum(market_ratios > 1.10))
        n_fair = int(np.sum((market_ratios >= 0.90) & (market_ratios <= 1.10)))
        n_under = int(np.sum(market_ratios < 0.90))
        avg_ratio = round(float(np.mean(market_ratios)), 4)
        median_ratio = round(float(np.median(market_ratios)), 4)

        avg_q25 = round(float(np.mean(q25_pm2)), 2) if q25_pm2 is not None else None
        avg_q75 = round(float(np.mean(q75_pm2)), 2) if q75_pm2 is not None else None
        avg_pred = round(float(np.mean(predicted_pm2)), 2)

        await conn.execute("""
            INSERT INTO iug.regression_market_summary
                (tipo_inmueble, r2_ols, r2_ridge, r2_lasso, r2_elastic_net,
                 cv_mean_ols, best_model, active_model,
                 n_properties, n_overpriced, n_fair, n_underpriced,
                 avg_market_ratio, median_market_ratio,
                 avg_q25_pm2, avg_q75_pm2, avg_predicted_pm2, top_features,
                 iaao_cod, iaao_prd, iaao_prb, iaao_median_ratio,
                 iaao_cod_ok, iaao_prd_ok, iaao_level_ok)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb,
                    $19,$20,$21,$22,$23,$24,$25)
            ON CONFLICT (tipo_inmueble) DO UPDATE SET
                r2_ols = EXCLUDED.r2_ols, r2_ridge = EXCLUDED.r2_ridge,
                r2_lasso = EXCLUDED.r2_lasso, r2_elastic_net = EXCLUDED.r2_elastic_net,
                cv_mean_ols = EXCLUDED.cv_mean_ols,
                best_model = EXCLUDED.best_model, active_model = EXCLUDED.active_model,
                n_properties = EXCLUDED.n_properties,
                n_overpriced = EXCLUDED.n_overpriced, n_fair = EXCLUDED.n_fair,
                n_underpriced = EXCLUDED.n_underpriced,
                avg_market_ratio = EXCLUDED.avg_market_ratio,
                median_market_ratio = EXCLUDED.median_market_ratio,
                avg_q25_pm2 = EXCLUDED.avg_q25_pm2, avg_q75_pm2 = EXCLUDED.avg_q75_pm2,
                avg_predicted_pm2 = EXCLUDED.avg_predicted_pm2,
                top_features = EXCLUDED.top_features,
                iaao_cod = EXCLUDED.iaao_cod, iaao_prd = EXCLUDED.iaao_prd,
                iaao_prb = EXCLUDED.iaao_prb, iaao_median_ratio = EXCLUDED.iaao_median_ratio,
                iaao_cod_ok = EXCLUDED.iaao_cod_ok, iaao_prd_ok = EXCLUDED.iaao_prd_ok,
                iaao_level_ok = EXCLUDED.iaao_level_ok,
                updated_at = NOW()
        """,
            tipo_inmueble,
            r2_ols_val, r2_ridge_val, r2_lasso_val, r2_enet_val,
            cv_ols_val,
            best_model, best_model,
            n_samples,
            n_over, n_fair, n_under,
            avg_ratio, median_ratio,
            avg_q25, avg_q75, avg_pred,
            json.dumps(top_features),
            iaao['cod'], iaao['prd'], iaao['prb'], iaao['median_ratio'],
            iaao['cod_ok'], iaao['prd_ok'], iaao['level_ok'],
        )

        # ── Persist run history (registro inmutable, no UPSERT) ──
        for model_type in ['ols', 'ridge', 'lasso', 'elastic_net']:
            res = results.get(model_type)
            if not res:
                continue
            m = res['metrics']
            coefs_for_history = {k: v for k, v in res['coefficients'].items() if k != 'intercept'}
            # Lasso active features (non-zero at CV alpha)
            lasso_active = None
            if model_type == 'lasso':
                lasso_active = json.dumps([
                    f for f in feature_names
                    if abs(float(res['coefficients'].get(f, 0))) > 1e-8
                ])
            try:
                await conn.execute("""
                    INSERT INTO iug.regression_run_history
                        (tipo_inmueble, model_type, n_samples,
                         trigger_reason,
                         r2, cv_rmse_mean, cv_rmse_std, cv_r2_mean, cv_r2_std,
                         rmse, mae, alpha, l1_ratio,
                         coefficients,
                         iaao_cod, iaao_prd, iaao_prb, iaao_median_ratio,
                         iaao_cod_ok, iaao_prd_ok, iaao_level_ok,
                         lasso_active_features,
                         consensus)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                            $14::jsonb,$15,$16,$17,$18,$19,$20,$21,$22::jsonb,$23::jsonb)
                """,
                    tipo_inmueble, model_type, n_samples,
                    trigger_reason,
                    m.get('r2'), m.get('cv_rmse_mean'), m.get('cv_rmse_std'),
                    m.get('cv_r2_mean'), m.get('cv_r2_std'),
                    m.get('rmse'), m.get('mae'),
                    m.get('alpha'), m.get('l1_ratio'),
                    json.dumps(coefs_for_history),
                    iaao['cod'], iaao['prd'], iaao['prb'], iaao['median_ratio'],
                    iaao['cod_ok'], iaao['prd_ok'], iaao['level_ok'],
                    lasso_active,
                    json.dumps(consensus) if model_type == 'ols' else None,
                )
            except Exception as e:
                logger.warning(f"Failed to insert run_history for {tipo_inmueble}/{model_type}: {e}")

    # ── Build summary ──
    cv_comparison = {}
    for name in ['ols', 'ridge', 'lasso', 'elastic_net']:
        if results.get(name):
            cv_comparison[name] = results[name]['metrics']['cv_rmse_mean']

    # Consensus: features con señal robusta (full o partial)
    robust_features = [
        {'feature': f, **{k: v for k, v in info.items() if k in ('label', 'consensus', 'partial_consensus', 'n_active', 'sign_agreement', 'multicollinearity_flag')}}
        for f, info in consensus.items()
        if info.get('partial_consensus')
    ]

    summary = {
        'n': n_samples,
        'r2_ols': r2_ols_val,
        'r2_ridge': r2_ridge_val,
        'r2_lasso': r2_lasso_val,
        'r2_elastic_net': r2_enet_val,
        'cv_mean_ols': cv_ols_val,
        'cv_rmse': cv_comparison,
        'best_model': best_model,
        'n_overpriced': n_over,
        'n_fair': n_fair,
        'n_underpriced': n_under,
        'iaao': iaao,
        'vif': results['ols']['metrics'].get('vif') if results.get('ols') else None,
        'consensus': robust_features,
        'spatial_cv': spatial_cv_result,
    }

    leakage_info = ""
    if spatial_cv_result and spatial_cv_result.get('leakage_flag'):
        leakage_info = f", LEAKAGE={spatial_cv_result['leakage_ratio']:+.1%}"

    logger.info(
        f"Regression {tipo_inmueble}: n={n_samples}, "
        f"best={best_model} (CV-RMSE={cv_comparison.get(best_model, '?')}), "
        f"IAAO COD={iaao['cod']:.1f}% PRD={iaao['prd']:.3f}"
        f"{leakage_info}"
    )

    return summary


# ─── Trigger logic ──────────────────────────────────────────
# Umbrales para auto-trigger post-DBSCAN
MIN_NEW_CLEAN = 27              # 3 × 9 features — minimo estadisticamente significativo
GROWTH_THRESHOLD = 0.10         # 10% crecimiento sobre N del ultimo entrenamiento
PSI_DRIFT_THRESHOLD = 0.20      # PSI >= 0.20 = drift significativo
IAAO_LEVEL_MARGIN = 0.87        # mas estricto que el 0.90 del IAAO para trigger temprano


async def should_retrain(conn) -> dict:
    """
    Evalua si se debe re-entrenar la regresion post-DBSCAN.
    Implementa el framework de 4 capas (N-sample + PSI + IAAO + growth).
    Devuelve {'trigger': bool, 'reasons': list, 'new_clean': int}
    """
    reasons = []

    # ── Capa 1: contar nuevos is_outlier=FALSE desde el ultimo entrenamiento ──
    last_train = await conn.fetchval("""
        SELECT MAX(trained_at) FROM iug.regression_run_history
    """)
    # Quitar timezone para comparar con ultima_vista (timestamp without tz)
    if last_train is not None and hasattr(last_train, 'replace'):
        last_train = last_train.replace(tzinfo=None)

    if last_train is None:
        # Nunca se ha entrenado: trigger inmediato si hay suficientes datos
        new_clean = await conn.fetchval("""
            SELECT COUNT(*) FROM iug.inmueble
            WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
        """)
        if new_clean >= MIN_SAMPLES:
            reasons.append(f'primer_entrenamiento ({new_clean} registros limpios)')
        return {'trigger': bool(reasons), 'reasons': reasons, 'new_clean': int(new_clean or 0)}

    new_clean = await conn.fetchval("""
        SELECT COUNT(*) FROM iug.inmueble
        WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
          AND ultima_vista > $1
    """, last_train) or 0

    if new_clean < MIN_NEW_CLEAN:
        return {
            'trigger': False,
            'reasons': [],
            'new_clean': int(new_clean),
            'message': f'Solo {new_clean} nuevos registros limpios (minimo {MIN_NEW_CLEAN})',
        }

    # ── Capa 2: crecimiento >= 10% por tipo ──
    growth_triggered = await conn.fetchval("""
        SELECT EXISTS (
            SELECT tipo_inmueble
            FROM iug.inmueble
            WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
            GROUP BY tipo_inmueble
            HAVING COUNT(*) >= (
                SELECT COALESCE(h.n_samples * (1 + $1), $2)
                FROM iug.regression_run_history h
                WHERE h.tipo_inmueble = iug.inmueble.tipo_inmueble
                  AND h.model_type = 'ols'
                ORDER BY h.trained_at DESC LIMIT 1
            )
        )
    """, GROWTH_THRESHOLD, MIN_SAMPLES)

    if growth_triggered:
        reasons.append(f'crecimiento_muestra ({int(new_clean)} nuevos, >{int(GROWTH_THRESHOLD*100)}%)')

    # ── Capa 3: PSI sobre estrato y area (datos post-DBSCAN vs ultimo entrenamiento) ──
    # Comparamos distribucion de estrato entre todos los datos de entrenamiento previo
    # y los nuevos datos (scraped_at > last_train)
    try:
        train_rows = await conn.fetch("""
            SELECT estrato, area_construida FROM iug.inmueble
            WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
              AND ultima_vista <= $1
            LIMIT 5000
        """, last_train)

        new_rows = await conn.fetch("""
            SELECT estrato, area_construida FROM iug.inmueble
            WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
              AND ultima_vista > $1
        """, last_train)

        if train_rows and new_rows:
            train_estrato = np.array([float(r['estrato']) for r in train_rows if r['estrato']])
            new_estrato = np.array([float(r['estrato']) for r in new_rows if r['estrato']])
            train_area = np.array([float(r['area_construida']) for r in train_rows if r['area_construida']])
            new_area = np.array([float(r['area_construida']) for r in new_rows if r['area_construida']])

            psi_estrato = _compute_psi(train_estrato, new_estrato) if len(new_estrato) >= 5 else 0.0
            psi_area = _compute_psi(train_area, new_area) if len(new_area) >= 5 else 0.0

            if psi_estrato >= PSI_DRIFT_THRESHOLD:
                reasons.append(f'psi_estrato={psi_estrato:.3f} (drift)')
            if psi_area >= PSI_DRIFT_THRESHOLD:
                reasons.append(f'psi_area={psi_area:.3f} (drift)')
    except Exception as e:
        logger.warning(f"PSI check failed: {e}")

    # ── Capa 4: IAAO sobre datos nuevos con el modelo actual ──
    # (solo si hay modelo previo y suficientes datos nuevos)
    if new_clean >= MIN_SAMPLES:
        try:
            iaao_rows = await conn.fetch("""
                SELECT rp.actual_precio_m2, rp.predicted_precio_m2
                FROM iug.regression_prediction rp
                JOIN iug.inmueble i ON i.id_inmueble = rp.id_inmueble
                WHERE i.ultima_vista > $1
                  AND rp.actual_precio_m2 > 0 AND rp.predicted_precio_m2 > 0
                LIMIT 500
            """, last_train)

            if len(iaao_rows) >= 10:
                actual = np.array([float(r['actual_precio_m2']) for r in iaao_rows])
                predicted = np.array([float(r['predicted_precio_m2']) for r in iaao_rows])
                iaao_check = _compute_iaao(actual, predicted)
                if not iaao_check['level_ok'] or iaao_check['cod'] > 20:
                    reasons.append(
                        f"iaao_drift (ratio_med={iaao_check['median_ratio']}, COD={iaao_check['cod']}%)"
                    )
        except Exception as e:
            logger.warning(f"IAAO trigger check failed: {e}")

    return {
        'trigger': bool(reasons),
        'reasons': reasons,
        'new_clean': int(new_clean),
    }


async def train_all_models(conn, admin_id: int = None, trigger_reason: str = 'manual'):
    """Train regression models for all property types with sufficient data."""
    tipos = await conn.fetch("""
        SELECT tipo_inmueble, COUNT(*) AS n
        FROM iug.inmueble
        WHERE is_outlier = FALSE AND precio > 0 AND area_construida > 0
        GROUP BY tipo_inmueble
        HAVING COUNT(*) >= $1
        ORDER BY n DESC
    """, MIN_SAMPLES)

    resultados = {}
    for row in tipos:
        tipo = row['tipo_inmueble']
        try:
            summary = await _train_for_type(conn, tipo, trigger_reason)
            if summary:
                resultados[tipo] = summary
        except Exception as e:
            logger.error(f"Regression failed for {tipo}: {e}", exc_info=True)
            resultados[tipo] = {'error': 'Error interno en el entrenamiento del modelo'}

    return {
        'tipos_entrenados': len([r for r in resultados.values() if 'error' not in r]),
        'resultados': resultados,
    }
