"""
Scraper para el sitio oficial de la SAE: https://www.saesas.gov.co

Estrategia:
  1. Intenta requests + BeautifulSoup (sitios .gov.co suelen ser SSR).
  2. Si detecta que el contenido requiere JS, cae a Selenium.
"""
import re
import json
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    SAE_BASE_URL,
    HEADERS,
    MAX_PAGES,
    REQUEST_DELAY,
    SELENIUM_URL,
    get_sae_search_urls,
)

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────

def _parse_precio(texto: str) -> Optional[int]:
    """Extrae precio numerico de un string como '$120.000.000'."""
    if not texto:
        return None
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else None


def _parse_area(texto: str) -> Optional[float]:
    """Extrae area de un string como '120 m2' o '120.5 m²'."""
    if not texto:
        return None
    match = re.search(r'[\d.,]+', texto.replace(',', '.'))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _clean_text(texto: Optional[str]) -> Optional[str]:
    """Limpia espacios multiples y saltos de linea."""
    if not texto:
        return None
    return re.sub(r'\s+', ' ', texto).strip()


# ── Scraper con requests + BS4 ───────────────────────────────────────

def _fetch_page(url: str, session: requests.Session) -> Optional[BeautifulSoup]:
    """Hace GET y retorna un BeautifulSoup, o None si falla."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'lxml')
    except requests.RequestException as e:
        log.warning(f"Error descargando {url}: {e}")
        return None


def _needs_javascript(soup: BeautifulSoup) -> bool:
    """Detecta si la pagina depende de JS para renderizar contenido."""
    body_text = soup.get_text(strip=True) if soup.body else ""
    # Senales tipicas de una SPA o pagina JS-only
    indicators = [
        len(body_text) < 200,
        soup.find('div', id='__next') is not None,
        soup.find('div', id='app') is not None and len(body_text) < 500,
        soup.find('noscript', string=re.compile(r'(habilitar|enable)\s+javascript', re.I)) is not None,
    ]
    return any(indicators)


def _extract_item_from_card(card, departamento: str) -> Optional[dict]:
    """
    Extrae datos de un 'card' de inmueble del HTML de SAE.
    Los selectores se ajustaran al DOM real; estos son estimaciones
    basadas en la estructura tipica de portales .gov.co.
    """
    try:
        # Codigo SAE -- buscar en atributos data-* o en texto
        codigo_sae = None
        codigo_el = card.find(string=re.compile(r'(c[oó]digo|ref)', re.I))
        if codigo_el:
            match = re.search(r'[A-Z0-9\-]+\d+', codigo_el.parent.get_text())
            if match:
                codigo_sae = match.group()
        # Tambien en data-id o similar
        if not codigo_sae:
            codigo_sae = card.get('data-id') or card.get('data-codigo')

        # Titulo / tipo de inmueble
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

        # Precio base
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
        estado_el = card.find(string=re.compile(r'(estado|etapa|fase)', re.I))
        if estado_el:
            estado_proceso = _clean_text(estado_el.parent.get_text())

        # Tipo de venta
        tipo_venta = None
        venta_el = card.find(string=re.compile(r'(subasta|venta\s+directa|remate)', re.I))
        if venta_el:
            tipo_venta = _clean_text(str(venta_el))

        # Fecha de subasta
        fecha_subasta = None
        fecha_el = card.find(string=re.compile(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}'))
        if fecha_el:
            fecha_subasta = str(fecha_el).strip()

        # Imagen
        image = None
        img_el = card.find('img')
        if img_el:
            src = img_el.get('src') or img_el.get('data-src')
            if src:
                image = src if src.startswith('http') else SAE_BASE_URL + src

        # Link al detalle
        link = None
        link_el = card.find('a', href=True)
        if link_el:
            href = link_el['href']
            link = href if href.startswith('http') else SAE_BASE_URL + href

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
            'fuente': 'sae',
        }
    except Exception as e:
        log.warning(f"Error extrayendo card: {e}")
        return None


def _scrape_detail_page(url: str, session: requests.Session) -> dict:
    """Visita la pagina de detalle de un inmueble para enriquecer datos."""
    extra = {}
    soup = _fetch_page(url, session)
    if not soup:
        return extra

    # Intentar extraer JSON-LD
    script = soup.find('script', type='application/ld+json')
    if script:
        try:
            data = json.loads(script.string)
            extra['json_ld'] = data
        except (json.JSONDecodeError, TypeError):
            pass

    # Descripcion completa
    desc_el = soup.find(class_=re.compile(r'(descripcion|description|detalle)', re.I))
    if desc_el:
        extra['descripcion_completa'] = _clean_text(desc_el.get_text())

    return extra


# ── Scraper con Selenium (fallback) ──────────────────────────────────

def _scrape_with_selenium(search_urls: list) -> list:
    """Fallback: usa Selenium para paginas JS-heavy."""
    log.info("Activando fallback Selenium para SAE...")
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
                log.info(f"  [Selenium] {departamento} pagina {page}: {page_url}")

                try:
                    driver.get(page_url)
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
                    )
                    time.sleep(3)  # Esperar renderizado JS

                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'lxml')

                    # Buscar cards de inmuebles
                    cards = soup.find_all(
                        class_=re.compile(r'(card|item|propiedad|inmueble|result)', re.I)
                    )

                    if not cards:
                        # Intentar contenedores alternativos
                        cards = soup.find_all('article')
                    if not cards:
                        cards = soup.find_all('div', class_=re.compile(r'(col|grid)', re.I))

                    if not cards:
                        log.info(f"  [Selenium] Sin resultados en pagina {page}, fin.")
                        break

                    page_items = 0
                    for card in cards:
                        item = _extract_item_from_card(card, departamento)
                        if item and (item.get('codigo_sae') or item.get('titulo')):
                            items.append(item)
                            page_items += 1

                    log.info(f"  [Selenium] {departamento} p.{page}: {page_items} inmuebles")

                    if page_items == 0:
                        break

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

def scrape_sae() -> list:
    """
    Scrapea el portal oficial de la SAE.
    Retorna lista de dicts con la info de cada inmueble.
    """
    search_urls = get_sae_search_urls()
    all_items = []
    use_selenium = False

    session = requests.Session()
    session.headers.update(HEADERS)

    for entry in search_urls:
        url = entry['url']
        departamento = entry['departamento']
        page = 1

        log.info(f"Scrapeando SAE - {departamento}")

        while page <= MAX_PAGES:
            page_url = f"{url}&page={page}" if '?' in url else f"{url}?page={page}"
            log.info(f"  {departamento} pagina {page}: {page_url}")

            soup = _fetch_page(page_url, session)
            if not soup:
                break

            # Detectar si necesitamos JS
            if page == 1 and _needs_javascript(soup):
                log.warning(f"  {departamento}: contenido requiere JavaScript, cambiando a Selenium")
                use_selenium = True
                break

            # Buscar cards de inmuebles: probar varios selectores
            cards = soup.find_all(
                class_=re.compile(r'(card|item|propiedad|inmueble|result)', re.I)
            )
            if not cards:
                cards = soup.find_all('article')
            if not cards:
                # Tabla? Algunos portales gov usan tablas
                rows = soup.find_all('tr')
                if len(rows) > 1:
                    cards = rows[1:]  # Skip header

            if not cards:
                log.info(f"  Sin resultados en pagina {page}, fin de {departamento}.")
                break

            page_items = 0
            for card in cards:
                item = _extract_item_from_card(card, departamento)
                if item and (item.get('codigo_sae') or item.get('titulo')):
                    # Intentar enriquecer desde pagina de detalle
                    if item.get('link'):
                        time.sleep(REQUEST_DELAY / 2)
                        extra = _scrape_detail_page(item['link'], session)
                        if extra.get('descripcion_completa'):
                            item['descripcion'] = extra['descripcion_completa']
                        if extra.get('json_ld'):
                            item['json_ld'] = extra['json_ld']

                    all_items.append(item)
                    page_items += 1

            log.info(f"  {departamento} p.{page}: {page_items} inmuebles extraidos")

            if page_items == 0:
                break

            page += 1
            time.sleep(REQUEST_DELAY)

        if use_selenium:
            break

    # Fallback a Selenium si fue necesario
    if use_selenium:
        all_items = _scrape_with_selenium(search_urls)

    log.info(f"SAE oficial: {len(all_items)} inmuebles totales")
    return all_items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    results = scrape_sae()
    log.info(f"Resultados: {len(results)}")
    for r in results[:5]:
        log.info(f"  {r.get('codigo_sae')} | {r.get('tipo_inmueble')} | ${r.get('precio_base')} | {r.get('departamento')}")
