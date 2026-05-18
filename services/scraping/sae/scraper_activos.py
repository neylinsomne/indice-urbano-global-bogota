"""
Scraper para Activos por Colombia: https://www.activosporcolombia.com

Es la plataforma moderna de subastas de bienes incautados.
Suele tener datos estructurados (JSON embebido, API interna) ya que
es una webapp mas reciente que el portal .gov.co.

Estrategia:
  1. Buscar APIs internas / JSON embebido en el page source.
  2. Fallback a parsing HTML con BeautifulSoup.
  3. Ultimo recurso: Selenium.
"""
import re
import json
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    ACTIVOS_BASE_URL,
    HEADERS,
    MAX_PAGES,
    REQUEST_DELAY,
    SELENIUM_URL,
    get_activos_search_urls,
)

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────

def _parse_precio(texto: str) -> Optional[int]:
    if not texto:
        return None
    limpio = re.sub(r'[^\d]', '', str(texto))
    return int(limpio) if limpio else None


def _parse_area(texto: str) -> Optional[float]:
    if not texto:
        return None
    match = re.search(r'[\d.,]+', str(texto).replace(',', '.'))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _clean_text(texto: Optional[str]) -> Optional[str]:
    if not texto:
        return None
    return re.sub(r'\s+', ' ', texto).strip()


# ── Extraccion de datos JSON embebidos ───────────────────────────────

def _extract_json_data(page_text: str) -> list:
    """
    Busca datos JSON embebidos en el source de la pagina.
    Muchas plataformas modernas inyectan el state como
    window.__INITIAL_STATE__, __NEXT_DATA__, o scripts JSON-LD.
    """
    items = []

    # Patron 1: __NEXT_DATA__ (Next.js)
    match = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_text, re.S)
    if match:
        try:
            data = json.loads(match.group(1))
            props = data.get('props', {}).get('pageProps', {})
            # Navegar la estructura buscando lista de inmuebles
            for key in ['inmuebles', 'items', 'results', 'properties', 'activos', 'data']:
                if key in props and isinstance(props[key], list):
                    items.extend(props[key])
                    break
            # Tambien buscar un nivel mas profundo
            if not items:
                for v in props.values():
                    if isinstance(v, dict):
                        for k2 in ['inmuebles', 'items', 'results', 'data', 'activos']:
                            if k2 in v and isinstance(v[k2], list):
                                items.extend(v[k2])
                                break
                    if items:
                        break
        except (json.JSONDecodeError, TypeError) as e:
            log.debug(f"Error parseando __NEXT_DATA__: {e}")

    # Patron 2: window.__INITIAL_STATE__ o similar
    if not items:
        match = re.search(r'window\.__(?:INITIAL_STATE|PRELOADED_STATE)__\s*=\s*({.*?});?\s*</script>', page_text, re.S)
        if match:
            try:
                data = json.loads(match.group(1))
                # Buscar listas de inmuebles en la estructura
                items = _find_items_in_dict(data)
            except (json.JSONDecodeError, TypeError):
                pass

    # Patron 3: JSON-LD
    if not items:
        soup = BeautifulSoup(page_text, 'lxml')
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    items.extend(data)
                elif isinstance(data, dict):
                    # ItemList
                    if data.get('@type') == 'ItemList':
                        for el in data.get('itemListElement', []):
                            if isinstance(el, dict):
                                items.append(el.get('item', el))
            except (json.JSONDecodeError, TypeError):
                pass

    # Patron 4: API endpoint en scripts
    if not items:
        api_matches = re.findall(r'["\'](/api/[^"\']+inmuebles?[^"\']*)["\']', page_text, re.I)
        if not api_matches:
            api_matches = re.findall(r'["\'](/api/[^"\']+activos?[^"\']*)["\']', page_text, re.I)
        for api_path in api_matches:
            try:
                api_url = ACTIVOS_BASE_URL + api_path
                log.info(f"  Encontrada API interna: {api_url}")
                resp = requests.get(api_url, headers=HEADERS, timeout=15)
                if resp.ok:
                    data = resp.json()
                    if isinstance(data, list):
                        items.extend(data)
                    elif isinstance(data, dict):
                        for key in ['data', 'items', 'results', 'inmuebles', 'activos']:
                            if key in data and isinstance(data[key], list):
                                items.extend(data[key])
                                break
                    if items:
                        break
            except Exception as e:
                log.debug(f"Error llamando API {api_path}: {e}")

    return items


