"""Smoke test: ejecuta las 3 funciones de validación con datos sintéticos."""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from analytics.iurb_validation import (
    compare_nested_models,
    commonality_analysis,
    ranking_stability_mc,
    validar_iurb_completo,
)


def _generar(n_inmuebles=500, n_zonas=20, seed=7):
    rng = np.random.default_rng(seed)

    iacc = rng.uniform(0, 5, n_inmuebles)
    iseg = rng.uniform(0, 5, n_inmuebles)
    idot = rng.uniform(0, 5, n_inmuebles)
    ihed = rng.uniform(0, 5, n_inmuebles)
    ipnu = rng.uniform(0, 5, n_inmuebles)
    iug = 0.2 * (iacc + iseg + idot + ihed + ipnu)

    area = rng.uniform(40, 200, n_inmuebles)
    habs = rng.integers(1, 5, n_inmuebles).astype(float)
    banos = rng.integers(1, 4, n_inmuebles).astype(float)
    estrato = rng.integers(1, 7, n_inmuebles).astype(float)

    log_precio = (
        17.0 + 0.20 * iug + 0.08 * iseg + 0.006 * area + 0.20 * estrato
        + rng.normal(0, 0.3, n_inmuebles)
    )

    data_inm = {
        "log_precio": log_precio, "iug": iug,
        "iacc": iacc, "iseg": iseg, "idot": idot, "ihed": ihed, "ipnu": ipnu,
        "area_construida": area, "habitaciones": habs,
        "banos": banos, "estrato": estrato,
    }

    data_zonas = {
        "id_zona": np.arange(n_zonas).astype(float),
        "iacc": rng.uniform(1, 4, n_zonas),
        "iseg": rng.uniform(1, 4, n_zonas),
        "idot": rng.uniform(1, 4, n_zonas),
        "ihed": rng.uniform(1, 4, n_zonas),
        "ipnu": rng.uniform(1, 4, n_zonas),
    }
    return data_inm, data_zonas


def main():
    data_inm, data_zonas = _generar()

    print("=" * 70, "\nP1. COMPARACIÓN DE MODELOS ANIDADOS\n" + "=" * 70)
    r1 = compare_nested_models(data_inm)
    print(f"  n = {r1['n']}")
    print(f"  R²  reducido={r1['modelo_reducido']['r2']:.4f}  "
          f"completo={r1['modelo_completo']['r2']:.4f}  ΔR²={r1['delta_r2']:+.4f}")
    print(f"  ΔAIC={r1['delta_aic']:+.2f}   LRT χ²={r1['lrt']['stat']:.2f}"
          f" p={r1['lrt']['pvalue']:.4f}")
    print(f"  Veredicto: {r1['veredicto']}")
    print(f"  → {r1['interpretacion']}\n")

    print("=" * 70, "\nP2. COMMONALITY ANALYSIS\n" + "=" * 70)
    r2 = commonality_analysis(data_inm)
    print(f"  R² total = {r2['r2_total']:.4f}    Varianza común = {r2['pct_comun']:.1f}%")
    for item in r2["por_indicador"]:
        print(f"    {item['indicador']:6s}: único={item['varianza_unica']:.4f}  "
              f"({item['pct_unica']:.1f}%)")
    print(f"  Veredicto: {r2['veredicto']}")
    print(f"  → {r2['interpretacion']}\n")

    print("=" * 70, "\nP3. ESTABILIDAD DE RANKING (Monte Carlo)\n" + "=" * 70)
    r3 = ranking_stability_mc(data_zonas, n_sim=500)
    print(f"  Zonas={r3['n_zonas']}  Sim={r3['n_simulaciones']}")
    print(f"  Spearman mediana={r3['spearman']['mediana']:.3f} "
          f"[{r3['spearman']['p5']:.3f}, {r3['spearman']['p95']:.3f}]")
    print(f"  % zonas que cambian >5 pos: "
          f"{r3['pct_zonas_que_cambian_mas_de_umbral']['mediana']:.1f}%")
    print(f"  Veredicto: {r3['veredicto']}")
    print(f"  → {r3['interpretacion']}\n")

    print("=" * 70, "\nTABLA DE DECISIÓN FINAL\n" + "=" * 70)
    res = validar_iurb_completo(data_inm, data_zonas)
    for f in res["tabla_resumen"]:
        print(f"  [{f['estado']:7s}] {f['prueba']:35s} = {str(f['valor']):>8}  "
              f"(umbral OK: {f['umbral_ok']})")
    print(f"\n  VEREDICTO GLOBAL: {res['veredicto_global']}")
    print(f"  {res['mensaje_global']}")


if __name__ == "__main__":
    main()
