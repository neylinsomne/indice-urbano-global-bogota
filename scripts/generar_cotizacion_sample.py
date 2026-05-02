"""
Genera un PDF de cotización (Análisis Comparativo de Mercado) de muestra
usando los datos del Apto 5700 (Puente Largo, Chapinero) que aparece en
la Ficha de inmueble individual de la tesis.

El estilo replica el del módulo `services/api/services/acm_pdf.py` del
sistema productivo, pero este script es autocontenido: no requiere base
de datos ni levantar la API. Solo necesita `fpdf2`.

Uso:
    pip install fpdf2
    python scripts/generar_cotizacion_sample.py

Salida:
    samples/cotizacion_ejemplo.pdf
"""
from __future__ import annotations

import os
import unicodedata
from datetime import date
from pathlib import Path

from fpdf import FPDF


# ─────────────────────────────────────────────────────────────────────
# Datos del inmueble sujeto (consistentes con la Tabla 4.X de la tesis)
# ─────────────────────────────────────────────────────────────────────
SUJETO = {
    "id": 5700,
    "tipo": "Apartamento",
    "barrio": "Puente Largo",
    "localidad": "Chapinero",
    "ciudad": "Bogota D.C.",
    "estado": "Usado",
    "edad": "10-20 anios",
    "estrato": 5,
    "area": 96,
    "habitaciones": 3,
    "banos": 3,
    "parqueaderos": 1,
    "precio": 659_000_000,
    "fuente_listado": "Finca Raiz",
    # Indicadores IUG calculados por el sistema
    "iug_acc": 4.62,
    "iug_seg": 3.28,
    "iug_hed": 5.00,
    "iug_dot": 5.00,
    "iug_pnu": 3.50,
    "iug": 4.28,
    "iug_banda_inf": 3.49,
    "iug_banda_sup": 5.07,
    "precio_estimado": 837_000_000,
    "residual_pct": -21.3,
    "cuadrante": "COMPRAR",
}

# Comparables sinteticos pero realistas (mismo barrio / sector)
COMPARABLES = [
    {
        "n": 1, "barrio": "Puente Largo", "edad": "15 anios",
        "fuente": "Finca Raiz", "fecha": "Abr/2026",
        "precio": 720_000_000, "area": 105, "estrato": 5,
        "factor_oferta": 0.95, "factor_conserv": 1.00,
    },
    {
        "n": 2, "barrio": "Chico Norte", "edad": "8 anios",
        "fuente": "Habi", "fecha": "Mar/2026",
        "precio": 695_000_000, "area": 92, "estrato": 5,
        "factor_oferta": 0.95, "factor_conserv": 1.02,
    },
    {
        "n": 3, "barrio": "Antiguo Country", "edad": "20 anios",
        "fuente": "Finca Raiz", "fecha": "Mar/2026",
        "precio": 780_000_000, "area": 110, "estrato": 5,
        "factor_oferta": 0.95, "factor_conserv": 0.97,
    },
    {
        "n": 4, "barrio": "Chapinero Central", "edad": "12 anios",
        "fuente": "Finca Raiz", "fecha": "Feb/2026",
        "precio": 645_000_000, "area": 98, "estrato": 5,
        "factor_oferta": 0.95, "factor_conserv": 1.00,
    },
    {
        "n": 5, "barrio": "Puente Largo", "edad": "18 anios",
        "fuente": "Habi", "fecha": "Feb/2026",
        "precio": 670_000_000, "area": 100, "estrato": 5,
        "factor_oferta": 0.95, "factor_conserv": 0.98,
    },
]


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    """Quita acentos para compatibilidad Latin-1 con fpdf2."""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in s if not unicodedata.combining(c))


def cop(value: float | int) -> str:
    if value is None:
        return "-"
    return f"$ {int(round(value)):,}".replace(",", ".")