def _find_items_in_dict(data: dict, depth: int = 0) -> list:
    """Busca recursivamente listas de inmuebles en un diccionario."""
    if depth > 5:
        return []
    for key in ['inmuebles', 'items', 'results', 'properties', 'activos', 'data']:
        if key in data and isinstance(data[key], list) and len(data[key]) > 0:
            return data[key]
    # Buscar un nivel mas profundo
    for v in data.values():
        if isinstance(v, dict):
            found = _find_items_in_dict(v, depth + 1)
            if found:
                return found
    return []


def _normalize_json_item(raw: dict, departamento: str) -> dict:
    """
    Normaliza un item JSON (de API o __NEXT_DATA__) al esquema comun SAE.
    Los nombres de campo varian segun la implementacion del portal;
    se prueban multiples variantes.
    """
    def _get(*keys):
        for k in keys:
            v = raw.get(k)
            if v is not None and str(v).strip():
                return v
        return None

    codigo_sae = _get('codigoSae', 'codigo_sae', 'codigo', 'id', 'ref', 'referencia', 'codigoActivo')
    precio_raw = _get('precioBase', 'precio_base', 'precio', 'valorBase', 'valor', 'price')
    tipo_inmueble = _get('tipoInmueble', 'tipo_inmueble', 'tipo', 'propertyType', 'tipoActivo')
    area_raw = _get('area', 'areaConstruida', 'area_construida', 'areaTerreno', 'size')
    departamento_raw = _get('departamento', 'department', 'estado') or departamento
    ciudad = _get('ciudad', 'municipio', 'city', 'ubicacion')
    direccion = _get('direccion', 'address', 'dir')
    descripcion = _get('descripcion', 'description', 'detalle')
    estado_proceso = _get('estadoProceso', 'estado_proceso', 'estado', 'status')
    tipo_venta = _get('tipoVenta', 'tipo_venta', 'modalidadVenta', 'saleType')
    fecha_subasta = _get('fechaSubasta', 'fecha_subasta', 'fechaEvento', 'auctionDate')

    image = _get('imagen', 'image', 'foto', 'urlImagen', 'imagenPrincipal', 'thumbnail')
    if image and not str(image).startswith('http'):
        image = ACTIVOS_BASE_URL + str(image)

    link = _get('url', 'link', 'detailUrl', 'slug')
    if link and not str(link).startswith('http'):
        link = ACTIVOS_BASE_URL + '/' + str(link).lstrip('/')

    return {
        'codigo_sae': str(codigo_sae) if codigo_sae else None,
        'precio_base': _parse_precio(str(precio_raw)) if precio_raw else None,
        'tipo_inmueble': str(tipo_inmueble).capitalize() if tipo_inmueble else None,
        'area': _parse_area(str(area_raw)) if area_raw else None,
        'departamento': str(departamento_raw).lower().replace(' ', '-') if departamento_raw else departamento,
        'ciudad': _clean_text(str(ciudad)) if ciudad else None,
        'direccion': _clean_text(str(direccion)) if direccion else None,
        'descripcion': _clean_text(str(descripcion)) if descripcion else None,
        'estado_proceso': _clean_text(str(estado_proceso)) if estado_proceso else None,
        'tipo_venta': _clean_text(str(tipo_venta)) if tipo_venta else None,
        'fecha_subasta': str(fecha_subasta) if fecha_subasta else None,
        'image': str(image) if image else None,
        'link': str(link) if link else None,
        'fuente': 'activos_por_colombia',
        'raw': raw,
    }


# ── Scraper HTML (BS4) ───────────────────────────────────────────────

