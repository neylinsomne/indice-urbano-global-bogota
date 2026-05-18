"""
Scraper web para Properati Colombia.
Usa requests + BeautifulSoup como fallback cuando BigQuery no esta disponible.

Estrategia:
  1. Intentar API no documentada (/api/v1/properties, etc.)
  2. Si no hay API, hacer scraping HTML de las paginas de listado
  3. Paginar hasta agotar resultados o alcanzar MAX_PAGES_PER_SEARCH
"""
import time
import random
import logging
import re
import json
from typing import Optional
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

from config import (
    PROPERATI_BASE_URL,
    PROPERATI_API_ENDPOINTS,
    USER_AGENTS,
    REQUEST_DELAY_MIN,
    REQUEST_DELAY_MAX,
    MAX_PAGES_PER_SEARCH,
    REQUEST_TIMEOUT,
)

log = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    """Crea una sesion con headers realistas."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    })
    return session


def _rotate_user_agent(session: requests.Session) -> None:
    """Cambia el User-Agent de la sesion."""
    session.headers["User-Agent"] = random.choice(USER_AGENTS)


def _rate_limit() -> None:
    """Espera un tiempo aleatorio entre requests."""
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(delay)


# ── API Discovery ──────────────────────────────────────────────────

def try_undocumented_api(
    session: requests.Session,
    ciudad: str,
    tipo: str,
    transaccion: str,
) -> Optional[list]:
    """
    Intenta obtener datos de una API no documentada de Properati.
    Retorna lista de propiedades si tiene exito, None si no.
    """
    for endpoint in PROPERATI_API_ENDPOINTS:
        url = f"{PROPERATI_BASE_URL}{endpoint}"
        params = {
            "city": ciudad,
            "property_type": tipo,
            "operation": transaccion,
            "limit": 50,
            "offset": 0,
        }
        log.info(f"  Probando API: {url}")
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                # Verificar que la respuesta contenga datos utiles
                if isinstance(data, list) and len(data) > 0:
                    log.info(f"  API encontrada: {url} ({len(data)} resultados)")
                    return _scrape_via_api(session, url, ciudad, tipo, transaccion)
                elif isinstance(data, dict):
                    # Buscar en claves comunes
                    for key in ("results", "properties", "data", "items", "listings"):
                        if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                            log.info(f"  API encontrada: {url} (clave='{key}', {len(data[key])} resultados)")
                            return _scrape_via_api(session, url, ciudad, tipo, transaccion, results_key=key)
            else:
                log.debug(f"  API {endpoint} retorno {resp.status_code}")
        except (requests.exceptions.JSONDecodeError, ValueError):
            log.debug(f"  API {endpoint} no retorna JSON")
        except requests.exceptions.RequestException as e:
            log.debug(f"  API {endpoint} error: {e}")

    log.info("  No se encontro API no documentada, usando scraping HTML")
    return None


def _scrape_via_api(
    session: requests.Session,
    api_url: str,
    ciudad: str,
    tipo: str,
    transaccion: str,
    results_key: Optional[str] = None,
) -> list:
    """Pagina a traves de una API descubierta y recolecta resultados."""
    all_properties = []
    offset = 0
    page_size = 50
    page_num = 0

    while page_num < MAX_PAGES_PER_SEARCH:
        params = {
            "city": ciudad,
            "property_type": tipo,
            "operation": transaccion,
            "limit": page_size,
            "offset": offset,
        }

        try:
            _rate_limit()
            _rotate_user_agent(session)
            resp = session.get(api_url, params=params, timeout=REQUEST_TIMEOUT)

            if resp.status_code != 200:
                log.warning(f"  API retorno {resp.status_code} en offset={offset}")
                break

            data = resp.json()

            if results_key:
                items = data.get(results_key, [])
            elif isinstance(data, list):
                items = data
            else:
                items = []

            if not items:
                log.info(f"  API: sin mas resultados en offset={offset}")
                break

            for item in items:
                prop = _normalize_api_property(item, ciudad, tipo, transaccion)
                if prop:
                    all_properties.append(prop)

            log.info(f"  API pagina {page_num + 1}: {len(items)} propiedades (total: {len(all_properties)})")

            offset += page_size
            page_num += 1

        except Exception as e:
            log.error(f"  Error en API offset={offset}: {e}")
            break

    return all_properties


def _normalize_api_property(item: dict, ciudad: str, tipo: str, transaccion: str) -> Optional[dict]:
    """Normaliza un registro de la API al formato estandar."""
    try:
        prop = {
            "id_properati": str(item.get("id", item.get("property_id", ""))),
            "precio": item.get("price", item.get("precio")),
            "moneda": item.get("currency", "COP"),
            "area": item.get("surface_total", item.get("area", item.get("surface_covered"))),
            "habitaciones": item.get("rooms", item.get("bedrooms", item.get("habitaciones"))),
            "banos": item.get("bathrooms", item.get("banos")),
            "tipo_propiedad": tipo,
            "transaccion": transaccion,
            "ciudad": ciudad,
            "ubicacion": item.get("place", {}).get("name", item.get("location", "")),
            "direccion": item.get("address", item.get("direccion", "")),
            "latitud": item.get("lat", item.get("geo_lat")),
            "longitud": item.get("lon", item.get("geo_lon")),
            "imagen": item.get("image", item.get("main_image", "")),
            "descripcion": item.get("description", item.get("descripcion", "")),
            "url": item.get("url", item.get("permalink", "")),
        }
        return prop
    except Exception as e:
        log.debug(f"  Error normalizando propiedad API: {e}")
        return None


# ── HTML Scraping ───────────────────────────────────────────────────

def scrape_listings_html(
    ciudad: str,
    tipo: str,
    transaccion: str,
) -> list:
    """
    Scraping HTML de las paginas de listado de Properati.
    Pagina hasta agotar resultados o alcanzar MAX_PAGES_PER_SEARCH.
    """
    session = _get_session()

    # Intentar API primero
    api_results = try_undocumented_api(session, ciudad, tipo, transaccion)
    if api_results is not None:
        return api_results

    # Fallback: scraping HTML
    all_properties = []
    base_path = f"/s/{ciudad}/{tipo}/{transaccion}"
    page_num = 1

    while page_num <= MAX_PAGES_PER_SEARCH:
        url = f"{PROPERATI_BASE_URL}{base_path}"
        if page_num > 1:
            url = f"{url}/{page_num}"

        log.info(f"  Scrapeando pagina {page_num}: {url}")

        try:
            _rate_limit()
            _rotate_user_agent(session)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                log.info(f"  Pagina {page_num} retorno 404, fin de resultados")
                break
            elif resp.status_code != 200:
                log.warning(f"  Pagina {page_num} retorno {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Intentar extraer datos de JSON-LD o __NEXT_DATA__ embebido
            properties_from_json = _extract_from_embedded_json(soup, ciudad, tipo, transaccion)
            if properties_from_json:
                all_properties.extend(properties_from_json)
                log.info(f"  Pagina {page_num}: {len(properties_from_json)} propiedades via JSON embebido (total: {len(all_properties)})")
                page_num += 1
                continue

            # Scraping HTML de tarjetas de propiedad
            cards = _find_property_cards(soup)
            if not cards:
                log.info(f"  Pagina {page_num}: sin tarjetas de propiedad, fin de resultados")
                break

            page_properties = []
            for card in cards:
                prop = _parse_property_card(card, ciudad, tipo, transaccion)
                if prop:
                    page_properties.append(prop)

            all_properties.extend(page_properties)
            log.info(f"  Pagina {page_num}: {len(page_properties)} propiedades (total: {len(all_properties)})")

            # Verificar si hay pagina siguiente
            if not _has_next_page(soup, page_num):
                log.info(f"  No hay pagina siguiente despues de {page_num}")
                break

            page_num += 1

        except requests.exceptions.RequestException as e:
            log.error(f"  Error de red en pagina {page_num}: {e}")
            break
        except Exception as e:
            log.error(f"  Error inesperado en pagina {page_num}: {e}")
            break

    return all_properties


def _extract_from_embedded_json(
    soup: BeautifulSoup,
    ciudad: str,
    tipo: str,
    transaccion: str,
) -> Optional[list]:
    """
    Busca datos de propiedades en scripts JSON embebidos en la pagina.
    Muchos portales modernos usan __NEXT_DATA__, JSON-LD, u objetos JS.
    """
    properties = []

    # Buscar __NEXT_DATA__ (Next.js)
    next_data_script = soup.find("script", id="__NEXT_DATA__")
    if next_data_script:
        try:
            data = json.loads(next_data_script.string)
            # Navegar la estructura comun de Next.js
            page_props = data.get("props", {}).get("pageProps", {})
            listings = (
                page_props.get("listings", [])
                or page_props.get("properties", [])
                or page_props.get("results", [])
                or page_props.get("data", {}).get("listings", [])
            )
            if listings:
                for item in listings:
                    prop = _normalize_json_property(item, ciudad, tipo, transaccion)
                    if prop:
                        properties.append(prop)
                return properties if properties else None
        except (json.JSONDecodeError, AttributeError) as e:
            log.debug(f"  Error parseando __NEXT_DATA__: {e}")

    # Buscar JSON-LD
    ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in ld_scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") in ("Product", "RealEstateListing", "Offer", "Residence"):
                        prop = _normalize_jsonld_property(item, ciudad, tipo, transaccion)
                        if prop:
                            properties.append(prop)
            elif isinstance(data, dict) and data.get("@type") in ("ItemList",):
                for item in data.get("itemListElement", []):
                    prop = _normalize_jsonld_property(item, ciudad, tipo, transaccion)
                    if prop:
                        properties.append(prop)
        except (json.JSONDecodeError, AttributeError):
            continue

    # Buscar variables JS con datos de propiedades
    for script in soup.find_all("script"):
        if not script.string:
            continue
        # Patron: window.__STATE__ = {...} o similar
        for pattern in [
            r'window\.__STATE__\s*=\s*({.+?});',
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.__DATA__\s*=\s*({.+?});',
            r'var\s+properties\s*=\s*(\[.+?\]);',
        ]:
            match = re.search(pattern, script.string, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        for item in data:
                            prop = _normalize_json_property(item, ciudad, tipo, transaccion)
                            if prop:
                                properties.append(prop)
                    elif isinstance(data, dict):
                        for key in ("listings", "properties", "results", "items"):
                            if key in data and isinstance(data[key], list):
                                for item in data[key]:
                                    prop = _normalize_json_property(item, ciudad, tipo, transaccion)
                                    if prop:
                                        properties.append(prop)
                                break
                except (json.JSONDecodeError, AttributeError):
                    continue

    return properties if properties else None


def _normalize_json_property(item: dict, ciudad: str, tipo: str, transaccion: str) -> Optional[dict]:
    """Normaliza una propiedad extraida de JSON embebido."""
    try:
        # Extraer precio
        price = item.get("price", item.get("precio"))
        if isinstance(price, dict):
            price = price.get("amount", price.get("value"))

        # Extraer coordenadas
        geo = item.get("geo", item.get("geoLocation", {}))
        lat = item.get("lat", item.get("latitude", geo.get("lat", geo.get("latitude"))))
        lon = item.get("lon", item.get("longitude", geo.get("lon", geo.get("longitude"))))

        # Extraer area
        area = item.get("surface_total", item.get("area", item.get("surface")))
        if isinstance(area, dict):
            area = area.get("value")

        prop = {
            "id_properati": str(item.get("id", item.get("propertyId", item.get("slug", "")))),
            "precio": price,
            "moneda": item.get("currency", item.get("moneda", "COP")),
            "area": area,
            "habitaciones": item.get("rooms", item.get("bedrooms", item.get("habitaciones"))),
            "banos": item.get("bathrooms", item.get("banos")),
            "tipo_propiedad": tipo,
            "transaccion": transaccion,
            "ciudad": ciudad,
            "ubicacion": item.get("location", item.get("address", item.get("place", ""))),
            "direccion": item.get("address", item.get("streetAddress", "")),
            "latitud": lat,
            "longitud": lon,
            "imagen": item.get("image", item.get("mainImage", item.get("thumbnail", ""))),
            "descripcion": item.get("description", item.get("title", "")),
            "url": item.get("url", item.get("permalink", item.get("slug", ""))),
        }

        # Si la ubicacion es un dict, intentar extraer texto
        if isinstance(prop["ubicacion"], dict):
            prop["ubicacion"] = prop["ubicacion"].get("name", str(prop["ubicacion"]))

        return prop
    except Exception as e:
        log.debug(f"  Error normalizando propiedad JSON: {e}")
        return None


def _normalize_jsonld_property(item: dict, ciudad: str, tipo: str, transaccion: str) -> Optional[dict]:
    """Normaliza una propiedad JSON-LD."""
    try:
        geo = item.get("geo", {})
        prop = {
            "id_properati": str(item.get("url", item.get("@id", ""))),
            "precio": item.get("offers", {}).get("price") if isinstance(item.get("offers"), dict) else None,
            "moneda": item.get("offers", {}).get("priceCurrency", "COP") if isinstance(item.get("offers"), dict) else "COP",
            "area": item.get("floorSize", {}).get("value") if isinstance(item.get("floorSize"), dict) else None,
            "tipo_propiedad": tipo,
            "transaccion": transaccion,
            "ciudad": ciudad,
            "ubicacion": item.get("address", ""),
            "latitud": geo.get("latitude"),
            "longitud": geo.get("longitude"),
            "descripcion": item.get("description", item.get("name", "")),
            "url": item.get("url", ""),
        }
        return prop
    except Exception as e:
        log.debug(f"  Error normalizando propiedad JSON-LD: {e}")
        return None


def _find_property_cards(soup: BeautifulSoup) -> list:
    """
    Encuentra las tarjetas de propiedad en la pagina.
    Intenta multiples selectores CSS comunes en portales inmobiliarios.
    """
    # Selectores comunes en orden de probabilidad
    selectors = [
        "div.listing-card",
        "div.property-card",
        "article.listing",
        "div[data-qa='listing']",
        "div[data-testid='listing-card']",
        "a.listing-card",
        "div.card-property",
        "div.result-card",
        "li.listing-item",
        "div.CardContainer",
        # Selectores genericos
        "div[class*='listing']",
        "div[class*='property']",
        "article[class*='card']",
    ]

    for selector in selectors:
        cards = soup.select(selector)
        if cards and len(cards) >= 2:  # Al menos 2 tarjetas para evitar falsos positivos
            log.debug(f"  Selector encontrado: '{selector}' ({len(cards)} tarjetas)")
            return cards

    # Fallback: buscar por estructura
    # Muchos portales usan <a> tags con href que contiene "/propiedad/" o "/inmueble/"
    links = soup.find_all("a", href=re.compile(r'/(propiedad|inmueble|property|detalle)/'))
    if links:
        log.debug(f"  Encontrados {len(links)} links de propiedades via href pattern")
        # Devolver los padres de estos links como "tarjetas"
        cards = []
        seen = set()
        for link in links:
            parent = link.find_parent(["div", "article", "li", "section"])
            if parent and id(parent) not in seen:
                seen.add(id(parent))
                cards.append(parent)
        if cards:
            return cards

    log.debug("  No se encontraron tarjetas de propiedad con selectores conocidos")
    return []


def _parse_property_card(card, ciudad: str, tipo: str, transaccion: str) -> Optional[dict]:
    """Extrae datos de una tarjeta de propiedad HTML."""
    try:
        prop = {
            "tipo_propiedad": tipo,
            "transaccion": transaccion,
            "ciudad": ciudad,
        }

        # ID / URL
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(PROPERATI_BASE_URL, href)
            prop["url"] = href
            # Extraer ID del URL
            slug = href.rstrip("/").split("/")[-1]
            prop["id_properati"] = slug

        # Precio
        price_el = card.find(
            ["span", "div", "p"],
            class_=re.compile(r'(price|precio|amount|value)', re.I),
        )
        if not price_el:
            price_el = card.find(string=re.compile(r'\$\s*[\d.,]+'))
            if price_el:
                price_el = price_el.parent
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_match = re.search(r'[\d.,]+', price_text.replace(".", "").replace(",", "."))
            if price_match:
                try:
                    prop["precio"] = float(price_match.group(0))
                except ValueError:
                    prop["precio"] = price_text

        # Area
        area_el = card.find(
            ["span", "div", "p"],
            class_=re.compile(r'(area|superficie|surface|size)', re.I),
        )
        if not area_el:
            area_el = card.find(string=re.compile(r'\d+\s*m'))
            if area_el:
                area_el = area_el.parent
        if area_el:
            area_text = area_el.get_text(strip=True)
            area_match = re.search(r'([\d.,]+)\s*m', area_text)
            if area_match:
                try:
                    prop["area"] = float(area_match.group(1).replace(",", "."))
                except ValueError:
                    pass

        # Habitaciones
        rooms_el = card.find(
            ["span", "div"],
            class_=re.compile(r'(room|bedroom|habit|dorm|rec)', re.I),
        )
        if not rooms_el:
            rooms_el = card.find(string=re.compile(r'\d+\s*(hab|dorm|rec)', re.I))
            if rooms_el:
                rooms_el = rooms_el.parent
        if rooms_el:
            rooms_text = rooms_el.get_text(strip=True)
            rooms_match = re.search(r'(\d+)', rooms_text)
            if rooms_match:
                prop["habitaciones"] = int(rooms_match.group(1))

        # Banos
        baths_el = card.find(
            ["span", "div"],
            class_=re.compile(r'(bath|bano|baño)', re.I),
        )
        if not baths_el:
            baths_el = card.find(string=re.compile(r'\d+\s*(baño|bano|bath)', re.I))
            if baths_el:
                baths_el = baths_el.parent
        if baths_el:
            baths_text = baths_el.get_text(strip=True)
            baths_match = re.search(r'(\d+)', baths_text)
            if baths_match:
                prop["banos"] = int(baths_match.group(1))

        # Ubicacion
        loc_el = card.find(
            ["span", "div", "p", "address"],
            class_=re.compile(r'(location|ubicacion|address|barrio|zona|place)', re.I),
        )
        if loc_el:
            prop["ubicacion"] = loc_el.get_text(strip=True)

        # Imagen
        img = card.find("img")
        if img:
            prop["imagen"] = img.get("src") or img.get("data-src") or img.get("data-lazy-src", "")

        # Descripcion / titulo
        title_el = card.find(["h2", "h3", "h4", "span"], class_=re.compile(r'(title|titulo|name)', re.I))
        if title_el:
            prop["descripcion"] = title_el.get_text(strip=True)

        # Solo retornar si tiene al menos un ID
        if prop.get("id_properati") or prop.get("url"):
            return prop

        return None

    except Exception as e:
        log.debug(f"  Error parseando tarjeta: {e}")
        return None


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Verifica si existe una pagina siguiente en la paginacion."""
    # Buscar link a pagina siguiente
    next_link = soup.find("a", {"rel": "next"})
    if next_link:
        return True

    # Buscar botones de paginacion
    next_selectors = [
        "a.next",
        "a[aria-label='Next']",
        "a[aria-label='Siguiente']",
        "button.next",
        "li.next a",
        "a[class*='next']",
        "button[class*='next']",
    ]
    for sel in next_selectors:
        if soup.select_one(sel):
            return True

    # Buscar link numerico a la pagina siguiente
    next_page_num = current_page + 1
    page_link = soup.find("a", href=re.compile(rf'/{next_page_num}(\?|$|/)'))
    if page_link:
        return True

    return False


