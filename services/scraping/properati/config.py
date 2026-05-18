"""
Configuracion del scraper Properati.
Define ciudades, tipos de propiedad, BigQuery dataset y URLs.

Properati maneja:
  - Tipos: apartamento, casa, local, lote, oficina
  - Transacciones: venta y arriendo
  - Ciudades: principales de Colombia
  - Fuentes: BigQuery (dataset publico) + web scraping (fallback)
"""
import os

# ── BigQuery ────────────────────────────────────────────────────────
BIGQUERY_PROJECT = "properati-data-public"
BIGQUERY_DATASET = "properties_co"
BIGQUERY_TABLE = "properties_co"
BIGQUERY_FULL_TABLE = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"

# ── Web Scraping ────────────────────────────────────────────────────
PROPERATI_BASE_URL = "https://www.properati.com.co"

# Endpoints que Properati puede exponer (se prueban en orden)
PROPERATI_API_ENDPOINTS = [
    "/api/v1/properties",
    "/api/v2/properties",
    "/api/properties",
]

# ── Ciudades ────────────────────────────────────────────────────────
PROPERATI_CIUDADES = [
    "bogota",
    "medellin",
    "cali",
    "barranquilla",
]

# ── Tipos de propiedad ──────────────────────────────────────────────
PROPERATI_TIPOS = [
    "apartamento",
    "casa",
    "local",
    "lote",
    "oficina",
]

# ── Transacciones ───────────────────────────────────────────────────
PROPERATI_TRANSACCIONES = ["venta", "arriendo"]

# ── MongoDB ─────────────────────────────────────────────────────────
MONGO_DB = os.getenv("MONGO_DB_PROPERATI", "properati")


def get_collection_name(ciudad: str, tipo: str, transaccion: str = "venta") -> str:
    """Genera el nombre de la coleccion por ciudad+tipo+transaccion.
    Ejemplo: bogota_apartamentos_venta
    """
    return f"{ciudad}_{tipo}s_{transaccion}"


def get_properati_urls():
    """Genera todas las combinaciones ciudad x tipo x transaccion como URLs web."""
    urls = []
    for ciudad in PROPERATI_CIUDADES:
        for tipo in PROPERATI_TIPOS:
            for transaccion in PROPERATI_TRANSACCIONES:
                # Properati URL pattern: /s/bogota/apartamento/venta
                path = f"/s/{ciudad}/{tipo}/{transaccion}"
                urls.append({
                    "url": f"{PROPERATI_BASE_URL}{path}",
                    "ciudad": ciudad,
                    "tipo": tipo,
                    "transaccion": transaccion,
                })
    return urls


# ── Scraping settings ───────────────────────────────────────────────
REQUEST_DELAY_MIN = 1.0   # segundos entre requests
REQUEST_DELAY_MAX = 2.0
MAX_PAGES_PER_SEARCH = 50  # maximo de paginas de listado a recorrer
REQUEST_TIMEOUT = 30       # timeout por request en segundos

# ── User-Agents rotativos ──────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]
