"""
Configuracion del scraper Ciencuadras.
Portal inmobiliario colombiano (~130K listings).

Ciencuadras maneja:
  - Tipos: apartamentos, casas, locales, lotes, bodegas, oficinas
  - Transacciones: venta, arriendo
  - Ciudades: bogota, medellin, cali, barranquilla, cajica, chia
  - Sitio construido con Next.js (posible API via /_next/data/)
"""
import os

# ── URL base ──────────────────────────────────────────────────────────
BASE_URL = "https://www.ciencuadras.com"

# Patrones de URL de listado:
# https://www.ciencuadras.com/venta/apartamentos/bogota
LISTING_URL = f"{BASE_URL}/{{transaccion}}/{{tipo}}/{{ciudad}}"

# ── Candidatos de API (Next.js / REST) ───────────────────────────────
API_CANDIDATES = [
    f"{BASE_URL}/_next/data/",          # Next.js build-data
    f"{BASE_URL}/api/properties",       # REST generico
    f"{BASE_URL}/api/search",           # REST busqueda
    f"{BASE_URL}/graphql",              # GraphQL
    f"{BASE_URL}/api/graphql",          # GraphQL alternativo
]

# ── Ciudades ──────────────────────────────────────────────────────────
CIUDADES = [
    "bogota",
    "medellin",
    "cali",
    "barranquilla",
    "cajica",
    "chia",
]

# ── Tipos de propiedad ───────────────────────────────────────────────
TIPOS = [
    "apartamentos",
    "casas",
    "locales",
    "lotes",
    "bodegas",
    "oficinas",
]

# ── Transacciones ─────────────────────────────────────────────────────
TRANSACCIONES = [
    "venta",
    "arriendo",
]

# ── MongoDB ───────────────────────────────────────────────────────────
MONGO_DB = os.getenv("MONGO_DB_CIENCUADRAS", "ciencuadras")

# Campos a extraer de cada listing
FIELDS = [
    "codigo", "precio", "area", "habitaciones", "banos",
    "estrato", "tipo", "ubicacion", "direccion",
    "lat", "lon", "image", "descripcion",
    "inmobiliaria", "caracteristicas",
]

# ── Scraper settings ─────────────────────────────────────────────────
MAX_PAGES = int(os.getenv("CIENCUADRAS_MAX_PAGES", "100"))
PAGE_TIMEOUT = int(os.getenv("CIENCUADRAS_PAGE_TIMEOUT", "30"))
REQUEST_DELAY = float(os.getenv("CIENCUADRAS_DELAY", "2.0"))

# Headers para requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}


def collection_name(ciudad: str, tipo: str, transaccion: str) -> str:
    """Genera nombre de coleccion MongoDB: e.g. bogota_apartamentos_venta"""
    return f"{ciudad}_{tipo}_{transaccion}"


def get_matrix():
    """
    Genera la matriz completa de combinaciones:
    ciudad x tipo x transaccion.
    Retorna lista de dicts con url, ciudad, tipo, transaccion.
    """
    combos = []
    for ciudad in CIUDADES:
        for tipo in TIPOS:
            for transaccion in TRANSACCIONES:
                url = LISTING_URL.format(
                    transaccion=transaccion,
                    tipo=tipo,
                    ciudad=ciudad,
                )
                combos.append({
                    "url": url,
                    "ciudad": ciudad,
                    "tipo": tipo,
                    "transaccion": transaccion,
                    "collection": collection_name(ciudad, tipo, transaccion),
                })
    return combos