def _extract_item_from_html(card, departamento: str) -> Optional[dict]:
    """Extrae datos de un card HTML de Activos por Colombia."""
    try:
        # Codigo SAE
        codigo_sae = None
        codigo_el = card.find(string=re.compile(r'(c[oó]digo|ref)', re.I))
        if codigo_el:
            match = re.search(r'[A-Z0-9\-]+\d+', codigo_el.parent.get_text())
            if match:
                codigo_sae = match.group()
        if not codigo_sae:
            codigo_sae = card.get('data-id') or card.get('data-codigo')

        # Titulo
        titulo_el = card.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'(titulo|title|nombre)', re.I))
        if not titulo_el:
            titulo_el = card.find(['h2', 'h3', 'h4'])
        titulo = _clean_text(titulo_el.get_text()) if titulo_el else None

        tipo_inmueble = None
        if titulo:
            for t in ['apartamento', 'casa', 'lote', 'bodega', 'local', 'finca', 'oficina']:
                if t in titulo.lower():
                    tipo_inmueble = t.capitalize()
                    break

        # Precio
        precio_el = card.find(string=re.compile(r'\$[\d.,]+'))
        if not precio_el:
            precio_el = card.find(class_=re.compile(r'(precio|price|valor)', re.I))
        precio_text = precio_el.get_text() if precio_el and hasattr(precio_el, 'get_text') else str(precio_el) if precio_el else None
        precio_base = _parse_precio(precio_text)

        # Area
        area = None
        area_el = card.find(string=re.compile(r'\d+\s*m[²2]', re.I))
        if area_el:
            area = _parse_area(str(area_el))

        # Ciudad
        ciudad = None
        ciudad_el = card.find(class_=re.compile(r'(ciudad|city|ubicacion|location)', re.I))
        if ciudad_el:
            ciudad = _clean_text(ciudad_el.get_text())

        # Direccion
        direccion = None
        dir_el = card.find(class_=re.compile(r'(direccion|address)', re.I))
        if dir_el:
            direccion = _clean_text(dir_el.get_text())

        # Descripcion
        descripcion = None
        desc_el = card.find(class_=re.compile(r'(descripcion|description|detalle)', re.I))
        if desc_el:
            descripcion = _clean_text(desc_el.get_text())

        # Estado del proceso
        estado_proceso = None
        estado_el = card.find(string=re.compile(r'(estado|etapa)', re.I))
        if estado_el:
            estado_proceso = _clean_text(estado_el.parent.get_text())

        # Tipo de venta
        tipo_venta = None
        venta_el = card.find(string=re.compile(r'(subasta|venta\s+directa|remate)', re.I))
        if venta_el:
            tipo_venta = _clean_text(str(venta_el))

        # Fecha subasta
        fecha_subasta = None
        fecha_el = card.find(string=re.compile(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}'))
        if fecha_el:
            fecha_subasta = str(fecha_el).strip()

        # Imagen
        image = None
        img_el = card.find('img')
        if img_el:
            src = img_el.get('src') or img_el.get('data-src') or img_el.get('data-lazy-src')
            if src:
                image = src if src.startswith('http') else ACTIVOS_BASE_URL + src

        # Link al detalle
        link = None
        link_el = card.find('a', href=True)
        if link_el:
            href = link_el['href']
            link = href if href.startswith('http') else ACTIVOS_BASE_URL + href

        return {
            'codigo_sae': codigo_sae,
            'precio_base': precio_base,
            'tipo_inmueble': tipo_inmueble,
            'area': area,
            'departamento': departamento,
            'ciudad': ciudad,
            'direccion': direccion,
            'descripcion': descripcion,
            'estado_proceso': estado_proceso,
            'tipo_venta': tipo_venta,
            'fecha_subasta': fecha_subasta,
            'image': image,
            'link': link,
            'titulo': titulo,
            'fuente': 'activos_por_colombia',
        }
    except Exception as e:
        log.warning(f"Error extrayendo card HTML: {e}")
        return None


# ── Scraper Selenium (ultimo recurso) ────────────────────────────────

def _scrape_with_selenium(search_urls: list) -> list:
    """Usa Selenium cuando no hay JSON ni HTML util."""
    log.info("Activando Selenium para Activos por Colombia...")
    items = []

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Remote(command_executor=SELENIUM_URL, options=opts)
    except Exception as e:
        log.error(f"No se pudo iniciar Selenium: {e}")
        return items

    try:
        for entry in search_urls:
            url = entry['url']
            departamento = entry['departamento']
            page = 1

            while page <= MAX_PAGES:
                page_url = f"{url}&page={page}" if '?' in url else f"{url}?page={page}"
                log.info(f"  [Selenium] {departamento} p.{page}: {page_url}")

                try:
                    driver.get(page_url)
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
                    )
                    time.sleep(3)

                    page_source = driver.page_source

                    # Intentar JSON primero incluso con Selenium
                    json_items = _extract_json_data(page_source)
                    if json_items:
                        for raw in json_items:
                            item = _normalize_json_item(raw, departamento)
                            if item.get('codigo_sae') or item.get('tipo_inmueble'):
                                items.append(item)
                        log.info(f"  [Selenium] JSON: {len(json_items)} items en p.{page}")
                        page += 1
                        time.sleep(REQUEST_DELAY)
                        continue

                    # Fallback a HTML
                    soup = BeautifulSoup(page_source, 'lxml')
                    cards = soup.find_all(class_=re.compile(r'(card|item|propiedad|inmueble|result)', re.I))
                    if not cards:
                        cards = soup.find_all('article')

                    if not cards:
                        log.info(f"  [Selenium] Sin resultados en p.{page}, fin.")
                        break

                    page_items = 0
                    for card in cards:
                        item = _extract_item_from_html(card, departamento)
                        if item and (item.get('codigo_sae') or item.get('titulo')):
                            items.append(item)
                            page_items += 1

                    if page_items == 0:
                        break

                    log.info(f"  [Selenium] {departamento} p.{page}: {page_items} items")
                    page += 1
                    time.sleep(REQUEST_DELAY)

                except Exception as e:
                    log.warning(f"  [Selenium] Error en {page_url}: {e}")
                    break
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return items


