"""
Configuracion del scraper Bancolombia REO (Remate / Dacion en pago).
Propiedades recuperadas por Bancolombia por incumplimiento de credito.

Bancolombia maneja:
  - Tipos: apartamentos, casas, lotes, oficinas, locales, bodegas, fincas
  - Transacciones: REO (bank-owned, no aplica venta/arriendo convencional)
  - Ciudades: las principales de Colombia
"""
import os

# ── Ciudades a scrapear ────────────────────────────────────────────
BANCOLOMBIA_CIUDADES = [
    "bogota", "medellin", "cali", "barranquilla",
]

# ── URLs ───────────────────────────────────────────────────────────
BANCOLOMBIA_BASE_URL = "https://inmobiliariatu360.bancolombia.com"

# Endpoints conocidos; el scraper prueba ambos hasta encontrar el que
# devuelva resultados (la plataforma ha cambiado rutas varias veces).
BANCOLOMBIA_SEARCH_PATHS = [
    "/nuevo",
    "/buscar-inmueble",
]

# ── MongoDB ────────────────────────────────────────────────────────
MONGO_DB = os.getenv("MONGO_DB_BANCOLOMBIA", "bancolombia_reo")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION_BANCOLOMBIA", "reo_raw")


def get_search_urls():
    """Genera URLs de busqueda por ciudad para cada endpoint candidato."""
    urls = []
    for ciudad in BANCOLOMBIA_CIUDADES:
        for path in BANCOLOMBIA_SEARCH_PATHS:
            urls.append({
                "base": BANCOLOMBIA_BASE_URL,
                "path": path,
                "ciudad": ciudad,
                "url": f"{BANCOLOMBIA_BASE_URL}{path}?ciudad={ciudad}",
            })
    return urls
