"""
Scraper Bancolombia REO -- Selenium + worker threads.
Navega listados de inmuebles recuperados, extrae tarjetas de propiedad
y sigue los links de detalle para obtener datos completos.
"""
import json
import logging
import os
import re
import time
from queue import Queue, Empty
from threading import Thread

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    SessionNotCreatedException,
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
)

from config import (
    BANCOLOMBIA_BASE_URL,
    BANCOLOMBIA_SEARCH_PATHS,
)

log = logging.getLogger(__name__)

# ── Selenium URLs (comma-separated) ───────────────────────────────
SELENIUM_URLS = os.getenv(
    "SELENIUM_URLS",
    "http://localhost:4444/wd/hub",
).split(",")

RESTART_EVERY = 30  # Reiniciar Chrome cada N paginas para liberar memoria
PAGE_LOAD_TIMEOUT = 20  # Segundos de espera para carga de pagina
DETAIL_TIMEOUT = 15


# ── Helpers ────────────────────────────────────────────────────────

def _crear_driver(selenium_url: str):
    """Crea una instancia remota de Chrome."""
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Remote(command_executor=selenium_url, options=options)


def _safe_text(element):
    """Extrae texto limpio de un WebElement o devuelve None."""
    try:
        return element.text.strip() if element else None
    except Exception:
        return None


def _parse_precio(raw: str):
    """Extrae valor numerico de un string de precio colombiano."""
    if not raw:
        return None
    nums = re.sub(r"[^\d]", "", raw)
    return int(nums) if nums else None


def _parse_area(raw: str):
    """Extrae metros cuadrados de un string como '65 m2'."""
    if not raw:
        return None
    match = re.search(r"([\d.,]+)", raw.replace(",", "."))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _parse_int(raw: str):
    """Extrae entero de texto."""
    if not raw:
        return None
    match = re.search(r"(\d+)", raw)
    return int(match.group(1)) if match else None


# ── Descubrimiento del endpoint correcto ───────────────────────────

def _resolve_search_url(driver, ciudad: str) -> str | None:
    """
    Prueba los endpoints conocidos y devuelve el primero que cargue
    contenido de inmuebles para la ciudad dada.
    """
    for path in BANCOLOMBIA_SEARCH_PATHS:
        url = f"{BANCOLOMBIA_BASE_URL}{path}?ciudad={ciudad}"
        log.info(f"  Probando endpoint: {url}")
        try:
            driver.get(url)
            time.sleep(3)
            # Buscar evidencia de tarjetas de propiedad en el DOM
            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = (
                soup.select(".card-inmueble")
                or soup.select("[class*='propert']")
                or soup.select("[class*='inmueble']")
                or soup.select("[class*='card']")
                or soup.select("article")
            )
            if cards:
                log.info(f"  Endpoint activo: {path} ({len(cards)} tarjetas encontradas)")
                return url
        except Exception as exc:
            log.warning(f"  Endpoint {path} fallo: {exc}")
    return None


# ── Extraccion de tarjetas en pagina de listado ────────────────────