def scrape_property_detail(url: str, session: Optional[requests.Session] = None) -> Optional[dict]:
    """
    Scrapea la pagina de detalle de una propiedad individual.
    Util para enriquecer datos obtenidos del listado.
    """
    if session is None:
        session = _get_session()

    try:
        _rate_limit()
        _rotate_user_agent(session)
        resp = session.get(url, timeout=REQUEST_TIMEOUT)

        if resp.status_code != 200:
            log.warning(f"  Detalle retorno {resp.status_code}: {url}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        detail = {}

        # JSON-LD
        ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    geo = data.get("geo", {})
                    if geo:
                        detail["latitud"] = geo.get("latitude")
                        detail["longitud"] = geo.get("longitude")
                    if data.get("description"):
                        detail["descripcion"] = data["description"]
                    if data.get("address"):
                        addr = data["address"]
                        if isinstance(addr, dict):
                            detail["direccion"] = addr.get("streetAddress", "")
                        else:
                            detail["direccion"] = str(addr)
            except (json.JSONDecodeError, AttributeError):
                continue

        # Descripcion
        desc_el = soup.find(["div", "p", "section"], class_=re.compile(r'(description|descripcion)', re.I))
        if desc_el and not detail.get("descripcion"):
            detail["descripcion"] = desc_el.get_text(strip=True)[:2000]

        # Coordenadas en mapa
        if not detail.get("latitud"):
            map_el = soup.find(attrs={"data-lat": True, "data-lng": True})
            if map_el:
                detail["latitud"] = float(map_el["data-lat"])
                detail["longitud"] = float(map_el["data-lng"])

        return detail if detail else None

    except Exception as e:
        log.warning(f"  Error scrapeando detalle {url}: {e}")
        return None
