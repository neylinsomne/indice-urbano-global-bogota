"""
Tests de normalidad sobre subindices del IUG y residuos del modelo
hedónico log-lineal — complemento a iurb_validation.py.

Tres pruebas estándar:
  - Shapiro-Wilk          (sensible a muestras pequeñas; H0: normal)
  - D'Agostino & Pearson  (combina skew + kurtosis; H0: normal)
  - Anderson-Darling      (más sensible en colas)
  - Jarque-Bera           (asintótico; H0: normal)
  - Kolmogorov-Smirnov    (vs normal estandarizada)

Para muestras grandes (n > 5000) Shapiro pierde sentido (rechaza
prácticamente siempre por sensibilidad), así que reportamos también
skewness, kurtosis y QQ-stats que son interpretables sin H0.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import psycopg2
from scipy import stats


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "postgres"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


def fetch_subindex_data(conn) -> Dict[str, np.ndarray]:
    """Carga los 5 subíndices del IUG sobre inmuebles bogotanos."""
    cols = ["iurb", "iacc", "iseg", "ihed", "idot", "ipnu"]
    out: Dict[str, np.ndarray] = {}
    with conn.cursor() as cur:
        for col in cols:
            cur.execute(f"""
                SELECT {col}
                FROM iug.inmueble
                WHERE {col} IS NOT NULL AND iurb IS NOT NULL
            """)
            out[col] = np.array([r[0] for r in cur.fetchall()], dtype=float)
    return out


def fetch_residuals(conn) -> np.ndarray:
    """
    Residuos del modelo hedónico log-lineal:
        log(precio) ~ const + iurb + log(area) + habs + banos + estrato
    Calcula coeficientes vía OLS y devuelve los residuos.
    """
    query = """
    SELECT
        LN(i.precio)::float       AS log_p,
        i.iurb::float             AS iurb,
        LN(i.area_construida)::float AS log_a,
        i.habitaciones::float     AS hab,
        i.banos::float            AS ban,
        COALESCE(i.estrato, 3)::float AS est
    FROM iug.inmueble i
    WHERE i.iurb IS NOT NULL
      AND i.precio BETWEEN 50000000 AND 5000000000
      AND i.area_construida BETWEEN 20 AND 1500
      AND i.habitaciones BETWEEN 0 AND 10
      AND i.banos BETWEEN 1 AND 10
    """
    with conn.cursor() as cur:
        cur.execute(query)
        data = np.array(cur.fetchall(), dtype=float)

    if len(data) < 100:
        return np.array([])

    y = data[:, 0]
    X = np.column_stack([np.ones(len(data)), data[:, 1:]])
    # OLS cerrado
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ beta
    return y - y_hat


def normality_battery(name: str, x: np.ndarray) -> Dict[str, Any]:
    """Aplica todas las pruebas, devuelve dict con resultados."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20:
        return {"name": name, "n": n, "error": "muestra_insuficiente"}

    out: Dict[str, Any] = {
        "name": name,
        "n": n,
        "media":     float(np.mean(x)),
        "mediana":   float(np.median(x)),
        "desv_est":  float(np.std(x, ddof=1)),
        "skewness":  float(stats.skew(x)),
        "kurtosis":  float(stats.kurtosis(x)),  # excess kurtosis (0 = normal)
    }

    # Shapiro-Wilk: scipy limita a n <= 5000 por exactitud
    if n <= 5000:
        sw_stat, sw_p = stats.shapiro(x)
        out["shapiro"] = {"W": float(sw_stat), "p_value": float(sw_p),
                          "rechaza_H0_normal": bool(sw_p < 0.05)}
    else:
        # Muestreo aleatorio de 4000 para Shapiro indicativo
        rng = np.random.default_rng(42)
        sample = rng.choice(x, size=4000, replace=False)
        sw_stat, sw_p = stats.shapiro(sample)
        out["shapiro"] = {"W": float(sw_stat), "p_value": float(sw_p),
                          "rechaza_H0_normal": bool(sw_p < 0.05),
                          "_nota": f"muestreado n=4000 (original n={n})"}

    # D'Agostino-Pearson
    if n >= 20:
        da_stat, da_p = stats.normaltest(x)
        out["dagostino"] = {"stat": float(da_stat), "p_value": float(da_p),
                            "rechaza_H0_normal": bool(da_p < 0.05)}

    # Jarque-Bera
    jb_stat, jb_p = stats.jarque_bera(x)
    out["jarque_bera"] = {"stat": float(jb_stat), "p_value": float(jb_p),
                          "rechaza_H0_normal": bool(jb_p < 0.05)}

    # Anderson-Darling (no devuelve p exacto, sino niveles críticos)
    ad = stats.anderson(x, dist="norm")
    out["anderson_darling"] = {
        "stat": float(ad.statistic),
        "critical_values": list(map(float, ad.critical_values)),
        "significance_levels": list(map(float, ad.significance_level)),
        "rechaza_5pct": bool(ad.statistic > ad.critical_values[2]),
    }

    # Kolmogorov-Smirnov contra normal estandarizada (con params estimados)
    x_std = (x - np.mean(x)) / np.std(x, ddof=1)
    ks_stat, ks_p = stats.kstest(x_std, "norm")
    out["ks_normal"] = {"stat": float(ks_stat), "p_value": float(ks_p),
                        "rechaza_H0_normal": bool(ks_p < 0.05)}

    # Veredicto compacto: mayoría de tests rechaza H0?
    rechazos = sum(1 for k in ("shapiro", "dagostino", "jarque_bera", "ks_normal")
                   if k in out and out[k].get("rechaza_H0_normal"))
    out["veredicto"] = {
        "rechazos_de_4": rechazos,
        "interpretacion": (
            "claramente_no_normal" if rechazos >= 3 else
            "marginalmente_no_normal" if rechazos == 2 else
            "compatible_con_normal_o_inconcluso"
        ),
        "_nota_n_grande": (
            "Con n>5000 los tests rechazan H0 incluso ante desviaciones "
            "irrelevantes. Para interpretación práctica usar skewness/kurtosis "
            "y QQ-plot." if n > 5000 else None
        ),
    }
    return out


