"""
Genera las 5 gráficas P1 para la sustentación.

Guarda los PDFs en /tmp/figs dentro del container. Después se copian al
host con `docker cp api-inmobiliario:/tmp/figs/. Prueba/Inmu/figs/`.

Estilo visual consistente con la paleta INMU (verde + azul oscuro).
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sin display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import psycopg2
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats
from shapely import wkt
from shapely.geometry import MultiPolygon, Polygon


# ──────────────────── Paleta INMU ─────────────────────────────
INMU_GREEN      = "#15803D"
INMU_GREEN_LITE = "#22C55E"
INMU_PRIMARY    = "#0A2540"
INMU_MUTED      = "#64748B"
INMU_RED        = "#DC2626"
INMU_GREEN_GRAD = LinearSegmentedColormap.from_list(
    "inmu_green",
    ["#F0FDF4", "#86EFAC", "#22C55E", "#15803D", "#052E16"],
)

OUT_DIR = Path("/tmp/figs")
OUT_DIR.mkdir(exist_ok=True, parents=True)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "postgres"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


def _style():
    """Estilo común para todas las gráficas."""
    plt.rcParams.update({
        "font.family":      "sans-serif",
        "font.sans-serif":  ["DejaVu Sans"],
        "axes.titlesize":   11,
        "axes.labelsize":   10,
        "xtick.labelsize":  9,
        "ytick.labelsize":  9,
        "legend.fontsize":  9,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.edgecolor":    INMU_PRIMARY,
        "axes.labelcolor":   INMU_PRIMARY,
        "xtick.color":       INMU_PRIMARY,
        "ytick.color":       INMU_PRIMARY,
    })


# ════════════════════════════════════════════════════════════════════
# 1.1 — Histograma + densidad de los 5 subíndices (+ IUG global)
# ════════════════════════════════════════════════════════════════════

def fig_histograma_subindices(conn):
    print("[1/5] Generando hist_subindices.pdf …")
    df = pd.read_sql(
        """
        SELECT iurb, iacc, iseg, ihed, idot, ipnu
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
        """,
        conn,
    )

    sub_labels = {
        "iurb": "IUG global",
        "iacc": "Accesibilidad (I_ACC)",
        "iseg": "Seguridad (I_SEG)",
        "ihed": "Hedónico (I_HED)",
        "idot": "Dotación (I_DOT)",
        "ipnu": "Normativo (I_PNU)",
    }

    fig, axs = plt.subplots(2, 3, figsize=(11, 6.2))
    for ax, (col, label) in zip(axs.flat, sub_labels.items()):
        x = df[col].dropna().to_numpy()
        sns.histplot(
            x, bins=40, kde=True, ax=ax,
            color=INMU_GREEN, edgecolor="white", linewidth=0.4,
            line_kws={"color": INMU_PRIMARY, "linewidth": 1.4},
        )
        ax.axvline(np.mean(x), color=INMU_PRIMARY, linestyle="--", linewidth=1)
        ax.set_title(f"{label}\nμ={np.mean(x):.2f} · σ={np.std(x):.2f}", fontsize=10)
        ax.set_xlabel(""); ax.set_ylabel("")
        ax.set_xlim(0, 5)
    fig.suptitle(
        "Distribución de los 5 subíndices del IUG (n = 23 761 inmuebles bogotanos)",
        fontsize=12, color=INMU_PRIMARY, y=1.01,
    )
    plt.tight_layout()
    plt.savefig(OUT_DIR / "hist_subindices.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 1.2 — QQ-plot de residuos hedónicos
# ════════════════════════════════════════════════════════════════════

def fig_qq_residuos(conn):
    print("[2/5] Generando qq_residuos.pdf …")
    df = pd.read_sql(
        """
        SELECT LN(precio)::float AS log_p,
               iurb::float,
               LN(area_construida)::float AS log_a,
               habitaciones::float, banos::float,
               COALESCE(estrato, 3)::float AS estrato
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
          AND precio BETWEEN 50000000 AND 5000000000
          AND area_construida BETWEEN 20 AND 1500
          AND habitaciones BETWEEN 0 AND 10
          AND banos BETWEEN 1 AND 10
        """,
        conn,
    )
    y = df["log_p"].values
    X = np.column_stack([
        np.ones(len(df)), df["iurb"], df["log_a"],
        df["habitaciones"], df["banos"], df["estrato"],
    ])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))

    # QQ-plot
    stats.probplot(resid, dist="norm", plot=axs[0])
    axs[0].get_lines()[0].set_markerfacecolor(INMU_GREEN)
    axs[0].get_lines()[0].set_markeredgecolor(INMU_GREEN)
    axs[0].get_lines()[0].set_markersize(3.5)
    axs[0].get_lines()[1].set_color(INMU_PRIMARY)
    axs[0].get_lines()[1].set_linewidth(1.5)
    axs[0].set_title(
        f"QQ-plot residuos · kurtosis exc = {stats.kurtosis(resid):+.2f}",
        fontsize=11,
    )
    axs[0].set_xlabel("Cuantiles teóricos N(0,1)")
    axs[0].set_ylabel("Cuantiles empíricos")

    # Histograma de residuos con normal ajustada superpuesta
    sns.histplot(resid, bins=80, kde=False, ax=axs[1],
                 color=INMU_GREEN, edgecolor="white", linewidth=0.4,
                 stat="density")
    xs = np.linspace(resid.min(), resid.max(), 300)
    axs[1].plot(xs, stats.norm.pdf(xs, np.mean(resid), np.std(resid)),
                color=INMU_PRIMARY, linewidth=1.6, label="N(μ, σ²)")
    axs[1].set_title(
        f"Distribución de residuos · skew = {stats.skew(resid):+.2f}",
        fontsize=11,
    )
    axs[1].set_xlabel("Residuo log(precio) - log(precio)_hat")
    axs[1].set_ylabel("Densidad")
    axs[1].legend(frameon=False)
    axs[1].set_xlim(np.percentile(resid, 1), np.percentile(resid, 99))

    fig.suptitle(
        "Normalidad de residuos del modelo hedónico log-lineal (n = 11 539)",
        fontsize=12, color=INMU_PRIMARY, y=1.02,
    )
    plt.tight_layout()
    plt.savefig(OUT_DIR / "qq_residuos.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 1.3 — Mapa coroplético del IUG por localidad
# ════════════════════════════════════════════════════════════════════

def fig_mapa_coropletico(conn):
    print("[3/5] Generando mapa_iug_v2.pdf …")
    df = pd.read_sql(
        """
        SELECT l.nombre,
               ST_AsText(ST_Simplify(l.geom, 0.0005)) AS wkt,
               ROUND(AVG(i.iurb)::numeric, 2)::float AS iurb
        FROM iug.localidad l
        LEFT JOIN iug.inmueble i ON i.id_localidad = l.id_localidad
                                AND i.iurb IS NOT NULL
        GROUP BY l.id_localidad, l.nombre, l.geom
        """,
        conn,
    )

    fig, ax = plt.subplots(figsize=(8, 9))
    vmin, vmax = 0.0, 4.0
    norm = plt.Normalize(vmin=vmin, vmax=vmax)

    for _, row in df.iterrows():
        if not row["wkt"]:
            continue
        geom = wkt.loads(row["wkt"])
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        color = INMU_GREEN_GRAD(norm(row["iurb"] if row["iurb"] else 0))
        for poly in polys:
            x, y = poly.exterior.xy
            ax.fill(x, y, facecolor=color, edgecolor=INMU_PRIMARY,
                    linewidth=0.6, alpha=0.95)

        # Etiqueta sobre el centroide
        centroid = geom.centroid
        ax.text(centroid.x, centroid.y, row["nombre"].title(),
                fontsize=6.5, ha="center", va="center",
                color=INMU_PRIMARY,
                bbox=dict(boxstyle="round,pad=0.15", fc="white",
                          ec="none", alpha=0.7))

    ax.set_aspect("equal")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.set_title("IUG promedio por localidad · Bogotá D.C.\n"
                 "(corpus v2.0 · 23 761 inmuebles)",
                 fontsize=12, color=INMU_PRIMARY)
    ax.grid(alpha=0.2, linestyle=":")

    # Barra de color
    sm = plt.cm.ScalarMappable(cmap=INMU_GREEN_GRAD, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, shrink=0.5, pad=0.02)
    cbar.set_label("IUG promedio [0, 5]", color=INMU_PRIMARY)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "mapa_iug_v2.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 1.4 — Bar chart de POIs por categoría
# ════════════════════════════════════════════════════════════════════

def fig_poi_categorias(conn):
    print("[4/5] Generando poi_categorias.pdf …")
    df = pd.read_sql(
        """
        SELECT categoria, COUNT(*)::int AS n
        FROM iug.dotaciones_poi
        GROUP BY categoria
        ORDER BY n DESC
        """,
        conn,
    )

    # Etiqueta humana
    human = {
        "farmacia": "Farmacias", "colegio": "Colegios SED",
        "universidad": "Universidades", "ips": "IPS · Salud",
        "parque": "Parques IDRD", "teatro": "Teatros / Auditorios",
        "centro_comercial": "Centros comerciales",
        "biblioteca": "Bibliotecas BibloRed",
        "escenario_deportivo": "Escenarios deportivos",
        "plaza_mercado": "Plazas de mercado",
    }
    df["label"] = df["categoria"].map(lambda c: human.get(c, c))

    # Marcamos las nuevas vs originales con color (las que en v1.0 eran 0)
    nuevas = {"colegio", "universidad", "parque", "teatro", "escenario_deportivo"}
    colors = [INMU_GREEN if c in nuevas else INMU_MUTED for c in df["categoria"]]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(df["label"], df["n"], color=colors, edgecolor="white", linewidth=0.6)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Cantidad (escala log)")
    ax.set_title(f"Volumetría de POIs por categoría · v2.0 ({df['n'].sum():,} totales)",
                 fontsize=12, color=INMU_PRIMARY)
    for bar, n in zip(bars, df["n"]):
        ax.text(bar.get_width() * 1.05, bar.get_y() + bar.get_height() / 2,
                f"{n:,}", va="center", fontsize=9, color=INMU_PRIMARY)

    # Leyenda manual
    handles = [
        mpatches.Patch(color=INMU_GREEN, label="Cargadas en v2.0 (eran 0 en v1.0)"),
        mpatches.Patch(color=INMU_MUTED, label="Ya estaban en v1.0"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False)
    ax.set_xlim(right=df["n"].max() * 3)
    ax.grid(axis="x", alpha=0.25, linestyle=":")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "poi_categorias.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 1.5 — Cuadrante de decisión 2×2 (mispricing)
# ════════════════════════════════════════════════════════════════════

def fig_cuadrante_decisiones(conn):
    print("[5/5] Generando cuadrante_decisiones.pdf …")
    df = pd.read_sql(
        """
        SELECT LN(precio)::float AS log_p,
               iurb::float,
               LN(area_construida)::float AS log_a,
               habitaciones::float, banos::float,
               COALESCE(estrato, 3)::float AS estrato
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
          AND precio BETWEEN 50000000 AND 5000000000
          AND area_construida BETWEEN 20 AND 1500
          AND habitaciones BETWEEN 0 AND 10
          AND banos BETWEEN 1 AND 10
        """,
        conn,
    )
    y = df["log_p"].values
    X = np.column_stack([
        np.ones(len(df)), df["iurb"], df["log_a"],
        df["habitaciones"], df["banos"], df["estrato"],
    ])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    df["resid"] = y - X @ beta

    iurb_med = df["iurb"].median()
    df["cuadrante"] = "CONSERVAR"
    df.loc[(df["iurb"] >= iurb_med) & (df["resid"] < 0), "cuadrante"] = "COMPRAR"
    df.loc[(df["iurb"] <  iurb_med) & (df["resid"] > 0), "cuadrante"] = "VENDER"
    df.loc[(df["iurb"] <  iurb_med) & (df["resid"] < 0), "cuadrante"] = "EVITAR"

    pct = df["cuadrante"].value_counts(normalize=True) * 100

    palette = {
        "COMPRAR":   INMU_GREEN,
        "VENDER":    INMU_RED,
        "CONSERVAR": INMU_MUTED,
        "EVITAR":    INMU_PRIMARY,
    }
    fig, ax = plt.subplots(figsize=(8.5, 6))
    for cuad in ["EVITAR", "CONSERVAR", "VENDER", "COMPRAR"]:
        sub = df[df["cuadrante"] == cuad]
        ax.scatter(sub["resid"], sub["iurb"],
                   s=4, alpha=0.35, color=palette[cuad],
                   label=f"{cuad} · {pct.get(cuad, 0):.1f}%")
    ax.axhline(iurb_med, color=INMU_PRIMARY, linestyle="--", linewidth=1)
    ax.axvline(0,        color=INMU_PRIMARY, linestyle="--", linewidth=1)

    # Anotaciones por cuadrante
    ax.text(df["resid"].quantile(0.05),  4.7, "COMPRAR",
            color=INMU_GREEN, fontsize=14, fontweight="bold", ha="left")
    ax.text(df["resid"].quantile(0.95),  4.7, "CONSERVAR",
            color=INMU_MUTED, fontsize=14, fontweight="bold", ha="right")
    ax.text(df["resid"].quantile(0.05),  0.3, "EVITAR",
            color=INMU_PRIMARY, fontsize=14, fontweight="bold", ha="left")
    ax.text(df["resid"].quantile(0.95),  0.3, "VENDER",
            color=INMU_RED, fontsize=14, fontweight="bold", ha="right")

    ax.set_xlabel("Residual log(precio) - log(precio)_hat")
    ax.set_ylabel("IUG [0, 5]")
    ax.set_title(f"Cuadrante de decisión de mispricing · n={len(df):,}",
                 fontsize=12, color=INMU_PRIMARY)
    ax.legend(loc="lower right", frameon=False, markerscale=2.5)
    ax.set_ylim(0, 5)
    ax.set_xlim(df["resid"].quantile(0.02), df["resid"].quantile(0.98))
    ax.grid(alpha=0.2, linestyle=":")

    plt.tight_layout()
    plt.savefig(OUT_DIR / "cuadrante_decisiones.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
# 2.1 — Scree plot del PCA hedónico
# ════════════════════════════════════════════════════════════════════

def fig_scree_pca(conn):
    print("[6/9] Generando scree_ihed.pdf …")
    df = pd.read_sql(
        """
        SELECT area_construida::float AS area,
               habitaciones::float AS hab,
               banos::float AS ban,
               COALESCE(garajes, 0)::float AS gar,
               COALESCE(estrato, 3)::float AS est
        FROM iug.inmueble
        WHERE area_construida BETWEEN 20 AND 1500
          AND habitaciones BETWEEN 0 AND 10
          AND banos BETWEEN 1 AND 10
          AND iurb IS NOT NULL
        """,
        conn,
    )
    # Limpieza: drop NaN + remover columnas con varianza 0
    df = df.dropna()
    df = df.loc[:, df.std(ddof=1) > 1e-9]
    # Estandarización Z
    X = ((df - df.mean()) / df.std(ddof=1)).to_numpy()

    # PCA vía SVD
    cov = np.cov(X, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = eigvals[::-1]  # mayor a menor
    var_ratio = eigvals / eigvals.sum()
    cumvar = np.cumsum(var_ratio)

    fig, ax1 = plt.subplots(figsize=(8.5, 5))
    n = len(eigvals)
    xs = np.arange(1, n + 1)
    ax1.bar(xs, eigvals, color=INMU_GREEN, edgecolor="white",
            linewidth=0.7, alpha=0.85)
    ax1.plot(xs, eigvals, color=INMU_PRIMARY, marker="o",
             linewidth=1.4, markersize=7, markerfacecolor="white",
             markeredgewidth=1.6)
    ax1.axhline(1.0, color=INMU_RED, linestyle="--", linewidth=1.2,
                label="Regla de Kaiser (λ > 1)")
    for i, v in enumerate(eigvals):
        ax1.text(i + 1, v + 0.05, f"{v:.2f}", ha="center", fontsize=9,
                 color=INMU_PRIMARY)
    ax1.set_xlabel("Componente")
    ax1.set_ylabel("Eigenvalue λ", color=INMU_PRIMARY)
    ax1.set_xticks(xs)
    ax1.set_xticklabels([f"PC{i}" for i in xs])
    ax1.tick_params(axis="y", labelcolor=INMU_PRIMARY)
    ax1.legend(loc="upper right", frameon=False)

    # Eje derecho: varianza acumulada
    ax2 = ax1.twinx()
    ax2.plot(xs, cumvar * 100, color=INMU_MUTED, marker="s",
             linewidth=1.2, markersize=5, linestyle=":")
    ax2.set_ylabel("Varianza acumulada (%)", color=INMU_MUTED)
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis="y", labelcolor=INMU_MUTED)

    plt.title(
        f"Scree plot · PCA de atributos hedónicos (n = {len(X):,}, p = {n})\n"
        f"PC1 explica {var_ratio[0]*100:.1f}% · PC1+PC2 = {cumvar[1]*100:.1f}%",
        fontsize=11, color=INMU_PRIMARY,
    )
    plt.tight_layout()
    plt.savefig(OUT_DIR / "scree_ihed.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 2.2 — Scatter criminalidad objetiva vs percepción
# ════════════════════════════════════════════════════════════════════

def fig_scatter_seg(conn):
    print("[7/9] Generando scatter_seg.pdf …")
    df = pd.read_sql(
        """
        SELECT c.nombre_localidad AS nombre,
               c.masa_crimen::float AS obj,
               (5 - AVG(i.iseg))::float AS percep_inseg
        FROM iug.criminalidad_localidad c
        LEFT JOIN iug.localidad l
          ON UPPER(l.nombre) = UPPER(c.nombre_localidad)
        LEFT JOIN iug.inmueble i
          ON i.id_localidad = l.id_localidad AND i.iseg IS NOT NULL
        WHERE c.masa_crimen IS NOT NULL
        GROUP BY c.nombre_localidad, c.masa_crimen
        HAVING COUNT(i.id_inmueble) >= 20
        """,
        conn,
    )
    df = df.dropna()

    obj_med = df["obj"].median()
    perc_med = df["percep_inseg"].median()

    # Cuadrantes: paradoja = alta crim + baja percep, o viceversa
    df["cuadrante"] = "consistente"
    df.loc[(df["obj"] > obj_med) & (df["percep_inseg"] < perc_med), "cuadrante"] = "paradoja_obj_alta"
    df.loc[(df["obj"] < obj_med) & (df["percep_inseg"] > perc_med), "cuadrante"] = "paradoja_perc_alta"

    fig, ax = plt.subplots(figsize=(9, 6))
    palette = {
        "consistente":        INMU_MUTED,
        "paradoja_obj_alta":  INMU_RED,
        "paradoja_perc_alta": INMU_GREEN,
    }
    for cuad, sub in df.groupby("cuadrante"):
        ax.scatter(sub["obj"], sub["percep_inseg"],
                   s=180, alpha=0.7, color=palette[cuad],
                   edgecolor=INMU_PRIMARY, linewidth=0.8,
                   label=cuad.replace("_", " "))
    for _, row in df.iterrows():
        ax.annotate(row["nombre"], (row["obj"], row["percep_inseg"]),
                    fontsize=7.5, xytext=(5, 5), textcoords="offset points",
                    color=INMU_PRIMARY)
    ax.axhline(perc_med, color=INMU_MUTED, linestyle="--", linewidth=0.8)
    ax.axvline(obj_med,  color=INMU_MUTED, linestyle="--", linewidth=0.8)

    ax.set_xlabel("Criminalidad objetiva (masa_crimen normalizada)")
    ax.set_ylabel("Inseguridad percibida (5 − I_SEG promedio)")
    ax.set_title("Paradoja de la inseguridad por localidad\n"
                 "Criminalidad objetiva vs. percepción ciudadana inversa",
                 fontsize=11, color=INMU_PRIMARY)
    ax.legend(loc="lower right", frameon=False)
    ax.grid(alpha=0.25, linestyle=":")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "scatter_seg.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 2.4 — Heatmap de correlación entre los 5 subíndices
# ════════════════════════════════════════════════════════════════════

def fig_heatmap_corr(conn):
    print("[8/9] Generando heatmap_corr.pdf …")
    df = pd.read_sql(
        """
        SELECT iurb, iacc, iseg, ihed, idot, ipnu
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
        """,
        conn,
    )
    labels = ["IUG", "I_ACC", "I_SEG", "I_HED", "I_DOT", "I_PNU"]
    corr_p = df.corr(method="pearson").to_numpy()
    corr_s = df.corr(method="spearman").to_numpy()

    fig, axs = plt.subplots(1, 2, figsize=(11.5, 5.2))

    # Pearson
    sns.heatmap(corr_p, ax=axs[0], annot=True, fmt=".2f",
                cmap="RdYlGn", center=0, vmin=-1, vmax=1,
                square=True, linewidths=0.5, linecolor="white",
                xticklabels=labels, yticklabels=labels,
                cbar_kws={"shrink": 0.7, "label": "Pearson r"})
    axs[0].set_title("Correlación de Pearson", color=INMU_PRIMARY)

    # Spearman
    sns.heatmap(corr_s, ax=axs[1], annot=True, fmt=".2f",
                cmap="RdYlGn", center=0, vmin=-1, vmax=1,
                square=True, linewidths=0.5, linecolor="white",
                xticklabels=labels, yticklabels=labels,
                cbar_kws={"shrink": 0.7, "label": "Spearman ρ"})
    axs[1].set_title("Correlación de Spearman", color=INMU_PRIMARY)

    fig.suptitle("Correlaciones entre subíndices del IUG (n = 23 761)",
                 fontsize=12, color=INMU_PRIMARY, y=1.02)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "heatmap_corr.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


# ════════════════════════════════════════════════════════════════════
# 2.3-bis — Histograma específico de I_ACC con anotaciones
# ════════════════════════════════════════════════════════════════════

def fig_hist_iacc(conn):
    print("[9/9] Generando hist_iacc.pdf …")
    df = pd.read_sql(
        "SELECT iacc FROM iug.inmueble WHERE iacc IS NOT NULL",
        conn,
    )
    x = df["iacc"].to_numpy()

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    sns.histplot(x, bins=50, kde=True, ax=ax,
                 color=INMU_GREEN, edgecolor="white", linewidth=0.4,
                 line_kws={"color": INMU_PRIMARY, "linewidth": 1.5})

    # Bandas de interpretación
    bands = [
        (0,   1.0, "Aislado",       INMU_RED),
        (1.0, 2.5, "Periferia TM",  "#F59E0B"),
        (2.5, 3.5, "Conectado",     INMU_GREEN_LITE),
        (3.5, 5.0, "Bien servido",  INMU_GREEN),
    ]
    ylim = ax.get_ylim()
    for lo, hi, label, col in bands:
        ax.axvspan(lo, hi, alpha=0.08, color=col)
        ax.text((lo + hi) / 2, ylim[1] * 0.95, label,
                ha="center", fontsize=8, color=col, fontweight="bold")

    ax.axvline(np.mean(x), color=INMU_PRIMARY, linestyle="--", linewidth=1.2,
               label=f"μ = {np.mean(x):.2f}")
    ax.axvline(np.median(x), color=INMU_RED, linestyle=":", linewidth=1.2,
               label=f"mediana = {np.median(x):.2f}")
    ax.set_title(
        "I_ACC · Distribución de la accesibilidad gravitacional\n"
        rf"modelo $I_{{ACC,i}} = \sum_j O_j / d_{{ij}}^{{\beta=1.5}}$ · n = {len(x):,}",
        fontsize=11, color=INMU_PRIMARY,
    )
    ax.set_xlabel("I_ACC normalizado [0, 5]")
    ax.set_ylabel("Frecuencia")
    ax.set_xlim(0, 5)
    ax.legend(loc="upper right", frameon=False)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "hist_iacc.pdf", bbox_inches="tight")
    plt.close()
    print("       OK")


def main():
    _style()
    conn = get_conn()
    fig_histograma_subindices(conn)
    fig_qq_residuos(conn)
    fig_mapa_coropletico(conn)
    fig_poi_categorias(conn)
    fig_cuadrante_decisiones(conn)
    fig_scree_pca(conn)
    fig_scatter_seg(conn)
    fig_heatmap_corr(conn)
    fig_hist_iacc(conn)
    conn.close()

    print("\n=== Listo. Archivos generados en /tmp/figs/: ===")
    for p in sorted(OUT_DIR.glob("*.pdf")):
        print(f"   {p.name}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
