"""Refits hedonic models cleanly for the thesis Cap 4.6 tables.

Why this exists: the production train_all_models pipeline fails on Apartamento
with a numeric overflow because 5 scraping records have prices > 10^10 COP.
This script runs a clean fit on a winsorised slice (50M < precio < 5B,
25 m2 <= area <= 600 m2) so the thesis tables reflect a defensible baseline
without touching production schema.

Run inside iug-postgres ⟂ docker exec api-inmobiliario python /app-scripts/refit_hedonic_v2.py
"""
import asyncio
import json

import asyncpg
import numpy as np
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.model_selection import KFold, cross_val_score
from sklearn.preprocessing import StandardScaler

import os

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:CHANGEME@iug-postgres:5432/postgres",
)
BASE_NAMES = ["log_area", "habitaciones", "banos", "estrato"]
SUB_NAMES = ["iacc", "iseg", "ihed", "idot", "ipnu"]


async def fetch(tipo):
    conn = await asyncpg.connect(DSN)
    try:
        return await conn.fetch(
            """
            SELECT precio, area_construida, habitaciones, banos, estrato,
                   iacc, iseg, ihed, idot, ipnu, iurb
            FROM iug.inmueble
            WHERE tipo_inmueble = $1
              AND id_localidad IS NOT NULL
              AND precio IS NOT NULL AND precio > 50e6 AND precio < 5e9
              AND area_construida IS NOT NULL AND area_construida BETWEEN 25 AND 600
              AND habitaciones BETWEEN 1 AND 8 AND banos BETWEEN 1 AND 8
              AND estrato BETWEEN 1 AND 6
              AND iurb IS NOT NULL AND iacc IS NOT NULL AND iseg IS NOT NULL
              AND ihed IS NOT NULL AND idot IS NOT NULL AND ipnu IS NOT NULL
            """,
            tipo,
        )
    finally:
        await conn.close()


def train(rows, label):
    if not rows:
        return {"label": label, "n": 0}

    y = np.log(np.array([float(r["precio"]) / float(r["area_construida"]) for r in rows]))
    X_base = np.array(
        [
            [
                np.log(float(r["area_construida"])),
                int(r["habitaciones"]),
                int(r["banos"]),
                int(r["estrato"]),
            ]
            for r in rows
        ]
    )
    X_iug = np.column_stack([X_base, [float(r["iurb"]) for r in rows]])
    X_sub = np.column_stack(
        [
            X_base,
            [
                [float(r["iacc"]), float(r["iseg"]), float(r["ihed"]), float(r["idot"]), float(r["ipnu"])]
                for r in rows
            ],
        ]
    )

    out = {"label": label, "n": len(rows)}
    estimators = [
        ("ols", LinearRegression()),
        ("ridge", Ridge(alpha=1.0)),
        ("lasso", Lasso(alpha=0.001, max_iter=10000)),
        ("enet", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=10000)),
    ]
    for spec, X in [("M0", X_base), ("M1", X_iug), ("B", X_sub)]:
        Xs = StandardScaler().fit_transform(X)
        for name, est in estimators:
            est.fit(Xs, y)
            r2 = est.score(Xs, y)
            try:
                cv = cross_val_score(
                    est, Xs, y, cv=KFold(5, shuffle=True, random_state=42), scoring="r2"
                )
                out[f"{spec}_{name}"] = [round(float(r2), 4), round(float(cv.mean()), 4)]
            except Exception:
                out[f"{spec}_{name}"] = [round(float(r2), 4), None]

    # Best M1 coefs (standardised) for top features table
    best_est = Ridge(alpha=1.0)
    Xs_iug = StandardScaler().fit_transform(X_iug)
    best_est.fit(Xs_iug, y)
    coefs = best_est.coef_
    names = BASE_NAMES + ["iurb"]
    abs_coefs = np.abs(coefs)
    total = abs_coefs.sum() or 1.0
    pct = (abs_coefs / total) * 100
    feats = sorted(
        [{"feature": n, "coef": round(float(c), 4), "pct": round(float(p), 1)} for n, c, p in zip(names, coefs, pct)],
        key=lambda d: -abs(d["coef"]),
    )
    out["top_features_M1_ridge"] = feats

    # IAAO on M5 (M0 + log_area already there + interaction estrato*log_area)
    Xs_base = StandardScaler().fit_transform(X_base)
    yhat = LinearRegression().fit(Xs_base, y).predict(Xs_base)
    pred_pm2 = np.exp(yhat)
    obs_pm2 = np.exp(y)
    ratios = pred_pm2 / obs_pm2
    out["IAAO_M0"] = {
        "median_ratio": round(float(np.median(ratios)), 4),
        "cod_pct": round(float(np.median(np.abs(ratios - np.median(ratios))) / np.median(ratios) * 100), 2),
        "prd": round(float(np.mean(ratios) / (np.sum(pred_pm2) / np.sum(obs_pm2))), 4),
    }
    return out


async def main():
    for tipo in ["Apartamento", "Casa"]:
        rows = await fetch(tipo)
        print(json.dumps(train(rows, tipo), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