def _extract_cards_from_page(driver) -> list[dict]:
    """
    Analiza el DOM actual del driver y extrae datos basicos de cada
    tarjeta de propiedad visible.  Devuelve lista de dicts con al
    menos 'detail_url' para seguir al detalle.
    """
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Selectores en orden de probabilidad
    card_selectors = [
        ".card-inmueble",
        "[class*='propert']",
        "[class*='inmueble']",
        "article.card",
        ".card",
        "article",
    ]

    cards_html = []
    for sel in card_selectors:
        cards_html = soup.select(sel)
        if cards_html:
            break

    results = []
    for card in cards_html:
        data = {}

        # Link de detalle
        link_tag = card.find("a", href=True)
        if link_tag:
            href = link_tag["href"]
            if not href.startswith("http"):
                href = BANCOLOMBIA_BASE_URL + href
            data["detail_url"] = href

        # Precio
        precio_el = (
            card.select_one("[class*='precio']")
            or card.select_one("[class*='price']")
            or card.find(string=re.compile(r"\$"))
        )
        if precio_el:
            raw = precio_el if isinstance(precio_el, str) else precio_el.get_text()
            data["precio_lista"] = _parse_precio(raw)

        # Tipo de inmueble
        tipo_el = card.select_one("[class*='tipo']") or card.select_one("[class*='type']")
        if tipo_el:
            data["tipo"] = tipo_el.get_text(strip=True)

        # Ciudad / ubicacion
        ubic_el = (
            card.select_one("[class*='ciudad']")
            or card.select_one("[class*='ubic']")
            or card.select_one("[class*='location']")
        )
        if ubic_el:
            data["ubicacion_lista"] = ubic_el.get_text(strip=True)

        # Imagen
        img = card.find("img", src=True)
        if img:
            data["image"] = img["src"]

        if data.get("detail_url"):
            results.append(data)

    return results


# ── Extraccion de detalle ──────────────────────────────────────────

def _scrape_detail(driver, url: str) -> dict | None:
    """Navega a la pagina de detalle de un inmueble y extrae todos los campos."""
    try:
        driver.get(url)
        WebDriverWait(driver, DETAIL_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)  # Esperar renderizado SPA

        soup = BeautifulSoup(driver.page_source, "html.parser")
        data = {"url_detalle": url}

        # ── Codigo / referencia ────────────────────────────────────
        for pattern in [r"[Cc][oó]digo[:\s]*([\w\-]+)", r"[Rr]ef(?:erencia)?[:\s]*([\w\-]+)"]:
            match = re.search(pattern, soup.get_text())
            if match:
                data["codigo"] = match.group(1)
                break

        # ── Precio de venta ────────────────────────────────────────
        precio_el = (
            soup.select_one("[class*='precio']")
            or soup.select_one("[class*='price']")
            or soup.find(string=re.compile(r"\$\s*[\d.,]+"))
        )
        if precio_el:
            raw = precio_el if isinstance(precio_el, str) else precio_el.get_text()
            data["precio"] = _parse_precio(raw)

        # ── Precio avaluo ──────────────────────────────────────────
        avaluo_el = soup.find(string=re.compile(r"[Aa]val[uú]o"))
        if avaluo_el:
            parent = avaluo_el.find_parent()
            if parent:
                nums = re.findall(r"[\d.,]+", parent.get_text())
                for n in nums:
                    val = _parse_precio(n)
                    if val and val > 1_000_000:
                        data["precio_avaluo"] = val
                        break

        # ── Tabla / lista de caracteristicas ───────────────────────
        _extract_features(soup, data)

        # ── Descripcion ───────────────────────────────────────────
        desc_el = (
            soup.select_one("[class*='descripcion']")
            or soup.select_one("[class*='description']")
            or soup.find("p", string=re.compile(r".{60,}"))
        )
        if desc_el:
            data["descripcion"] = desc_el.get_text(strip=True)[:2000]

        # ── Estado juridico ────────────────────────────────────────
        juridico_el = soup.find(string=re.compile(r"[Jj]ur[ií]dico|[Ee]stado\s+legal"))
        if juridico_el:
            parent = juridico_el.find_parent()
            if parent:
                data["estado_juridico"] = parent.get_text(strip=True)[:500]

        # ── Imagen principal ──────────────────────────────────────
        img = soup.select_one("img[class*='principal']") or soup.select_one("img[class*='main']")
        if not img:
            imgs = soup.find_all("img", src=True)
            for i in imgs:
                src = i.get("src", "")
                if "inmueble" in src or "propert" in src or "foto" in src or src.startswith("http"):
                    img = i
                    break
        if img:
            data["image"] = img.get("src")

        # ── Coordenadas (JSON-LD o data attributes) ───────────────
        _extract_coordinates(soup, driver, data)

        # ── Direccion ──────────────────────────────────────────────
        dir_el = (
            soup.select_one("[class*='direccion']")
            or soup.select_one("[class*='address']")
            or soup.find(string=re.compile(r"[Dd]irecci[oó]n"))
        )
        if dir_el:
            raw = dir_el if isinstance(dir_el, str) else dir_el.get_text(strip=True)
            data["direccion"] = raw[:300]

        return data

    except TimeoutException:
        log.warning(f"Timeout cargando detalle: {url}")
        return None
    except Exception as exc:
        log.warning(f"Error en detalle {url}: {exc}")
        return None