def main():
    print("=" * 80)
    print("TESTS DE NORMALIDAD · INMU / IUG")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    print("=" * 80)

    conn = get_conn()

    # Subíndices
    subi = fetch_subindex_data(conn)
    results: List[Dict[str, Any]] = []

    for name, x in subi.items():
        print(f"\n── {name.upper()} (n={len(x)}) ──")
        r = normality_battery(name, x)
        results.append(r)
        if "error" in r:
            print(f"   ERROR: {r['error']}")
            continue
        print(f"   media={r['media']:.3f}  mediana={r['mediana']:.3f}  σ={r['desv_est']:.3f}")
        print(f"   skewness={r['skewness']:+.3f}  kurtosis_exceso={r['kurtosis']:+.3f}")
        if "shapiro" in r:
            sw = r["shapiro"]
            print(f"   Shapiro-Wilk     W={sw['W']:.4f}  p={sw['p_value']:.2e}  rechaza={sw['rechaza_H0_normal']}")
        jb = r["jarque_bera"]
        print(f"   Jarque-Bera      stat={jb['stat']:.1f}  p={jb['p_value']:.2e}  rechaza={jb['rechaza_H0_normal']}")
        ad = r["anderson_darling"]
        print(f"   Anderson-Darling A²={ad['stat']:.3f}  crit_5%={ad['critical_values'][2]:.3f}  rechaza={ad['rechaza_5pct']}")
        ks = r["ks_normal"]
        print(f"   K-S vs Normal    D={ks['stat']:.4f}  p={ks['p_value']:.2e}  rechaza={ks['rechaza_H0_normal']}")
        v = r["veredicto"]
        print(f"   → {v['rechazos_de_4']}/4 tests rechazan H0  · {v['interpretacion']}")

    # Residuos hedónicos
    print("\n── RESIDUOS DEL MODELO HEDÓNICO log-lineal ──")
    res = fetch_residuals(conn)
    if len(res) > 0:
        r = normality_battery("residuos_hedonicos", res)
        results.append(r)
        print(f"   n={r['n']}  media={r['media']:.4f}  σ={r['desv_est']:.4f}")
        print(f"   skewness={r['skewness']:+.3f}  kurtosis_exceso={r['kurtosis']:+.3f}")
        jb = r["jarque_bera"]
        print(f"   Jarque-Bera  stat={jb['stat']:.1f}  p={jb['p_value']:.2e}  rechaza={jb['rechaza_H0_normal']}")
        ad = r["anderson_darling"]
        print(f"   Anderson-Darling A²={ad['stat']:.3f}  crit_5%={ad['critical_values'][2]:.3f}")
        v = r["veredicto"]
        print(f"   → {v['rechazos_de_4']}/4 rechazan · {v['interpretacion']}")
    else:
        print("   muestra_insuficiente")

    conn.close()

    # Persistencia
    out_path = Path("/tmp/normality_results.json")
    out_path.write_text(json.dumps(results, default=str, indent=2, ensure_ascii=False))
    print(f"\n[OK] Resultados crudos: {out_path}")


if __name__ == "__main__":
    main()
