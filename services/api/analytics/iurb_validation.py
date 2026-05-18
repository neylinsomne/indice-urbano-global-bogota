"""
Validación del IUG como indicador compuesto suficiente vs subindicadores.

Tres preguntas centrales (Nardo et al., 2008; OECD/JRC handbook):

P1. ¿El IUG agregado predice el precio igual de bien que los subindicadores sueltos?
    → Comparación de modelos anidados (F-test, AIC, BIC, LRT)
    → Commonality analysis (descomposición de varianza)

P2. ¿Los subindicadores son compensatorios (Munda, 2008)?
    → Implícito en P1: si un subindicador aporta ΔR² significativo más allá
      del IUG, rompe la compensatoriedad.

P3. ¿El ranking de zonas con IUG es estable frente a perturbación de pesos?
    → Monte Carlo sobre pesos ± delta, correlación Spearman y % de zonas
      que cambian más de k posiciones.

Dependencias: numpy, scipy (sin pandas/statsmodels para mantener
consistencia con los requirements del proyecto).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Utilidades OLS (numpy puro)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class _OLSFit:
    n: int
    k: int              # regresores sin intercepto
    r2: float
    r2_adj: float
    ssr: float          # suma cuadrados residuales
    sst: float
    loglik: float       # log-verosimilitud (MLE normal)
    aic: float
    bic: float
    df_model: int       # grados de libertad del modelo (k)


def _ols_fit(X: np.ndarray, y: np.ndarray, add_const: bool = True) -> _OLSFit:
    """OLS mediante lstsq (más estable que inversa explícita)."""
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    n = X.shape[0]
    k = X.shape[1]
    Xd = np.column_stack([np.ones(n), X]) if add_const else X

    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta

    ssr = float(np.sum(resid ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ssr / sst if sst > 0 else 0.0
    r2_adj = 1.0 - (1.0 - r2) * (n - 1) / max(n - k - 1, 1)

    sigma2 = ssr / n if n > 0 else float("nan")
    if sigma2 > 0:
        loglik = -0.5 * n * (math.log(2 * math.pi) + math.log(sigma2) + 1.0)
    else:
        loglik = float("nan")

    num_params = k + 2  # k coefs + intercepto + σ²
    aic = -2 * loglik + 2 * num_params
    bic = -2 * loglik + num_params * math.log(n) if n > 0 else float("nan")

    return _OLSFit(n, k, r2, r2_adj, ssr, sst, loglik, aic, bic, df_model=k)


def _extract(data: dict, cols: Sequence[str]) -> np.ndarray:
    """Construye una matriz (n, k) a partir de dict[col] -> array."""
    return np.column_stack([np.asarray(data[c], dtype=float) for c in cols])


def _filter_valid(data: dict, cols: Sequence[str]) -> dict:
    """Elimina filas donde cualquier columna es NaN/None."""
    arrs = {c: np.asarray(data[c], dtype=float) for c in cols}
    mask = np.ones(len(next(iter(arrs.values()))), dtype=bool)
    for a in arrs.values():
        mask &= ~np.isnan(a)
    return {c: arrs[c][mask] for c in cols}


# ═══════════════════════════════════════════════════════════════════
# Prueba 1: COMPARACIÓN DE MODELOS ANIDADOS
# ═══════════════════════════════════════════════════════════════════

def compare_nested_models(
    data: dict,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
) -> dict:
    """
    Compara:
        A (reducido):  y ~ IUG + controles
        B (completo):  y ~ sub1 + ... + subK + controles

    `data` debe ser un dict col_name -> array/lista de valores.
    """
    from scipy import stats as sp_stats

    cols_all = [y_col, iug_col, *sub_cols, *control_cols]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 30:
        return {"error": f"Muestra insuficiente (n={n}, mínimo 30)"}

    y = clean[y_col]

    mod_red = _ols_fit(_extract(clean, [iug_col, *control_cols]), y, True)
    mod_full = _ols_fit(_extract(clean, [*sub_cols, *control_cols]), y, True)

    delta_r2 = mod_full.r2 - mod_red.r2
    delta_r2_adj = mod_full.r2_adj - mod_red.r2_adj
    delta_aic = mod_full.aic - mod_red.aic
    delta_bic = mod_full.bic - mod_red.bic

    lrt_stat = 2 * (mod_full.loglik - mod_red.loglik)
    lrt_df = mod_full.df_model - mod_red.df_model
    lrt_pvalue = float(sp_stats.chi2.sf(lrt_stat, lrt_df)) if lrt_df > 0 else 1.0

    df_num = mod_full.df_model - mod_red.df_model
    df_den = n - mod_full.df_model - 1
    if df_num > 0 and df_den > 0 and mod_full.ssr > 0:
        f_stat = ((mod_red.ssr - mod_full.ssr) / df_num) / (mod_full.ssr / df_den)
        f_pvalue = float(sp_stats.f.sf(f_stat, df_num, df_den))
    else:
        f_stat, f_pvalue = float("nan"), float("nan")

    if delta_r2 < 0.02 and delta_aic > -10:
        veredicto = "iug_suficiente"
        interp = (
            f"El IUG captura la mayor parte de la señal del precio "
            f"(ΔR²={delta_r2:.3f} < 0.02; ΔAIC={delta_aic:+.1f} > -10). "
            f"Usar el índice agregado no pierde información sustantiva."
        )
    elif delta_r2 > 0.05 or delta_aic < -20:
        veredicto = "subindicadores_dominan"
        interp = (
            f"Los subindicadores por separado explican sustancialmente más varianza "
            f"(ΔR²={delta_r2:.3f}; ΔAIC={delta_aic:+.1f} < -20). "
            f"El IUG pierde información y NO debería usarse como único predictor."
        )
    else:
        veredicto = "subindicadores_aportan"
        interp = (
            f"Los subindicadores aportan información marginal al IUG "
            f"(ΔR²={delta_r2:.3f}; ΔAIC={delta_aic:+.1f}). "
            f"El IUG es útil como síntesis, pero reportar también los subindicadores."
        )

    return {
        "n": int(n),
        "modelo_reducido": {
            "formula": f"{y_col} ~ {iug_col} + {'+'.join(control_cols)}",
            "r2": float(mod_red.r2),
            "r2_adj": float(mod_red.r2_adj),
            "aic": float(mod_red.aic),
            "bic": float(mod_red.bic),
            "df_model": int(mod_red.df_model),
        },
        "modelo_completo": {
            "formula": f"{y_col} ~ {'+'.join(sub_cols)} + {'+'.join(control_cols)}",
            "r2": float(mod_full.r2),
            "r2_adj": float(mod_full.r2_adj),
            "aic": float(mod_full.aic),
            "bic": float(mod_full.bic),
            "df_model": int(mod_full.df_model),
        },
        "delta_r2": float(delta_r2),
        "delta_r2_adj": float(delta_r2_adj),
        "delta_aic": float(delta_aic),
        "delta_bic": float(delta_bic),
        "lrt": {"stat": float(lrt_stat), "df": int(lrt_df), "pvalue": float(lrt_pvalue)},
        "f_test": {
            "stat": float(f_stat),
            "df_num": int(df_num),
            "df_den": int(df_den),
            "pvalue": float(f_pvalue),
        },
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 2: COMMONALITY ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def commonality_analysis(
    data: dict,
    y_col: str = "log_precio",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
) -> dict:
    """
    Descompone R² total en:
      - Varianza ÚNICA de cada subindicador (R²_total - R²(todos sin i))
      - Varianza COMÚN entre subindicadores (R²_total - Σ únicas)

    Interpretación (Nimon & Oswald, 2013):
      pct_común > 70%  → un IUG agregado es buena síntesis
      pct_común 40-70% → IUG aceptable, reportar subindicadores con mayor aporte único
      pct_común < 40%  → subindicadores ortogonales: un IUG oculta información
    """
    cols_all = [y_col, *sub_cols]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 30:
        return {"error": f"Muestra insuficiente (n={n}, mínimo 30)"}

    y = clean[y_col]

    def _r2(cols: Sequence[str]) -> float:
        if not cols:
            return 0.0
        X = _extract(clean, cols)
        return _ols_fit(X, y, add_const=True).r2

    r2_total = _r2(list(sub_cols))

    # Varianza única SIN clipping: valores negativos indican efecto supresor
    # (el sub-indicador correlaciona con el error de los demás). Se clipean a
    # 0 para interpretación, pero se expone n_supresores para que el usuario
    # sepa que pct_comun puede estar inflado artificialmente.
    varianza_unica_raw = {}
    for ind in sub_cols:
        r2_sin_i = _r2([c for c in sub_cols if c != ind])
        varianza_unica_raw[ind] = r2_total - r2_sin_i

    n_supresores = sum(1 for v in varianza_unica_raw.values() if v < 0)
    varianza_unica = {k: max(0.0, v) for k, v in varianza_unica_raw.items()}

    total_unica = sum(varianza_unica.values())
    varianza_comun = max(0.0, r2_total - total_unica)

    if r2_total > 0:
        pct_unica = {k: v / r2_total * 100 for k, v in varianza_unica.items()}
        pct_comun = varianza_comun / r2_total * 100
    else:
        pct_unica = {k: 0.0 for k in sub_cols}
        pct_comun = 0.0

    # Flag de confiabilidad: si hay supresores, el pct_comun está sesgado al
    # alza (Nimon & Oswald 2013, §3.2). El método approximado por eliminación
    # requiere commonality completo (2^k subconjuntos) para ser exacto.
    interpretacion_confiable = n_supresores == 0

    if pct_comun > 70 and interpretacion_confiable:
        veredicto = "iug_es_buena_sintesis"
        interp = (
            f"El {pct_comun:.0f}% de la varianza explicada es COMÚN entre los "
            f"subindicadores. El IUG es una buena síntesis."
        )
    elif pct_comun > 40 and interpretacion_confiable:
        veredicto = "iug_aceptable_con_complemento"
        interp = (
            f"El {pct_comun:.0f}% de la varianza es común. El IUG funciona como "
            f"resumen, pero conviene reportar también los subindicadores con "
            f"mayor aporte único."
        )
    elif not interpretacion_confiable:
        veredicto = "supresion_detectada"
        interp = (
            f"{n_supresores} de {len(sub_cols)} subindicadores muestran efecto "
            f"supresor (varianza única negativa). El pct_comun={pct_comun:.0f}% "
            f"puede estar sesgado al alza por colinealidad. Ejecutar "
            f"commonality completo (2^k subconjuntos) para interpretación "
            f"definitiva (Nimon & Oswald, 2013)."
        )
    else:
        veredicto = "subindicadores_ortogonales"
        interp = (
            f"Solo el {pct_comun:.0f}% de la varianza es común; el resto es "
            f"aporte único de cada subindicador. El IUG agregado OCULTA "
            f"información relevante."
        )

    ranking = sorted(
        [{
            "indicador": k,
            "varianza_unica": float(varianza_unica[k]),
            "varianza_unica_raw": float(varianza_unica_raw[k]),  # puede ser <0
            "pct_unica": float(pct_unica[k]),
            "es_supresor": varianza_unica_raw[k] < 0,
         } for k in sub_cols],
        key=lambda x: -x["varianza_unica"],
    )

    return {
        "n": int(n),
        "r2_total": float(r2_total),
        "varianza_comun": float(varianza_comun),
        "pct_comun": float(pct_comun),
        "total_varianza_unica": float(total_unica),
        "por_indicador": ranking,
        "n_supresores": int(n_supresores),
        "interpretacion_confiable": bool(interpretacion_confiable),
        "metodo": "commonality_aproximado_por_eliminacion",
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 3: ESTABILIDAD DE RANKINGS (Monte Carlo)
# ═══════════════════════════════════════════════════════════════════

def ranking_stability_mc(
    data_zonas: dict,
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    zone_col: str = "id_zona",
    pesos_base: Optional[Sequence[float]] = None,
    delta: float = 0.20,
    n_sim: int = 1000,
    umbral_cambio_posiciones: int = 5,
    random_state: int = 42,
) -> dict:
    """
    Estabilidad del ranking de zonas ante perturbación ± delta de los pesos.

    Umbrales OECD (Nardo et al., 2008):
      ρ_Spearman > 0.90 y < 10% de zonas cambian >umbral posiciones → robusto.
    """
    from scipy import stats as sp_stats

    clean = _filter_valid(data_zonas, [zone_col, *sub_cols])
    n_zonas = len(clean[zone_col])
    if n_zonas < 10:
        return {"error": f"Muy pocas zonas (n={n_zonas}, mínimo 10)"}

    K = len(sub_cols)
    if pesos_base is None:
        pesos_base = [1.0 / K] * K
    pesos_base = np.asarray(pesos_base, dtype=float)
    pesos_base = pesos_base / pesos_base.sum()

    X = _extract(clean, list(sub_cols))

    iug_base = X @ pesos_base
    orden_base = np.argsort(-iug_base)
    rank_base = np.empty(n_zonas, dtype=int)
    rank_base[orden_base] = np.arange(1, n_zonas + 1)

    rng = np.random.default_rng(random_state)
    spearmans = np.empty(n_sim)
    cambios = np.empty(n_sim)

    for i in range(n_sim):
        low = pesos_base * (1 - delta)
        high = pesos_base * (1 + delta)
        w = rng.uniform(low, high)
        w = w / w.sum()

        iug_p = X @ w
        orden_p = np.argsort(-iug_p)
        rank_p = np.empty(n_zonas, dtype=int)
        rank_p[orden_p] = np.arange(1, n_zonas + 1)

        # scipy >= 1.9 renombra .correlation -> .statistic; indexar por posicion es portable
        spearmans[i] = float(sp_stats.spearmanr(rank_base, rank_p)[0])
        cambios[i] = float(np.mean(np.abs(rank_base - rank_p) > umbral_cambio_posiciones))

    spearman_med = float(np.median(spearmans))
    spearman_p5 = float(np.percentile(spearmans, 5))
    spearman_p95 = float(np.percentile(spearmans, 95))
    pct_cambios_med = float(np.median(cambios)) * 100

    if spearman_med > 0.90 and pct_cambios_med < 10:
        veredicto = "ranking_robusto"
        interp = (
            f"Rankings estables: ρ_Spearman mediana = {spearman_med:.3f} (>0.90 OECD) "
            f"y solo {pct_cambios_med:.1f}% de zonas se mueven más de "
            f"{umbral_cambio_posiciones} posiciones bajo perturbación ±{int(delta*100)}%."
        )
    elif spearman_med > 0.80:
        veredicto = "ranking_aceptable"
        interp = (
            f"Estabilidad moderada: ρ_Spearman = {spearman_med:.3f}, "
            f"{pct_cambios_med:.1f}% de zonas se desplazan >{umbral_cambio_posiciones} "
            f"posiciones. Reportar intervalos de confianza del ranking."
        )
    else:
        veredicto = "ranking_fragil"
        interp = (
            f"Rankings FRÁGILES: ρ_Spearman = {spearman_med:.3f} (<0.80), "
            f"{pct_cambios_med:.1f}% de zonas cambian posición >{umbral_cambio_posiciones}. "
            f"Los pesos del IUG deben re-calibrarse."
        )

    return {
        "n_zonas": int(n_zonas),
        "n_simulaciones": int(n_sim),
        "delta_pct": float(delta * 100),
        "umbral_cambio_posiciones": int(umbral_cambio_posiciones),
        "pesos_base": pesos_base.tolist(),
        "spearman": {"mediana": spearman_med, "p5": spearman_p5, "p95": spearman_p95},
        "pct_zonas_que_cambian_mas_de_umbral": {
            "mediana": pct_cambios_med,
            "p5": float(np.percentile(cambios, 5)) * 100,
            "p95": float(np.percentile(cambios, 95)) * 100,
        },
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 4: CROSS-VALIDATION ESPACIAL (contrasta R² in-sample)
# ═══════════════════════════════════════════════════════════════════

def cv_comparison(
    data: dict,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    group_col: str = "id_localidad",
    n_splits: int = 5,
    random_state: int = 42,
) -> dict:
    """
    Compara R² in-sample vs R² CV aleatorio vs R² CV espacial
    para ambos modelos (reducido con IUG y completo con subindicadores).

    El 'leakage espacial' ocurre cuando vecinos caen en folds distintos:
    infla el R² aleatorio. El R² espacial es el honesto para datos geo.

    Returns
    -------
    dict con r2 in-sample, cv aleatorio, cv espacial y flag de leakage.
    """
    from sklearn.model_selection import KFold, GroupKFold
    from sklearn.linear_model import LinearRegression

    cols_all = [y_col, iug_col, *sub_cols, *control_cols, group_col]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    groups = clean[group_col].astype(int)
    unique_groups = np.unique(groups)
    n_groups = len(unique_groups)

    def _cv_r2(X, cv_iter):
        r2s = []
        for tr, te in cv_iter:
            if len(tr) < 10 or len(te) < 5:
                continue
            m = LinearRegression()
            m.fit(X[tr], y[tr])
            r2s.append(m.score(X[te], y[te]))
        return float(np.mean(r2s)) if r2s else float("nan"), \
               float(np.std(r2s)) if len(r2s) > 1 else 0.0

    def _evaluar(X):
        # In-sample (equivalente a lo ya visto)
        r2_in = _ols_fit(X, y, add_const=True).r2

        # CV aleatorio
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        cv_rnd = list(kf.split(X))
        r2_rnd, r2_rnd_std = _cv_r2(X, cv_rnd)

        # CV espacial (grupos = localidades)
        n_sp = min(n_splits, n_groups)
        if n_sp < 2:
            r2_sp, r2_sp_std = float("nan"), 0.0
        else:
            gkf = GroupKFold(n_splits=n_sp)
            cv_spatial = list(gkf.split(X, y, groups=groups))
            r2_sp, r2_sp_std = _cv_r2(X, cv_spatial)

        # Leakage ratio: (R²_rnd - R²_sp) / R²_sp
        leakage = (r2_rnd - r2_sp) / abs(r2_sp) if r2_sp and not np.isnan(r2_sp) else float("nan")

        return {
            "r2_in_sample": float(r2_in),
            "r2_cv_aleatorio": float(r2_rnd),
            "r2_cv_aleatorio_std": float(r2_rnd_std),
            "r2_cv_espacial": float(r2_sp),
            "r2_cv_espacial_std": float(r2_sp_std),
            "leakage_ratio": float(leakage),
        }

    X_red = _extract(clean, [iug_col, *control_cols])
    X_full = _extract(clean, [*sub_cols, *control_cols])
    res_red = _evaluar(X_red)
    res_full = _evaluar(X_full)

    delta_spatial = res_full["r2_cv_espacial"] - res_red["r2_cv_espacial"]
    delta_rnd = res_full["r2_cv_aleatorio"] - res_red["r2_cv_aleatorio"]

    # Interpretación
    if abs(res_full.get("leakage_ratio", 0)) > 0.15:
        leakage_msg = (
            "Se detecta leakage espacial >15%: el CV aleatorio infla el R² porque "
            "vecinos caen en folds distintos. El R² espacial es la referencia honesta."
        )
        leakage_flag = True
    else:
        leakage_msg = "No hay leakage espacial significativo."
        leakage_flag = False

    if delta_spatial > 0.02:
        veredicto = "subindicadores_ganan_fuera_muestra"
    elif delta_spatial < -0.02:
        veredicto = "iug_gana_fuera_muestra"
    else:
        veredicto = "empate_fuera_muestra"

    return {
        "n": int(n),
        "n_grupos_espaciales": int(n_groups),
        "n_splits": int(n_splits),
        "modelo_reducido": res_red,
        "modelo_completo": res_full,
        "delta_r2_cv_aleatorio": float(delta_rnd),
        "delta_r2_cv_espacial": float(delta_spatial),
        "leakage_espacial": leakage_flag,
        "mensaje_leakage": leakage_msg,
        "veredicto": veredicto,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 5: BOOTSTRAP IC de R² y ΔAIC
# ═══════════════════════════════════════════════════════════════════

def bootstrap_r2_aic(
    data: dict,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    n_boot: int = 1000,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> dict:
    """
    Intervalos de confianza bootstrap (percentil) para:
      - R² de modelo reducido y completo
      - ΔR² (completo - reducido)
      - ΔAIC (completo - reducido)

    Si IC95(ΔR²) incluye 0 → la diferencia no es significativa.
    Si IC95(ΔAIC) incluye 0 → AIC no distingue entre modelos.
    """
    cols_all = [y_col, iug_col, *sub_cols, *control_cols]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    X_red = _extract(clean, [iug_col, *control_cols])
    X_full = _extract(clean, [*sub_cols, *control_cols])

    rng = np.random.default_rng(random_state)
    alpha = (1 - ci_level) / 2

    r2_red_boot = np.empty(n_boot)
    r2_full_boot = np.empty(n_boot)
    aic_red_boot = np.empty(n_boot)
    aic_full_boot = np.empty(n_boot)

    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        f_red = _ols_fit(X_red[idx], y[idx], add_const=True)
        f_full = _ols_fit(X_full[idx], y[idx], add_const=True)
        r2_red_boot[i] = f_red.r2
        r2_full_boot[i] = f_full.r2
        aic_red_boot[i] = f_red.aic
        aic_full_boot[i] = f_full.aic

    delta_r2_boot = r2_full_boot - r2_red_boot
    delta_aic_boot = aic_full_boot - aic_red_boot

    # Filtrar NaN: AIC puede ser NaN si un remuestreo produce SSR=0 (muestra
    # degenerada). Propagar NaN al IC daría falsos positivos porque
    # np.quantile(nan) = nan y la comparación nan <= 0 <= nan es False,
    # haciendo que sig_* evalúe True por accidente.
    def _ci(arr):
        clean = arr[~np.isnan(arr)]
        n_valid = int(clean.size)
        n_dropped = int(arr.size - n_valid)
        if n_valid < max(10, arr.size // 2):
            return {
                "media": float("nan"), "mediana": float("nan"),
                "ic_low": float("nan"), "ic_high": float("nan"),
                "n_valid": n_valid, "n_dropped": n_dropped,
                "warning": "Muestra bootstrap válida insuficiente (<50%)",
            }
        return {
            "media": float(np.mean(clean)),
            "mediana": float(np.median(clean)),
            "ic_low": float(np.quantile(clean, alpha)),
            "ic_high": float(np.quantile(clean, 1 - alpha)),
            "n_valid": n_valid, "n_dropped": n_dropped,
        }

    ci_dr2 = _ci(delta_r2_boot)
    ci_daic = _ci(delta_aic_boot)

    # ΔR² significativo si IC no incluye 0 (y el IC es computable)
    def _excluye_cero(ci: dict) -> bool:
        lo, hi = ci["ic_low"], ci["ic_high"]
        if np.isnan(lo) or np.isnan(hi):
            return False
        return not (lo <= 0 <= hi)

    sig_dr2 = _excluye_cero(ci_dr2)
    sig_daic = _excluye_cero(ci_daic)

    if sig_dr2 and sig_daic:
        veredicto = "diferencia_significativa"
        interp = (
            f"Con {int(ci_level*100)}% confianza, el modelo completo es "
            f"significativamente mejor. IC ΔR² = [{ci_dr2['ic_low']:.4f}, "
            f"{ci_dr2['ic_high']:.4f}] y IC ΔAIC = [{ci_daic['ic_low']:.1f}, "
            f"{ci_daic['ic_high']:.1f}] — ambos excluyen el cero."
        )
    else:
        veredicto = "diferencia_no_significativa"
        interp = (
            f"El IC incluye cero. La diferencia entre modelos puede ser azar."
        )

    return {
        "n": int(n),
        "n_bootstrap": int(n_boot),
        "ci_level": float(ci_level),
        "r2_reducido": _ci(r2_red_boot),
        "r2_completo": _ci(r2_full_boot),
        "delta_r2": ci_dr2,
        "delta_aic": ci_daic,
        "delta_r2_significativo": bool(sig_dr2),
        "delta_aic_significativo": bool(sig_daic),
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 6: RAMSEY RESET (validez de la forma funcional)
# ═══════════════════════════════════════════════════════════════════

def ramsey_reset(
    data: dict,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    potencias: Sequence[int] = (2, 3),
) -> dict:
    """
    Test de Ramsey RESET para forma funcional:
      H0: modelo está bien especificado (forma funcional correcta)
      H1: faltan términos no lineales / interacciones

    Método: añade ŷ², ŷ³ como regresores y prueba significancia conjunta.
    Si p < 0.05 → la forma funcional es insuficiente; faltan términos.
    """
    from scipy import stats as sp_stats

    cols_all = [y_col, iug_col, *sub_cols, *control_cols]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]

    def _reset_test(X):
        """Test RESET para un modelo dado."""
        # Modelo base
        f0 = _ols_fit(X, y, add_const=True)
        # Predicciones
        Xd = np.column_stack([np.ones(len(y)), X])
        beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
        yhat = Xd @ beta

        # Añadir potencias de yhat
        extras = np.column_stack([yhat ** p for p in potencias])
        X_aug = np.column_stack([X, extras])
        f1 = _ols_fit(X_aug, y, add_const=True)

        df_num = len(potencias)
        df_den = n - f1.df_model - 1
        if df_num > 0 and df_den > 0 and f1.ssr > 0:
            f_stat = ((f0.ssr - f1.ssr) / df_num) / (f1.ssr / df_den)
            p_val = float(sp_stats.f.sf(f_stat, df_num, df_den))
        else:
            f_stat, p_val = float("nan"), float("nan")

        return {
            "f_stat": float(f_stat),
            "df_num": int(df_num),
            "df_den": int(df_den),
            "pvalue": float(p_val),
            "rechaza_H0": bool(p_val < 0.05),
        }

    X_red = _extract(clean, [iug_col, *control_cols])
    X_full = _extract(clean, [*sub_cols, *control_cols])

    res_red = _reset_test(X_red)
    res_full = _reset_test(X_full)

    # Interpretación
    if res_red["rechaza_H0"] and res_full["rechaza_H0"]:
        veredicto = "ambos_mal_especificados"
        interp = (
            "Ambos modelos muestran formas funcionales insuficientes (p<0.05). "
            "Considerar transformaciones log, términos cuadráticos o interacciones."
        )
    elif res_full["rechaza_H0"]:
        veredicto = "completo_mal_especificado"
        interp = "El modelo completo tiene forma funcional insuficiente."
    elif res_red["rechaza_H0"]:
        veredicto = "reducido_mal_especificado"
        interp = "El modelo reducido (solo IUG) tiene forma funcional insuficiente."
    else:
        veredicto = "ambos_bien_especificados"
        interp = "Las formas funcionales son adecuadas (no se rechaza H0)."

    return {
        "n": int(n),
        "potencias_usadas": list(potencias),
        "modelo_reducido": res_red,
        "modelo_completo": res_full,
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 7: R² POR SUBGRUPOS (heterogeneidad del modelo)
# ═══════════════════════════════════════════════════════════════════

def subgroup_r2(
    data: dict,
    group_col: str,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    min_n_grupo: int = 50,
) -> dict:
    """
    Calcula R² del modelo reducido y completo por subgrupo
    (ej. tipo de inmueble o localidad).

    Si la varianza del R² entre subgrupos es alta → el modelo funciona
    muy distinto según el subgrupo (heterogeneidad no modelada).
    """
    cols_all = [y_col, iug_col, *sub_cols, *control_cols, group_col]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    groups = clean[group_col]
    unique_groups = np.unique(groups)

    resultados = []
    for g in unique_groups:
        mask = groups == g
        n_g = int(mask.sum())
        if n_g < min_n_grupo:
            continue
        y_g = y[mask]
        X_red_g = _extract({k: clean[k][mask] for k in [iug_col, *control_cols]},
                           [iug_col, *control_cols])
        X_full_g = _extract({k: clean[k][mask] for k in [*sub_cols, *control_cols]},
                            [*sub_cols, *control_cols])
        try:
            r2_red_g = _ols_fit(X_red_g, y_g, add_const=True).r2
            r2_full_g = _ols_fit(X_full_g, y_g, add_const=True).r2
        except Exception:
            continue

        resultados.append({
            "grupo": float(g) if isinstance(g, (int, float, np.integer, np.floating)) else str(g),
            "n": n_g,
            "r2_reducido": float(r2_red_g),
            "r2_completo": float(r2_full_g),
            "delta_r2": float(r2_full_g - r2_red_g),
        })

    if not resultados:
        return {"error": f"Ningún subgrupo con n >= {min_n_grupo}"}

    r2_reds = np.array([r["r2_reducido"] for r in resultados])
    r2_fulls = np.array([r["r2_completo"] for r in resultados])
    deltas = np.array([r["delta_r2"] for r in resultados])

    # Coeficiente de variación del R² como medida de heterogeneidad
    cv_red = float(np.std(r2_reds) / np.mean(r2_reds)) if np.mean(r2_reds) > 0 else float("nan")
    cv_full = float(np.std(r2_fulls) / np.mean(r2_fulls)) if np.mean(r2_fulls) > 0 else float("nan")

    if cv_full > 0.30:
        veredicto = "alta_heterogeneidad"
        interp = (
            f"El R² del modelo completo varía mucho entre grupos "
            f"(CV={cv_full:.2f}). El modelo funciona de manera heterogénea; "
            f"considerar modelos por subgrupo o interacciones."
        )
    elif cv_full > 0.15:
        veredicto = "heterogeneidad_moderada"
        interp = f"Heterogeneidad moderada entre grupos (CV={cv_full:.2f})."
    else:
        veredicto = "modelo_homogeneo"
        interp = f"El modelo funciona de manera homogénea entre grupos (CV={cv_full:.2f})."

    resultados.sort(key=lambda x: -x["n"])

    return {
        "n_total": int(n),
        "n_grupos": len(resultados),
        "grupo_col": group_col,
        "min_n_grupo": min_n_grupo,
        "por_grupo": resultados,
        "r2_reducido": {
            "media": float(np.mean(r2_reds)),
            "min": float(np.min(r2_reds)),
            "max": float(np.max(r2_reds)),
            "cv": cv_red,
        },
        "r2_completo": {
            "media": float(np.mean(r2_fulls)),
            "min": float(np.min(r2_fulls)),
            "max": float(np.max(r2_fulls)),
            "cv": cv_full,
        },
        "delta_r2_promedio": float(np.mean(deltas)),
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Prueba 8: COMPARACIÓN DE ESPECIFICACIONES FUNCIONALES
# ═══════════════════════════════════════════════════════════════════

def improve_specification(
    data: dict,
    y_col: str = "log_precio",
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    area_col: str = "area_construida",
) -> dict:
    """
    Compara varias especificaciones funcionales para encontrar la mejor:

    M1. Base OLS lineal (referencia)
    M2. + log(area)  — no-linealidad en el tamaño
    M3. + cuadráticos de indicadores (iseg², ihed²)
    M4. + interacciones clave (iseg×estrato, ihed×área, iacc×idot)
    M5. Todo combinado (M2 + M3 + M4)

    Para cada modelo reporta R², R²_adj, AIC, BIC, Ramsey RESET p-value.
    Identifica la especificación ganadora.
    """
    from scipy import stats as sp_stats

    cols_all = [y_col, *sub_cols, *control_cols, area_col]
    clean = _filter_valid(data, cols_all)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    base_cols = list(sub_cols) + list(control_cols)
    X_base = _extract(clean, base_cols)

    # Features derivadas
    area = clean[area_col]
    log_area = np.log(np.maximum(area, 1.0))
    iseg_sq = clean["iseg"] ** 2
    ihed_sq = clean["ihed"] ** 2
    iseg_x_estrato = clean["iseg"] * clean["estrato"]
    ihed_x_area = clean["ihed"] * area
    iacc_x_idot = clean["iacc"] * clean["idot"]

    specs = {
        "M1_base": X_base,
        "M2_log_area": np.column_stack([X_base, log_area]),
        "M3_cuadraticos": np.column_stack([X_base, iseg_sq, ihed_sq]),
        "M4_interacciones": np.column_stack([X_base, iseg_x_estrato, ihed_x_area, iacc_x_idot]),
        "M5_completa": np.column_stack([
            X_base, log_area, iseg_sq, ihed_sq,
            iseg_x_estrato, ihed_x_area, iacc_x_idot,
        ]),
    }

    def _ramsey(X):
        f0 = _ols_fit(X, y, add_const=True)
        Xd = np.column_stack([np.ones(n), X])
        beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
        yhat = Xd @ beta
        extras = np.column_stack([yhat ** 2, yhat ** 3])
        f1 = _ols_fit(np.column_stack([X, extras]), y, add_const=True)
        df_num = 2
        df_den = n - f1.df_model - 1
        if df_num > 0 and df_den > 0 and f1.ssr > 0:
            fstat = ((f0.ssr - f1.ssr) / df_num) / (f1.ssr / df_den)
            pval = float(sp_stats.f.sf(fstat, df_num, df_den))
        else:
            pval = float("nan")
        return pval

    resultados = []
    for nombre, X in specs.items():
        fit = _ols_fit(X, y, add_const=True)
        ramsey_p = _ramsey(X)
        resultados.append({
            "modelo": nombre,
            "n_features": int(X.shape[1]),
            "r2": float(fit.r2),
            "r2_adj": float(fit.r2_adj),
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "ramsey_pvalue": float(ramsey_p),
            "ramsey_ok": bool(ramsey_p > 0.05),
        })

    # El mejor según R² ajustado
    mejor_r2adj = max(resultados, key=lambda r: r["r2_adj"])
    # El mejor según AIC (menor es mejor)
    mejor_aic = min(resultados, key=lambda r: r["aic"])
    # El primero que pasa Ramsey (si alguno pasa)
    mejor_ramsey = next(
        (r for r in sorted(resultados, key=lambda r: -r["r2_adj"]) if r["ramsey_ok"]),
        None,
    )

    # Comparar con M1 (ΔR², ΔAIC respecto a la base)
    base = resultados[0]
    for r in resultados:
        r["delta_r2_vs_base"] = round(r["r2"] - base["r2"], 4)
        r["delta_aic_vs_base"] = round(r["aic"] - base["aic"], 2)

    # Veredicto
    if mejor_ramsey and mejor_ramsey["modelo"] != "M1_base":
        veredicto = "especificacion_mejorable_y_especificada"
        interp = (
            f"La mejor especificación que cumple Ramsey es "
            f"{mejor_ramsey['modelo']} con R²={mejor_ramsey['r2']:.3f} "
            f"y ΔR² vs base = {mejor_ramsey['delta_r2_vs_base']:+.3f}."
        )
    elif mejor_aic["modelo"] != "M1_base":
        veredicto = "especificacion_mejorable_pero_mal_especificada"
        interp = (
            f"{mejor_aic['modelo']} mejora AIC en {mejor_aic['delta_aic_vs_base']:+.1f} "
            f"pero Ramsey sigue rechazando. Considerar modelos no paramétricos "
            f"(GAM, random forest) o interacciones adicionales."
        )
    else:
        veredicto = "base_es_la_mejor"
        interp = "El modelo base es la mejor especificación lineal posible."

    return {
        "n": int(n),
        "especificaciones": resultados,
        "mejor_r2_adj": mejor_r2adj["modelo"],
        "mejor_aic": mejor_aic["modelo"],
        "mejor_ramsey": mejor_ramsey["modelo"] if mejor_ramsey else None,
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# VALIDEZ DE USO: ¿el IUG sirve para DECISIONES DE INVERSIÓN?
# ═══════════════════════════════════════════════════════════════════
# Se abandona el enfoque predictivo. El indicador se juzga por:
#   - Capacidad de detectar sub/sobrevaloración (mispricing)
#   - Validez convergente con estrato y precio/m²
#   - Validez discriminante entre zonas (AUC, ANOVA)
#   - Utilidad operativa como matriz de decisión 2×2


def mispricing_analysis(
    data: dict,
    y_col: str = "log_precio",
    iug_col: str = "iug",
    hedonic_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
) -> dict:
    """
    Análisis de mispricing (Rosen 1974; Shiller 2015).

    1. Ajusta modelo hedónico con SOLO características físicas:
          log(precio) ~ área + habs + baños + estrato
    2. Residual = sobre/sub-valoración del mercado
    3. Correlación Spearman entre IUG y residuales:
          ρ < 0 → zonas con IUG alto están SUBVALORADAS → oportunidad
          ρ > 0 → zonas con IUG alto ya están 'priced-in' → sin alpha

    Complementa con test Mann-Whitney entre el cuartil superior e
    inferior del IUG para confirmar que la diferencia de residual
    entre ambos grupos es estadísticamente significativa.
    """
    from scipy import stats as sp_stats

    cols = [y_col, iug_col, *hedonic_cols]
    clean = _filter_valid(data, cols)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    iug = clean[iug_col]
    X = _extract(clean, hedonic_cols)

    # 1. Modelo hedónico base (SIN IUG ni subindicadores)
    Xd = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    yhat = Xd @ beta
    resid = y - yhat  # > 0: sobrevalorado ; < 0: subvalorado
    fit = _ols_fit(X, y, add_const=True)

    # 2. Correlación Spearman entre IUG y residual
    rho, p_spearman = sp_stats.spearmanr(iug, resid)

    # 3. Cuartiles del IUG
    q_iug = np.quantile(iug, [0.25, 0.50, 0.75])
    # Residual medio por cuartil del IUG
    cuartiles = []
    for i, (lo, hi, label) in enumerate([
        (-np.inf, q_iug[0], "Q1_IUG_bajo"),
        (q_iug[0], q_iug[1], "Q2"),
        (q_iug[1], q_iug[2], "Q3"),
        (q_iug[2], np.inf, "Q4_IUG_alto"),
    ]):
        mask = (iug > lo) & (iug <= hi) if i > 0 else (iug <= hi)
        if i == 3:
            mask = iug > lo
        r_g = resid[mask]
        cuartiles.append({
            "cuartil": label,
            "n": int(mask.sum()),
            "iug_medio": float(iug[mask].mean()) if mask.any() else float("nan"),
            "residual_medio": float(r_g.mean()) if mask.any() else float("nan"),
            "residual_mediana": float(np.median(r_g)) if mask.any() else float("nan"),
        })

    # 4. Mann-Whitney Q4 vs Q1 (residuales)
    mask_q1 = iug <= q_iug[0]
    mask_q4 = iug > q_iug[2]
    if mask_q1.sum() > 5 and mask_q4.sum() > 5:
        mw_stat, mw_p = sp_stats.mannwhitneyu(
            resid[mask_q4], resid[mask_q1], alternative="two-sided"
        )
        diff_medianas = float(np.median(resid[mask_q4]) - np.median(resid[mask_q1]))
    else:
        mw_stat, mw_p, diff_medianas = float("nan"), float("nan"), float("nan")

    # Veredicto
    if not np.isnan(rho):
        if rho < -0.05 and p_spearman < 0.05:
            veredicto = "iug_detecta_subvaloracion"
            interp = (
                f"IUG correlaciona NEGATIVAMENTE con residuales (ρ={rho:.3f}, "
                f"p={p_spearman:.4f}). Las zonas con IUG alto están SUBVALORADAS "
                f"por el mercado — el IUG sirve para detectar oportunidades de "
                f"inversión."
            )
        elif rho > 0.05 and p_spearman < 0.05:
            veredicto = "iug_refleja_valorizacion_ya_incorporada"
            interp = (
                f"IUG correlaciona POSITIVAMENTE con residuales (ρ={rho:.3f}). "
                f"Las zonas con IUG alto ya están sobrevaloradas; el mercado ya "
                f"incorpora la calidad urbana → el IUG NO genera alpha de "
                f"inversión, pero SÍ describe lo que el mercado paga por calidad."
            )
        else:
            veredicto = "sin_correlacion_con_mispricing"
            interp = (
                f"IUG no correlaciona significativamente con residuales "
                f"(ρ={rho:.3f}, p={p_spearman:.4f}). El indicador no aporta "
                f"información sobre mispricing — usarlo solo como medida de "
                f"calidad urbana, no de oportunidad financiera."
            )
    else:
        veredicto = "error"
        interp = "No se pudo calcular correlación."

    return {
        "n": int(n),
        "modelo_hedonico": {
            "formula": f"{y_col} ~ {'+'.join(hedonic_cols)}",
            "r2": float(fit.r2),
            "ssr": float(fit.ssr),
        },
        "spearman_iug_residual": {
            "rho": float(rho),
            "pvalue": float(p_spearman),
        },
        "cuartiles_iug": cuartiles,
        "mann_whitney_q4_vs_q1": {
            "diff_mediana_residuales": diff_medianas,
            "stat": float(mw_stat),
            "pvalue": float(mw_p),
        },
        "veredicto": veredicto,
        "interpretacion": interp,
    }


def convergent_validity(
    data: dict,
    iug_col: str = "iug",
    estrato_col: str = "estrato",
    precio_col: str = "precio",
    area_col: str = "area_construida",
) -> dict:
    """
    Validez convergente y discriminante:

    1. Correlación Spearman IUG ↔ estrato (validez convergente)
    2. ANOVA del IUG por estrato (¿discrimina entre estratos?)
    3. AUC del IUG como clasificador binario (estrato ≥ 4 vs estrato ≤ 3)
    4. Correlación Spearman IUG ↔ precio/m² (debe ser positiva pero no perfecta)
    """
    from scipy import stats as sp_stats
    from sklearn.metrics import roc_auc_score

    cols = [iug_col, estrato_col, precio_col, area_col]
    clean = _filter_valid(data, cols)
    n = len(clean[iug_col])
    if n < 100:
        return {"error": f"Muestra insuficiente (n={n})"}

    iug = clean[iug_col]
    estrato = clean[estrato_col]
    precio_m2 = clean[precio_col] / np.maximum(clean[area_col], 1.0)

    # 1. Spearman IUG vs estrato
    rho_estrato, p_estrato = sp_stats.spearmanr(iug, estrato)

    # 2. Spearman IUG vs precio/m²
    rho_precio, p_precio = sp_stats.spearmanr(iug, precio_m2)

    # 3. ANOVA del IUG por estrato
    grupos = []
    estrato_unicos = sorted(set(int(e) for e in estrato if not np.isnan(e)))
    for e in estrato_unicos:
        mask = estrato == e
        if mask.sum() >= 5:
            grupos.append(iug[mask])

    if len(grupos) >= 2:
        f_stat, p_anova = sp_stats.f_oneway(*grupos)
        # eta² = SS_between / SS_total
        grand_mean = iug.mean()
        ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in grupos)
        ss_total = float(np.sum((iug - grand_mean) ** 2))
        eta_sq = float(ss_between / ss_total) if ss_total > 0 else 0.0
    else:
        f_stat, p_anova, eta_sq = float("nan"), float("nan"), float("nan")

    # IUG medio por estrato
    iug_por_estrato = []
    for e in estrato_unicos:
        mask = estrato == e
        if mask.sum() >= 5:
            iug_por_estrato.append({
                "estrato": int(e),
                "n": int(mask.sum()),
                "iug_medio": float(iug[mask].mean()),
                "iug_std": float(iug[mask].std()),
            })

    # 4. AUC (estrato ≥ 4 = clase positiva)
    try:
        y_bin = (estrato >= 4).astype(int)
        if len(np.unique(y_bin)) == 2:
            auc = float(roc_auc_score(y_bin, iug))
        else:
            auc = float("nan")
    except Exception:
        auc = float("nan")

    # Veredicto
    ok_convergente = rho_estrato > 0.3 and p_estrato < 0.01
    ok_discriminante = (not np.isnan(eta_sq)) and eta_sq > 0.1
    ok_auc = (not np.isnan(auc)) and auc > 0.70

    if ok_convergente and ok_discriminante and ok_auc:
        veredicto = "validez_convergente_ok"
        interp = (
            f"El IUG tiene validez convergente (ρ con estrato = {rho_estrato:.3f}), "
            f"discriminante (η²={eta_sq:.3f}) y clasifica bien estratos altos "
            f"(AUC={auc:.3f}). Es una medida válida de calidad urbana."
        )
    elif ok_auc or ok_convergente:
        veredicto = "validez_parcial"
        interp = (
            f"Validez parcial: ρ_estrato={rho_estrato:.3f}, η²={eta_sq:.3f}, "
            f"AUC={auc:.3f}. El IUG aporta información pero no de forma uniforme."
        )
    else:
        veredicto = "validez_insuficiente"
        interp = (
            f"Validez débil: ρ_estrato={rho_estrato:.3f}, η²={eta_sq:.3f}, "
            f"AUC={auc:.3f}. El IUG no logra separar claramente estratos."
        )

    return {
        "n": int(n),
        "spearman_iug_estrato": {"rho": float(rho_estrato), "pvalue": float(p_estrato)},
        "spearman_iug_precio_m2": {"rho": float(rho_precio), "pvalue": float(p_precio)},
        "anova_por_estrato": {
            "f_stat": float(f_stat),
            "pvalue": float(p_anova),
            "eta_squared": float(eta_sq),
            "n_grupos": len(grupos),
        },
        "iug_por_estrato": iug_por_estrato,
        "auc_estrato_alto": auc,
        "veredicto": veredicto,
        "interpretacion": interp,
    }


def investment_decision_matrix(
    data: dict,
    iug_col: str = "iug",
    precio_col: str = "precio",
    area_col: str = "area_construida",
    hedonic_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    y_col: str = "log_precio",
) -> dict:
    """
    Matriz de decisión 2×2 (IUG × mispricing).

    Clasifica cada inmueble en 1 de 4 cuadrantes según:
      - IUG alto / bajo (mediana)
      - Residual hedónico positivo (sobrevalorado) / negativo (subvalorado)

    Cuadrantes:
      🟢 IUG_alto × subvalorado  → COMPRAR (calidad escondida)
      🟡 IUG_alto × sobrevalorado → CONSERVAR (priced-in)
      🟠 IUG_bajo × subvalorado  → EVITAR (barato por razón)
      🔴 IUG_bajo × sobrevalorado → VENDER (caro sin fundamentales)
    """
    from scipy import stats as sp_stats

    cols = [y_col, iug_col, precio_col, area_col, *hedonic_cols]
    clean = _filter_valid(data, cols)
    n = len(clean[y_col])
    if n < 50:
        return {"error": f"Muestra insuficiente (n={n})"}

    y = clean[y_col]
    iug = clean[iug_col]
    precio_m2 = clean[precio_col] / np.maximum(clean[area_col], 1.0)

    # Residual del modelo hedónico
    X = _extract(clean, hedonic_cols)
    Xd = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta

    # Thresholds: mediana IUG y residual = 0 (o mediana)
    iug_med = float(np.median(iug))
    resid_med = 0.0  # residual OLS ya centrado

    # Asignar cuadrantes
    mask_iug_alto = iug > iug_med
    mask_subval = resid < resid_med

    cuadrantes = {
        "🟢 COMPRAR (IUG alto + subvalorado)":
            mask_iug_alto & mask_subval,
        "🟡 CONSERVAR (IUG alto + sobrevalorado)":
            mask_iug_alto & ~mask_subval,
        "🟠 EVITAR (IUG bajo + subvalorado)":
            ~mask_iug_alto & mask_subval,
        "🔴 VENDER (IUG bajo + sobrevalorado)":
            ~mask_iug_alto & ~mask_subval,
    }

    filas = []
    for nombre, m in cuadrantes.items():
        if not m.any():
            continue
        filas.append({
            "cuadrante": nombre,
            "n": int(m.sum()),
            "pct": round(float(m.sum() / n * 100), 2),
            "iug_medio": float(iug[m].mean()),
            "precio_m2_medio": float(precio_m2[m].mean()),
            "residual_medio": float(resid[m].mean()),
            "precio_m2_vs_global_pct": round(
                float((precio_m2[m].mean() / precio_m2.mean() - 1) * 100), 2
            ),
        })

    # Test: ¿el precio/m² del cuadrante verde es menor que el del amarillo?
    verde = mask_iug_alto & mask_subval
    amarillo = mask_iug_alto & ~mask_subval
    if verde.sum() > 10 and amarillo.sum() > 10:
        ks_stat, ks_p = sp_stats.ks_2samp(precio_m2[verde], precio_m2[amarillo])
    else:
        ks_stat, ks_p = float("nan"), float("nan")

    # % en cuadrante verde (oportunidad)
    pct_verde = float(verde.sum() / n * 100)
    pct_rojo = float(((~mask_iug_alto) & (~mask_subval)).sum() / n * 100)

    if pct_verde > 15 and pct_rojo > 15:
        veredicto = "matriz_util_para_inversion"
        interp = (
            f"La matriz distribuye {pct_verde:.1f}% en cuadrante COMPRAR y "
            f"{pct_rojo:.1f}% en cuadrante VENDER. El IUG identifica "
            f"oportunidades concretas de arbitraje."
        )
    elif pct_verde + pct_rojo > 20:
        veredicto = "matriz_utilidad_moderada"
        interp = (
            f"Masa limitada en cuadrantes de decisión ({pct_verde + pct_rojo:.1f}% "
            f"en verde+rojo). El IUG sirve para filtrar, no para señalar alpha."
        )
    else:
        veredicto = "matriz_poco_util"
        interp = (
            "La mayoría de inmuebles cae en cuadrantes indecisos; el IUG no "
            "diferencia claramente entre oportunidades y riesgos."
        )

    return {
        "n": int(n),
        "iug_mediano": iug_med,
        "por_cuadrante": filas,
        "ks_test_verde_vs_amarillo": {
            "stat": float(ks_stat),
            "pvalue": float(ks_p),
        },
        "pct_cuadrante_comprar": pct_verde,
        "pct_cuadrante_vender": pct_rojo,
        "veredicto": veredicto,
        "interpretacion": interp,
    }


# ═══════════════════════════════════════════════════════════════════
# Interfaz unificada
# ═══════════════════════════════════════════════════════════════════

def validar_iurb_completo(
    data_inmuebles: dict,
    data_zonas: dict,
    sub_cols: Sequence[str] = ("iacc", "iseg", "idot", "ihed", "ipnu"),
    y_col: str = "log_precio",
    iug_col: str = "iug",
    control_cols: Sequence[str] = ("area_construida", "habitaciones", "banos", "estrato"),
    zone_col: str = "id_zona",
    pesos_base: Optional[Sequence[float]] = None,
) -> dict:
    """
    Ejecuta las 3 pruebas y construye la tabla de decisión final.
    """
    resultado = {
        "modelos_anidados": compare_nested_models(
            data_inmuebles, y_col, iug_col, sub_cols, control_cols
        ),
        "commonality": commonality_analysis(data_inmuebles, y_col, sub_cols),
        "estabilidad_ranking": ranking_stability_mc(
            data_zonas, sub_cols, zone_col, pesos_base
        ),
    }

    filas = []
    m = resultado["modelos_anidados"]
    if "error" not in m:
        filas.append({
            "prueba": "ΔR² (completo vs IUG)",
            "valor": round(m["delta_r2"], 4),
            "umbral_ok": "< 0.02",
            "estado": "OK" if m["delta_r2"] < 0.02 else ("REVISAR" if m["delta_r2"] < 0.05 else "FALLA"),
        })
        filas.append({
            "prueba": "ΔAIC",
            "valor": round(m["delta_aic"], 2),
            "umbral_ok": "> -10",
            "estado": "OK" if m["delta_aic"] > -10 else ("REVISAR" if m["delta_aic"] > -20 else "FALLA"),
        })

    c = resultado["commonality"]
    if "error" not in c:
        filas.append({
            "prueba": "Varianza común (%)",
            "valor": round(c["pct_comun"], 1),
            "umbral_ok": "> 70%",
            "estado": "OK" if c["pct_comun"] > 70 else ("REVISAR" if c["pct_comun"] > 40 else "FALLA"),
        })

    r = resultado["estabilidad_ranking"]
    if "error" not in r:
        filas.append({
            "prueba": "ρ Spearman ranking",
            "valor": round(r["spearman"]["mediana"], 3),
            "umbral_ok": "> 0.90",
            "estado": "OK" if r["spearman"]["mediana"] > 0.90 else ("REVISAR" if r["spearman"]["mediana"] > 0.80 else "FALLA"),
        })
        filas.append({
            "prueba": "% zonas que cambian >umbral",
            "valor": round(r["pct_zonas_que_cambian_mas_de_umbral"]["mediana"], 1),
            "umbral_ok": "< 10%",
            "estado": "OK" if r["pct_zonas_que_cambian_mas_de_umbral"]["mediana"] < 10 else ("REVISAR" if r["pct_zonas_que_cambian_mas_de_umbral"]["mediana"] < 20 else "FALLA"),
        })

    estados = [f["estado"] for f in filas]
    if all(e == "OK" for e in estados):
        veredicto_global = "iurb_confiable"
        mensaje = "El IUG es un indicador compuesto estadísticamente confiable."
    elif any(e == "FALLA" for e in estados):
        veredicto_global = "iurb_no_confiable"
        mensaje = "El IUG presenta problemas metodológicos; re-calibrar pesos o desagregar."
    else:
        veredicto_global = "iurb_aceptable_con_reservas"
        mensaje = "El IUG es útil como síntesis, pero reportar subindicadores con aporte único."

    resultado["tabla_resumen"] = filas
    resultado["veredicto_global"] = veredicto_global
    resultado["mensaje_global"] = mensaje
    return resultado