def _extract_features(soup: BeautifulSoup, data: dict):
    """Extrae area, habitaciones, banos, estrato, tipo, ciudad, barrio del HTML."""
    text = soup.get_text(separator="\n")

    feature_patterns = {
        "area": [r"[AÁa]rea[:\s]*([\d.,]+)\s*m", r"([\d.,]+)\s*m[2²]"],
        "habitaciones": [r"[Hh]abitaci[oó]n(?:es)?[:\s]*(\d+)", r"(\d+)\s*[Hh]ab"],
        "banos": [r"[Bb]a[nñ]o(?:s)?[:\s]*(\d+)", r"(\d+)\s*[Bb]a[nñ]"],
        "estrato": [r"[Ee]strato[:\s]*(\d+)"],
        "tipo": [r"[Tt]ipo[:\s]*([\w\s]+?)(?:\n|$)"],
        "ciudad": [r"[Cc]iudad[:\s]*([\w\s]+?)(?:\n|$)"],
        "barrio": [r"[Bb]arrio[:\s]*([\w\s]+?)(?:\n|$)", r"[Ss]ector[:\s]*([\w\s]+?)(?:\n|$)"],
    }

    for key, patterns in feature_patterns.items():
        if key in data:
            continue
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                val = match.group(1).strip()
                if key == "area":
                    data[key] = _parse_area(val)
                elif key in ("habitaciones", "banos", "estrato"):
                    data[key] = _parse_int(val)
                else:
                    data[key] = val
                break

    # Tambien intentar via <li>, <td>, <span> con labels
    label_map = {
        "area": ["area", "superficie", "m2"],
        "habitaciones": ["habitacion", "alcoba", "cuarto", "bedroom"],
        "banos": ["bano", "baño", "bathroom"],
        "estrato": ["estrato"],
        "tipo": ["tipo inmueble", "tipo de inmueble", "property type"],
        "barrio": ["barrio", "sector", "zona"],
        "ciudad": ["ciudad", "city", "municipio"],
    }

    for li in soup.find_all(["li", "tr", "div", "span"]):
        li_text = li.get_text(separator=" ", strip=True).lower()
        for key, keywords in label_map.items():
            if key in data:
                continue
            for kw in keywords:
                if kw in li_text:
                    # El valor suele estar despues del label
                    parts = re.split(r"[:\s]{2,}", li_text, maxsplit=1)
                    if len(parts) == 2:
                        val = parts[1].strip()
                    else:
                        val = li_text.replace(kw, "").strip()
                    if val:
                        if key == "area":
                            data[key] = _parse_area(val)
                        elif key in ("habitaciones", "banos", "estrato"):
                            data[key] = _parse_int(val)
                        else:
                            data[key] = val[:200]
                        break