def num(value: float | int, decimals: int = 0) -> str:
    if value is None:
        return "-"
    if decimals == 0:
        return f"{int(round(value)):,}".replace(",", ".")
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ─────────────────────────────────────────────────────────────────────
# Estadistica del ACM
# ─────────────────────────────────────────────────────────────────────
def compute_homologation(comp: dict) -> dict:
    p_m2 = comp["precio"] / comp["area"]
    p_m2_hom = p_m2 * comp["factor_oferta"] * comp["factor_conserv"]
    return {**comp, "precio_m2": p_m2, "precio_m2_hom": p_m2_hom}


def compute_stats(comps: list[dict]) -> dict:
    import statistics as st
    prices = [c["precio_m2_hom"] for c in comps]
    n = len(prices)
    mean = sum(prices) / n
    sd = st.stdev(prices) if n > 1 else 0
    cv = (sd / mean * 100) if mean else 0
    # IC 90% con t-Student (n-1 grados de libertad)
    # Para n=5 -> gl=4 -> t_{0.95, 4} = 2.132
    t_table = {2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943,
               7: 1.895, 8: 1.860, 9: 1.833}
    gl = n - 1
    t = t_table.get(gl, 1.96)
    margin = t * sd / (n ** 0.5)
    return {
        "n": n, "gl": gl, "t": t,
        "mean": mean, "sd": sd, "cv": cv,
        "ci_low": mean - margin,
        "ci_high": mean + margin,
    }