# ── Funcion principal ─────────────────────────────────────────────────

def scrape_activos() -> list:
    """
    Scrapea Activos por Colombia.
    Prioriza extraccion de JSON embebido; fallback a HTML y Selenium.
    Retorna lista de dicts normalizados.
    """
    search_urls = get_activos_search_urls()
    all_items = []

    session = requests.Session()
    session.headers.update(HEADERS)

    for entry in search_urls:
        url = entry['url']
        departamento = entry['departamento']
        page = 1

        log.info(f"Scrapeando Activos por Colombia - {departamento}")

        while page <= MAX_PAGES:
            page_url = f"{url}&page={page}" if '?' in url else f"{url}?page={page}"
            log.info(f"  {departamento} pagina {page}: {page_url}")

            try:
                resp = session.get(page_url, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                log.warning(f"  Error HTTP en {page_url}: {e}")
                break

            page_text = resp.text

            # 1. Intentar JSON embebido
            json_items = _extract_json_data(page_text)
            if json_items:
                for raw in json_items:
                    item = _normalize_json_item(raw, departamento)
                    if item.get('codigo_sae') or item.get('tipo_inmueble'):
                        all_items.append(item)

                log.info(f"  {departamento} p.{page}: {len(json_items)} items (JSON)")
                page += 1
                time.sleep(REQUEST_DELAY)
                continue

            # 2. Parsing HTML
            soup = BeautifulSoup(page_text, 'lxml')

            # Detectar si necesita JS
            body_text = soup.get_text(strip=True) if soup.body else ""
            if len(body_text) < 200 or soup.find('div', id='__next'):
                log.warning(f"  {departamento}: pagina parece JS-only, cambiando a Selenium")
                selenium_items = _scrape_with_selenium(search_urls)
                all_items.extend(selenium_items)
                return all_items  # Selenium ya procesa todos los deptos

            cards = soup.find_all(
                class_=re.compile(r'(card|item|propiedad|inmueble|result)', re.I)
            )
            if not cards:
                cards = soup.find_all('article')
            if not cards:
                rows = soup.find_all('tr')
                if len(rows) > 1:
                    cards = rows[1:]

            if not cards:
                log.info(f"  Sin resultados en p.{page}, fin de {departamento}.")
                break

            page_items = 0
            for card in cards:
                item = _extract_item_from_html(card, departamento)
                if item and (item.get('codigo_sae') or item.get('titulo')):
                    all_items.append(item)
                    page_items += 1

            log.info(f"  {departamento} p.{page}: {page_items} items (HTML)")

            if page_items == 0:
                break

            page += 1
            time.sleep(REQUEST_DELAY)

    log.info(f"Activos por Colombia: {len(all_items)} inmuebles totales")
    return all_items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    results = scrape_activos()
    log.info(f"Resultados: {len(results)}")
    for r in results[:5]:
        log.info(f"  {r.get('codigo_sae')} | {r.get('tipo_inmueble')} | ${r.get('precio_base')} | {r.get('departamento')}")
