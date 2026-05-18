"""
Servicio de scraping por URL — Feature Premium (Beta).

Extrae datos de un inmueble desde una URL pública de:
  - fincaraiz.com.co
  - habi.co
  - metrocuadrado.com

Control de concurrencia:
  - Por usuario: asyncio.Lock — máx 1 scraping simultáneo por usuario
  - Global: asyncio.Semaphore — máx 5 scrapers simultáneos totales

Dependencias: httpx, beautifulsoup4 (en requirements.txt)
"""
import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Dominios permitidos (seguridad: evita SSRF contra hosts internos)
ALLOWED_DOMAINS = {
    "fincaraiz.com.co",
    "www.fincaraiz.com.co",
    "habi.co",
    "www.habi.co",
    "metrocuadrado.com",
    "www.metrocuadrado.com",
}

# Concurrencia: 1 por usuario, 5 global
_user_locks: dict[int, asyncio.Lock] = {}
_global_semaphore = asyncio.Semaphore(5)

SCRAPE_TIMEOUT = 20  # segundos


def _get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


def validate_url(url: str) -> str:
    """
    Valida que la URL sea de un dominio permitido.
    Retorna el dominio base o lanza ValueError.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Solo se aceptan URLs http/https")
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_DOMAINS:
            allowed = ", ".join(sorted(ALLOWED_DOMAINS))
            raise ValueError(
                f"Dominio no permitido: {host}. "
                f"Dominios aceptados: {allowed}"
            )
        return host
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"URL inválida: {e}")


async def scrape_property_url(url: str, user_id: int) -> dict:
    """
    Scraping de un inmueble desde su URL.

    Raises:
        RuntimeError("user_busy")    — si el usuario ya tiene un scraping activo
        ValueError("...")            — URL inválida o dominio no permitido
        httpx.HTTPError              — error de red
    """
    host = validate_url(url)

    user_lock = _get_user_lock(user_id)
    if user_lock.locked():
        raise RuntimeError("user_busy")

    async with user_lock:
        async with _global_semaphore:
            return await _do_scrape(url, host)


async def _do_scrape(url: str, host: str) -> dict:
    """Descarga y parsea la página según el dominio."""
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError(f"Dependencia faltante: {e}. Instala httpx y beautifulsoup4.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-CO,es;q=0.9",
    }

    async with httpx.AsyncClient(
        timeout=SCRAPE_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    if "fincaraiz" in host:
        data = _parse_fincaraiz(soup, url)
    elif "habi" in host:
        data = _parse_habi(soup, url)
    elif "metrocuadrado" in host:
        data = _parse_metrocuadrado(soup, url)
    else:
        data = _parse_generic(soup, url)

    data["url_anuncio"] = url
    data["fuente"] = host
    return data


# ─────────────────────────────────────────────
# Parsers específicos por sitio
# ─────────────────────────────────────────────

def _safe_number(text: Optional[str]) -> Optional[float]:
    """Extrae primer número (entero o decimal) de una cadena."""
    if not text:
        return None
    # Remover separadores de miles colombianos (puntos) y convertir coma a punto
    clean = re.sub(r"[^\d,.]", "", text).replace(".", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", clean)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _safe_int(text: Optional[str]) -> Optional[int]:
    v = _safe_number(text)
    return int(v) if v is not None else None


def _parse_fincaraiz(soup, url: str) -> dict:
    """Parser para fincaraiz.com.co."""
    data: dict = {}

    # Título / tipo inmueble
    title_el = soup.find("h1")
    data["titulo"] = title_el.get_text(strip=True) if title_el else ""

    # Precio
    for sel in [
        "[class*='price']", "[class*='precio']",
        "[data-test='listing-price']", "span.price",
    ]:
        el = soup.select_one(sel)
        if el:
            data["precio"] = _safe_number(el.get_text())
            break

    # Área
    for sel in ["[class*='area']", "[class*='metros']"]:
        el = soup.select_one(sel)
        if el:
            data["area_construida"] = _safe_number(el.get_text())
            break

    # Habitaciones / baños / estrato desde li/span con iconos
    text_full = soup.get_text(" ", strip=True)

    if "area_construida" not in data or not data["area_construida"]:
        m = re.search(r"(\d[\d.]*)\s*m[²2]", text_full, re.I)
        if m:
            data["area_construida"] = _safe_number(m.group(1))

    m = re.search(r"(\d+)\s*(?:hab|habitaci[oó]n|cuarto)", text_full, re.I)
    if m:
        data["habitaciones"] = int(m.group(1))

    m = re.search(r"(\d+)\s*(?:ba[ñn]o)", text_full, re.I)
    if m:
        data["banos"] = int(m.group(1))

    m = re.search(r"estrato\s*(\d)", text_full, re.I)
    if m:
        data["estrato"] = int(m.group(1))

    # Dirección / ubicación
    for sel in ["[class*='address']", "[class*='direccion']", "[class*='location']"]:
        el = soup.select_one(sel)
        if el:
            data["direccion"] = el.get_text(strip=True)
            break

    # Imagen principal
    img = soup.select_one("img[class*='photo'], img[class*='gallery'], picture img")
    if img:
        data["image"] = img.get("src") or img.get("data-src") or ""

    return data


def _parse_habi(soup, url: str) -> dict:
    """Parser para habi.co."""
    data: dict = {}
    text_full = soup.get_text(" ", strip=True)

    title_el = soup.find("h1")
    data["titulo"] = title_el.get_text(strip=True) if title_el else ""

    # Precio
    m = re.search(r"\$\s*([\d.,]+)", text_full)
    if m:
        data["precio"] = _safe_number(m.group(1))

    # Área
    m = re.search(r"(\d+)\s*m[²2]", text_full, re.I)
    if m:
        data["area_construida"] = float(m.group(1))

    m = re.search(r"(\d+)\s*(?:hab|cuarto)", text_full, re.I)
    if m:
        data["habitaciones"] = int(m.group(1))

    m = re.search(r"(\d+)\s*ba[ñn]o", text_full, re.I)
    if m:
        data["banos"] = int(m.group(1))

    m = re.search(r"estrato\s*(\d)", text_full, re.I)
    if m:
        data["estrato"] = int(m.group(1))

    img = soup.select_one("img[class*='photo'], img[class*='hero'], picture img")
    if img:
        data["image"] = img.get("src") or img.get("data-src") or ""

    return data


def _parse_metrocuadrado(soup, url: str) -> dict:
    """Parser para metrocuadrado.com."""
    return _parse_generic(soup, url)


def _parse_generic(soup, url: str) -> dict:
    """Parser genérico — extrae lo que pueda con regexes sobre el texto."""
    data: dict = {}
    text_full = soup.get_text(" ", strip=True)

    title_el = soup.find("h1")
    data["titulo"] = title_el.get_text(strip=True) if title_el else ""

    m = re.search(r"\$\s*([\d.,]+)", text_full)
    if m:
        data["precio"] = _safe_number(m.group(1))

    m = re.search(r"(\d[\d.]*)\s*m[²2]", text_full, re.I)
    if m:
        data["area_construida"] = _safe_number(m.group(1))

    m = re.search(r"(\d+)\s*(?:hab|habitaci[oó]n|cuarto)", text_full, re.I)
    if m:
        data["habitaciones"] = int(m.group(1))

    m = re.search(r"(\d+)\s*ba[ñn]o", text_full, re.I)
    if m:
        data["banos"] = int(m.group(1))

    m = re.search(r"estrato\s*(\d)", text_full, re.I)
    if m:
        data["estrato"] = int(m.group(1))

    return data