# ─────────────────────────────────────────────────────────────────────
# Renderizador PDF
# ─────────────────────────────────────────────────────────────────────
class CotizacionPDF(FPDF):
    # Paleta del sistema productivo
    C_PRIMARY = (27, 73, 101)
    C_PRIMARY_LIGHT = (95, 168, 211)
    C_GOLD = (232, 201, 106)
    C_DARK = (51, 51, 51)
    C_GRAY = (100, 100, 100)
    C_LIGHT_GRAY = (240, 240, 240)
    C_WHITE = (255, 255, 255)
    C_GREEN_OK = (76, 175, 80)
    C_RED_WARN = (211, 47, 47)

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margin(10)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(
            0, 10,
            f"INMU - Indice Urbano Global de Bogota | Pagina {self.page_no()} | "
            "MUESTRA ACADEMICA - Trabajo de Grado PUJ 2026",
            align="C",
        )

    # ─── Header ──────────────────────────────────────────────────────
    def render_header(self):
        self.set_fill_color(*self.C_PRIMARY)
        self.rect(0, 0, 210, 22, style="F")
        self.set_xy(10, 5)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*self.C_WHITE)
        self.cell(190, 12, clean(
            "ANALISIS DE MERCADO Y PRECIO OBJETIVO DE VENTA"), align="C")
        self.ln(18)
        # Subtitulo institucional
        self.set_xy(10, 24)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*self.C_GRAY)
        self.cell(190, 5, clean(
            f"Generado el {date.today().strftime('%d/%m/%Y')} | "
            "Sistema INMU - Indice Urbano Global de Bogota"), align="C")
        self.ln(8)

    # ─── Banner de muestra academica ─────────────────────────────────
    def render_academic_banner(self):
        self.set_fill_color(*self.C_GOLD)
        self.set_draw_color(180, 150, 50)
        y = self.get_y()
        self.rect(10, y, 190, 8, style="DF")
        self.set_xy(10, y + 1)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*self.C_DARK)
        self.cell(190, 6, clean(
            "MUESTRA ACADEMICA - Datos del Apto 5700 (Capitulo 4 de la tesis)"),
            align="C")
        self.ln(11)

    # ─── Ficha del sujeto ────────────────────────────────────────────
    def render_subject(self):
        y0 = self.get_y()
        fields = [
            ("ID inmueble", str(SUJETO["id"])),
            ("Tipo", SUJETO["tipo"]),
            ("Barrio", SUJETO["barrio"]),
            ("Localidad", SUJETO["localidad"]),
            ("Ciudad", SUJETO["ciudad"]),
            ("Estado", SUJETO["estado"]),
            ("Antiguedad", SUJETO["edad"]),
            ("Area construida", f"{SUJETO['area']} mt2"),
            ("Habitaciones / Banos", f"{SUJETO['habitaciones']} / {SUJETO['banos']}"),
            ("Estrato", str(SUJETO["estrato"])),
            ("Precio listado", cop(SUJETO["precio"])),
        ]
        label_w, value_w, row_h = 38, 56, 6.2
        for i, (lab, val) in enumerate(fields):
            y = y0 + i * row_h
            self.set_xy(10, y)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*self.C_DARK)
            self.set_fill_color(*self.C_LIGHT_GRAY)
            self.cell(label_w, row_h, clean(f" {lab}"), border=1, fill=True)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*self.C_GRAY)
            self.cell(value_w, row_h, clean(f" {val}"), border=1)

        # Imagen placeholder (columna derecha)
        img_x, img_y, img_w, img_h = 110, y0, 90, len(fields) * row_h
        self.set_fill_color(235, 235, 235)
        self.rect(img_x, img_y, img_w, img_h, style="F")
        self.set_draw_color(180, 180, 180)
        self.rect(img_x, img_y, img_w, img_h)
        # Marca de agua diagonal
        self.set_xy(img_x, img_y + img_h / 2 - 8)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(170, 170, 170)
        self.cell(img_w, 5, clean("MUESTRA ACADEMICA"), align="C")
        self.set_xy(img_x, img_y + img_h / 2 - 1)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(img_w, 4, clean("Imagen del inmueble omitida por"), align="C")
        self.set_xy(img_x, img_y + img_h / 2 + 3)
        self.cell(img_w, 4, clean("derechos de uso del anuncio original."), align="C")
        self.set_xy(img_x, img_y + img_h / 2 + 7)
        self.cell(img_w, 4, clean(
            "En produccion se incluye automaticamente."), align="C")

        self.set_y(y0 + len(fields) * row_h + 4)

    # ─── Tabla de comparables ────────────────────────────────────────
    def render_comparables_table(self, comps_h: list[dict]):
        self.set_y(self.get_y() + 2)
        # Subtitulo de seccion
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.C_PRIMARY)
        self.set_x(10)
        self.cell(190, 5, clean("Comparables del mercado"))
        self.ln(6)
        cols = [
            ("#", 8),
            ("Barrio / Edad", 36),
            ("Fuente", 18),
            ("Fecha", 14),
            ("Valor", 26),
            ("Area", 12),
            ("Precio/m2", 22),
            ("F.Of.", 10),
            ("F.Cn.", 10),
            ("Precio/m2\nHomolog.", 24),
        ]
        # Header
        x = 10
        y_h = self.get_y()
        self.set_fill_color(*self.C_PRIMARY)
        self.set_text_color(*self.C_WHITE)
        self.set_font("Helvetica", "B", 6.5)
        for name, w in cols:
            self.set_xy(x, y_h)
            self.multi_cell(w, 4, clean(name), border=1, align="C", fill=True)
            x += w
        self.set_y(y_h + 8)

        row_h = 7
        for i, c in enumerate(comps_h):
            x = 10
            y_r = self.get_y()
            if i % 2 == 0:
                self.set_fill_color(*self.C_WHITE)
            else:
                self.set_fill_color(248, 248, 248)
            self.set_text_color(*self.C_DARK)
            self.set_font("Helvetica", "", 6.5)
            values = [
                str(c["n"]),
                f"{c['barrio']} / {c['edad']}",
                c["fuente"],
                c["fecha"],
                cop(c["precio"]),
                f"{c['area']} m2",
                cop(c["precio_m2"]),
                f"{c['factor_oferta']:.2f}",
                f"{c['factor_conserv']:.2f}",
                cop(c["precio_m2_hom"]),
            ]
            aligns = ["C", "L", "L", "C", "R", "C", "R", "C", "C", "R"]
            for j, ((_, w), val, al) in enumerate(zip(cols, values, aligns)):
                self.set_xy(x, y_r)
                self.cell(w, row_h, clean(f" {val} "),
                          border=1, align=al, fill=True)
                x += w
            self.set_y(y_r + row_h)
        self.ln(2)

    # ─── Estadisticas ────────────────────────────────────────────────
    def render_statistics(self, stats: dict):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.C_PRIMARY)
        self.set_x(10)
        self.cell(190, 5, clean("Estadistica del estudio"))
        self.ln(6)
        rows = [
            ("Promedio aritmetico precio/m2", cop(stats["mean"])),
            ("Desviacion tipica (muestral)", cop(stats["sd"])),
            ("Coeficiente de variacion", f"{stats['cv']:.2f} %"),
            ("Limite superior (IC 90%)", cop(stats["ci_high"])),
            ("Limite inferior (IC 90%)", cop(stats["ci_low"])),
            (f"t-Student (gl={stats['gl']})", f"{stats['t']:.4f}"),
            ("N comparables", str(stats["n"])),
        ]
        label_w, value_w, row_h = 95, 95, 5.5
        for lab, val in rows:
            self.set_x(10)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*self.C_DARK)
            self.cell(label_w, row_h, clean(f" {lab}"), border=0, align="L")
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*self.C_PRIMARY)
            self.cell(value_w, row_h, clean(val), border=0, align="R")
            self.ln(row_h)
        self.ln(2)

    # ─── Bloque IUG (especifico de este sistema) ─────────────────────
    def render_iug_block(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.C_PRIMARY)
        self.set_x(10)
        self.cell(190, 5, clean("Indice Urbano Global (IUG) del entorno"))
        self.ln(7)

        # Caja con desglose
        x0, y0, w_total = 10, self.get_y(), 190
        sub_w = w_total / 5
        self.set_fill_color(*self.C_LIGHT_GRAY)
        self.rect(x0, y0, w_total, 26, style="F")
        self.set_draw_color(200, 200, 200)
        self.rect(x0, y0, w_total, 26)

        labels = [
            ("Accesibilidad", SUJETO["iug_acc"]),
            ("Seguridad", SUJETO["iug_seg"]),
            ("Hedonico", SUJETO["iug_hed"]),
            ("Dotacional", SUJETO["iug_dot"]),
            ("Normativo", SUJETO["iug_pnu"]),
        ]
        for i, (lab, val) in enumerate(labels):
            x = x0 + i * sub_w
            self.set_xy(x, y0 + 2)
            self.set_font("Helvetica", "B", 7.5)
            self.set_text_color(*self.C_GRAY)
            self.cell(sub_w, 4, clean(lab), align="C")
            self.set_xy(x, y0 + 8)
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*self.C_PRIMARY)
            self.cell(sub_w, 8, f"{val:.2f}", align="C")
            # Mini barra
            bar_w = (val / 5.0) * (sub_w - 8)
            self.set_fill_color(*self.C_PRIMARY_LIGHT)
            self.rect(x + 4, y0 + 19, bar_w, 3, style="F")
            self.set_draw_color(180, 180, 180)
            self.rect(x + 4, y0 + 19, sub_w - 8, 3)

        self.set_y(y0 + 30)

        # IUG agregado y banda
        self.set_x(10)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.C_PRIMARY)
        self.cell(60, 7, clean(f"IUG agregado: {SUJETO['iug']:.2f} / 5.00"))
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.C_GRAY)
        self.cell(130, 7, clean(
            f"Banda de confianza al 90%: [{SUJETO['iug_banda_inf']:.2f}, "
            f"{SUJETO['iug_banda_sup']:.2f}]   |   "
            "Posicion: top 5% del sistema"))
        self.ln(9)

    # ─── Bloque de mispricing y cuadrante ────────────────────────────
    def render_decision_block(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.C_PRIMARY)
        self.set_x(10)
        self.cell(190, 5, clean("Diagnostico de mispricing y cuadrante de decision"))
        self.ln(7)

        # Caja con metricas
        x0, y0 = 10, self.get_y()
        self.set_fill_color(248, 248, 248)
        self.rect(x0, y0, 190, 22, style="F")
        self.set_draw_color(200, 200, 200)
        self.rect(x0, y0, 190, 22)

        col_w = 190 / 3
        self.set_xy(x0 + 4, y0 + 2)
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*self.C_GRAY)
        self.cell(col_w - 4, 4, clean("Precio listado"), align="L")
        self.set_xy(x0 + col_w, y0 + 2)
        self.cell(col_w, 4, clean("Precio estimado (modelo hedonico)"), align="C")
        self.set_xy(x0 + 2 * col_w, y0 + 2)
        self.cell(col_w - 4, 4, clean("Residual"), align="R")

        self.set_xy(x0 + 4, y0 + 8)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*self.C_DARK)
        self.cell(col_w - 4, 8, clean(cop(SUJETO["precio"])), align="L")
        self.set_xy(x0 + col_w, y0 + 8)
        self.cell(col_w, 8, clean(cop(SUJETO["precio_estimado"])), align="C")
        self.set_xy(x0 + 2 * col_w, y0 + 8)
        residual_color = self.C_GREEN_OK if SUJETO["residual_pct"] < 0 else self.C_RED_WARN
        self.set_text_color(*residual_color)
        self.cell(col_w - 4, 8, f"{SUJETO['residual_pct']:+.1f} %", align="R")

        self.set_y(y0 + 26)

        # Cuadrante de decision (caja destacada)
        x0, y0 = 10, self.get_y()
        self.set_fill_color(*self.C_GREEN_OK)
        self.rect(x0, y0, 190, 14, style="F")
        self.set_xy(x0, y0 + 2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*self.C_WHITE)
        self.cell(190, 6, clean(
            f"CUADRANTE DE DECISION: {SUJETO['cuadrante']}"), align="C")
        self.set_xy(x0, y0 + 8)
        self.set_font("Helvetica", "I", 8)
        self.cell(190, 4, clean(
            "IUG alto (4.28) + precio listado por debajo del estimado (-21.3%) => "
            "subvaloracion sustentada en calidad urbana objetiva."), align="C")
        self.set_y(y0 + 18)

    # ─── Nota metodologica ───────────────────────────────────────────
    def render_methodological_note(self):
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*self.C_GRAY)
        self.set_x(10)
        text = clean(
            "Nota metodologica: el IUG es un indicador sintetico de calidad urbana "
            "calculado de forma ortogonal al precio. No predice el precio de mercado; "
            "lo contrasta con los fundamentales urbanos del territorio. La banda al "
            "90% propaga incertidumbre desde GPS, EPV 2024 e ICSU. Los comparables "
            "se seleccionan por similitud espacial y estructural; los factores de "
            "homologacion siguen el protocolo IAAO 2013. Validez del indicador "
            "verificada mediante un protocolo de 11 pruebas estadisticas (Capitulo 5 "
            "de la tesis: bondad de ajuste, robustez, validez convergente, validez "
            "de uso). Este reporte es una MUESTRA ACADEMICA generada con datos del "
            "Apto 5700 que aparece en el cuerpo de la tesis."
        )
        self.multi_cell(190, 3.5, text, align="J")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
def main() -> None:
    comps_h = [compute_homologation(c) for c in COMPARABLES]
    stats = compute_stats(comps_h)

    pdf = CotizacionPDF()
    pdf.add_page()
    pdf.render_header()
    pdf.render_academic_banner()
    pdf.render_subject()
    pdf.render_iug_block()
    pdf.render_decision_block()
    pdf.render_comparables_table(comps_h)
    pdf.render_statistics(stats)
    pdf.render_methodological_note()

    out_dir = Path(__file__).resolve().parent.parent / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cotizacion_ejemplo.pdf"
    pdf.output(str(out_path))
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