def _extract_coordinates(soup: BeautifulSoup, driver, data: dict):
    """Intenta extraer lat/lon de JSON-LD, meta tags o scripts."""
    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string)
            if isinstance(ld, dict):
                geo = ld.get("geo") or ld
                lat = geo.get("latitude") or ld.get("latitude")
                lon = geo.get("longitude") or ld.get("longitude")
                if lat and lon:
                    data["lat"] = float(lat)
                    data["lon"] = float(lon)
                    return
        except (json.JSONDecodeError, ValueError):
            continue

    # Meta tags
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        if "latitude" in name:
            try:
                data["lat"] = float(meta.get("content", ""))
            except ValueError:
                pass
        elif "longitude" in name:
            try:
                data["lon"] = float(meta.get("content", ""))
            except ValueError:
                pass

    # Regex en scripts para coordenadas
    for script in soup.find_all("script"):
        if not script.string:
            continue
        lat_match = re.search(r"[\"']?lat(?:itude)?[\"']?\s*[:=]\s*([-\d.]+)", script.string)
        lon_match = re.search(r"[\"']?(?:lng|lon(?:gitude)?)[\"']?\s*[:=]\s*([-\d.]+)", script.string)
        if lat_match and lon_match:
            try:
                data["lat"] = float(lat_match.group(1))
                data["lon"] = float(lon_match.group(1))
                return
            except ValueError:
                pass


# ── Paginacion ─────────────────────────────────────────────────────

def _go_next_page(driver) -> bool:
    """
    Intenta navegar a la siguiente pagina de resultados.
    Devuelve True si lo logro, False si no hay mas paginas.
    """
    try:
        # Boton "Siguiente" o ">" o "next"
        next_selectors = [
            "a[aria-label='Next']",
            "a[aria-label='Siguiente']",
            "button[aria-label='Next']",
            "button[aria-label='Siguiente']",
            "[class*='next']",
            "[class*='siguiente']",
            "a.page-link:last-child",
            "li.page-item:last-child a",
        ]
        for sel in next_selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed() and btn.is_enabled():
                    # Verificar que no esta deshabilitado
                    parent = btn.find_element(By.XPATH, "..")
                    classes = (parent.get_attribute("class") or "") + (btn.get_attribute("class") or "")
                    if "disabled" in classes:
                        continue
                    btn.click()
                    time.sleep(3)
                    return True
            except (NoSuchElementException, WebDriverException):
                continue

        # Intentar via URL si hay parametro page
        current = driver.current_url
        page_match = re.search(r"[?&]page=(\d+)", current)
        if page_match:
            current_page = int(page_match.group(1))
            next_url = re.sub(r"([?&])page=\d+", rf"\g<1>page={current_page + 1}", current)
            driver.get(next_url)
            time.sleep(3)
            # Verificar que hay contenido nuevo
            soup = BeautifulSoup(driver.page_source, "html.parser")
            if soup.select(".card-inmueble") or soup.select("[class*='inmueble']") or soup.select("article"):
                return True
            return False

        return False
    except Exception:
        return False


# ── Scraping completo de una ciudad ────────────────────────────────

def scrape_ciudad_listings(driver, ciudad: str, max_pages: int = 50) -> list[dict]:
    """
    Navega todas las paginas de listado para una ciudad y recopila
    las URLs de detalle y datos basicos de cada tarjeta.
    """
    search_url = _resolve_search_url(driver, ciudad)
    if not search_url:
        log.warning(f"No se encontro endpoint activo para {ciudad}")
        return []

    all_cards = []
    page = 1

    while page <= max_pages:
        log.info(f"  Pagina {page} de {ciudad}...")
        cards = _extract_cards_from_page(driver)

        if not cards:
            log.info(f"  Sin tarjetas en pagina {page}, fin del listado")
            break

        log.info(f"  {len(cards)} tarjetas extraidas en pagina {page}")
        all_cards.extend(cards)

        if not _go_next_page(driver):
            log.info(f"  No hay mas paginas despues de {page}")
            break

        page += 1

    log.info(f"  Total tarjetas para {ciudad}: {len(all_cards)}")
    return all_cards


# ── Workers con thread pool ────────────────────────────────────────

