"""
Configuracion del scraper SAE (Sociedad de Activos Especiales).
Bienes incautados por el estado colombiano: narcotrafico, crimen,
extincion de dominio.

Fuentes:
  - SAE oficial: https://www.saesas.gov.co
  - Activos por Colombia: https://www.activosporcolombia.com (plataforma de subastas)
"""
import os

# ── URLs base ──────────────────────────────────────────────────────────
SAE_BASE_URL = "https://www.saesas.gov.co"
ACTIVOS_BASE_URL = "https://www.activosporcolombia.com"

# ── Departamentos de interes ──────────────────────────────────────────
SAE_DEPARTAMENTOS = [
    "cundinamarca",
    "antioquia",
    "valle-del-cauca",
    "atlantico",
]

# ── Tipos de inmueble esperados en la pagina ──────────────────────────
SAE_TIPOS_INMUEBLE = [
    "apartamento",
    "casa",
    "lote",
    "bodega",
    "local",
    "finca",
    "oficina",
]

# ── MongoDB ───────────────────────────────────────────────────────────
MONGO_DB = os.getenv("MONGO_DB_SAE", "sae")
MONGO_COLLECTION_SAE = os.getenv("MONGO_COLLECTION_SAE", "sae_raw")

# ── Selenium (fallback si requests+BS4 no basta) ─────────────────────
SELENIUM_URL = os.getenv("SELENIUM_URL", "http://localhost:4444/wd/hub")

# ── Request headers ──────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9",
}

# ── Paginacion ────────────────────────────────────────────────────────
MAX_PAGES = int(os.getenv("SAE_MAX_PAGES", "50"))
REQUEST_DELAY = float(os.getenv("SAE_REQUEST_DELAY", "2.0"))


def get_sae_search_urls():
    """Genera URLs de busqueda del sitio oficial SAE por departamento."""
    urls = []
    for depto in SAE_DEPARTAMENTOS:
        urls.append({
            "url": f"{SAE_BASE_URL}/inmuebles?departamento={depto}",
            "departamento": depto,
            "fuente": "sae",
        })
    return urls


def get_activos_search_urls():
    """Genera URLs de busqueda de Activos por Colombia por departamento."""
    urls = []
    for depto in SAE_DEPARTAMENTOS:
        urls.append({
            "url": f"{ACTIVOS_BASE_URL}/inmuebles?departamento={depto}",
            "departamento": depto,
            "fuente": "activos_por_colombia",
        })
    return urls