def worker(q: Queue, selenium_url: str, results: list):
    """
    Worker thread: consume URLs de detalle de la cola, las scrapea
    y agrega los resultados a la lista compartida.
    """
    log.info(f"Worker iniciado con {selenium_url}")
    driver = _crear_driver(selenium_url)
    urls_processed = 0
    urls_ok = 0
    urls_fail = 0

    while True:
        try:
            detail_url = q.get(timeout=5)
        except Empty:
            break

        try:
            # Reiniciar driver periodicamente para liberar memoria
            if urls_processed > 0 and urls_processed % RESTART_EVERY == 0:
                log.info(f"Reiniciando driver despues de {urls_processed} URLs...")
                try:
                    driver.quit()
                except Exception:
                    pass
                time.sleep(2)
                driver = _crear_driver(selenium_url)

            dato = _scrape_detail(driver, detail_url)
            if dato:
                results.append(dato)
                urls_ok += 1
            else:
                urls_fail += 1
            urls_processed += 1

            if urls_processed % 10 == 0:
                log.info(
                    f"  Worker progreso: {urls_processed} procesadas "
                    f"({urls_ok} OK, {urls_fail} fallidas)"
                )

        except (SessionNotCreatedException, WebDriverException) as exc:
            log.error(f"Driver muerto, recreando: {exc}")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(3)
            try:
                driver = _crear_driver(selenium_url)
            except Exception as exc2:
                log.error(f"No se pudo recrear driver: {exc2}")
                q.task_done()
                break
        except Exception as exc:
            log.error(f"Error procesando {detail_url}: {exc}")
            urls_fail += 1
            urls_processed += 1
        finally:
            q.task_done()

    try:
        driver.quit()
    except Exception:
        pass
    log.info(
        f"Worker {selenium_url} finalizado: {urls_processed} procesadas "
        f"({urls_ok} OK, {urls_fail} fallidas)"
    )


def scrape_details_threaded(detail_urls: list[str]) -> list[dict]:
    """
    Scrapea las paginas de detalle usando multiples workers en paralelo
    (uno por cada URL de Selenium configurada).
    """
    if not detail_urls:
        return []

    q = Queue()
    results = []

    for url in detail_urls:
        q.put(url)

    threads = []
    for selenium_url in SELENIUM_URLS:
        t = Thread(target=worker, args=(q, selenium_url, results))
        t.start()
        threads.append(t)

    q.join()

    for t in threads:
        t.join(timeout=30)

    log.info(f"Scraping de detalles completado: {len(results)}/{len(detail_urls)}")
    return results


def scrape_ciudad_completa(ciudad: str) -> list[dict]:
    """
    Pipeline completo para una ciudad:
    1. Obtener listado de tarjetas con URLs de detalle
    2. Scrapear cada detalle en paralelo
    3. Devolver lista de propiedades con datos completos
    """
    log.info(f"Iniciando scraping completo para {ciudad}...")

    # Paso 1: Obtener listado (usa un driver propio)
    listing_driver = _crear_driver(SELENIUM_URLS[0])
    try:
        cards = scrape_ciudad_listings(listing_driver, ciudad)
    finally:
        try:
            listing_driver.quit()
        except Exception:
            pass

    if not cards:
        log.warning(f"No se encontraron propiedades en el listado de {ciudad}")
        return []

    # Deduplicar por URL de detalle
    seen = set()
    unique_urls = []
    for card in cards:
        url = card.get("detail_url")
        if url and url not in seen:
            seen.add(url)
            unique_urls.append(url)

    log.info(f"  {len(unique_urls)} URLs unicas de detalle para {ciudad}")

    # Paso 2: Scrapear detalles
    details = scrape_details_threaded(unique_urls)

    # Paso 3: Merge datos de tarjeta con detalle
    detail_map = {d.get("url_detalle"): d for d in details if d}
    merged = []
    for card in cards:
        url = card.get("detail_url")
        if url in detail_map:
            # Datos de detalle tienen prioridad, tarjeta llena huecos
            doc = {**card, **detail_map[url]}
            merged.append(doc)
        # Si no hay detalle, no incluimos la tarjeta sola (datos incompletos)

    log.info(f"  {len(merged)} propiedades completas para {ciudad}")
    return merged
