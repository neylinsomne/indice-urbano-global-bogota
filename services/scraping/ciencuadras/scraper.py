"""
Web scraper (Selenium) para Ciencuadras.
Fallback cuando no se puede usar la API directa.
Navega las paginas de listados y extrae informacion de cada propiedad.
"""
import logging
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (
    BASE_URL, LISTING_URL, MAX_PAGES, PAGE_TIMEOUT, REQUEST_DELAY,
)

log = logging.getLogger(__name__)


def _create_driver() -> webdriver.Chrome:
    """Crea una instancia de Chrome headless."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # Desactivar automatizacion detectable
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        # Fallback: intentar con webdriver_manager
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


class CiencuadrasScraper:
    """Scraper basado en Selenium para Ciencuadras."""

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None

    def _ensure_driver(self):
        if self.driver is None:
            self.driver = _create_driver()

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def scrape_listings(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """
        Scrapea todos los listings para una combinacion
        ciudad/tipo/transaccion.
        """
        self._ensure_driver()
        all_listings = []
        page = 1

        while page <= MAX_PAGES:
            url = LISTING_URL.format(
                transaccion=transaccion,
                tipo=tipo,
                ciudad=ciudad,
            )
            if page > 1:
                url += f"?pagina={page}"

            log.info(
                f"Scraping pagina {page}: {url}"
            )

            try:
                self.driver.get(url)
                time.sleep(REQUEST_DELAY)

                # Esperar a que carguen las tarjetas de propiedades
                try:
                    WebDriverWait(self.driver, PAGE_TIMEOUT).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, self._card_selector())
                        )
                    )
                except Exception:
                    log.info(
                        f"No se encontraron tarjetas en pagina {page}, "
                        f"posiblemente ultima pagina"
                    )
                    break

                # Scroll para cargar lazy content
                self._scroll_page()

                # Parsear HTML
                soup = BeautifulSoup(self.driver.page_source, "lxml")
                cards = self._find_cards(soup)

                if not cards:
                    log.info(
                        f"Sin resultados en pagina {page} "
                        f"({ciudad}/{tipo}/{transaccion})"
                    )
                    break

                for card in cards:
                    prop = self._parse_card(card)
                    if prop:
                        all_listings.append(prop)

                log.info(
                    f"Pagina {page}: {len(cards)} tarjetas encontradas "
                    f"({ciudad}/{tipo}/{transaccion})"
                )

                # Verificar si hay pagina siguiente
                if not self._has_next_page(soup):
                    log.info("Ultima pagina alcanzada")
                    break

                page += 1

            except Exception as e:
                log.error(f"Error en pagina {page}: {e}")
                break

        return all_listings

    def scrape_detail(self, url: str) -> dict:
        """
        Scrapea la pagina de detalle de una propiedad individual.
        Extrae informacion mas completa que la tarjeta del listado.
        """
        self._ensure_driver()
        prop = {}

        try:
            self.driver.get(url)
            time.sleep(REQUEST_DELAY)

            WebDriverWait(self.driver, PAGE_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )

            soup = BeautifulSoup(self.driver.page_source, "lxml")

            # Codigo / referencia
            prop["codigo"] = self._extract_text(
                soup,
                [
                    "[class*='code']", "[class*='codigo']",
                    "[class*='reference']", "[class*='ref']",
                ],
            )

            # Precio
            prop["precio"] = self._extract_price(soup)

            # Area
            prop["area"] = self._extract_number(
                soup,
                [
                    "[class*='area']", "[class*='size']",
                    "[class*='superficie']",
                ],
            )

            # Habitaciones
            prop["habitaciones"] = self._extract_number(
                soup,
                [
                    "[class*='room']", "[class*='bedroom']",
                    "[class*='habitacion']", "[class*='alcoba']",
                ],
            )

            # Banos
            prop["banos"] = self._extract_number(
                soup,
                [
                    "[class*='bath']", "[class*='bano']",
                    "[class*='bathroom']",
                ],
            )

            # Estrato
            prop["estrato"] = self._extract_number(
                soup,
                ["[class*='estrato']", "[class*='stratum']"],
            )

            # Descripcion
            desc_el = soup.select_one(
                "[class*='description'], [class*='descripcion'], "
                "[class*='detail-text']"
            )
            if desc_el:
                prop["descripcion"] = desc_el.get_text(strip=True)

            # Direccion
            prop["direccion"] = self._extract_text(
                soup,
                [
                    "[class*='address']", "[class*='direccion']",
                    "[class*='location']",
                ],
            )

            # Ubicacion (barrio)
            prop["ubicacion"] = self._extract_text(
                soup,
                [
                    "[class*='neighborhood']", "[class*='barrio']",
                    "[class*='zone']", "[class*='sector']",
                ],
            )

            # Inmobiliaria
            prop["inmobiliaria"] = self._extract_text(
                soup,
                [
                    "[class*='agency']", "[class*='inmobiliaria']",
                    "[class*='realtor']", "[class*='company']",
                ],
            )

            # Imagen principal
            main_img = soup.select_one(
                "[class*='gallery'] img, [class*='image'] img, "
                "[class*='photo'] img, [class*='slider'] img"
            )
            if main_img:
                prop["image"] = main_img.get("src") or main_img.get("data-src")

            # Coordenadas (buscar en scripts o data-attributes)
            prop["lat"], prop["lon"] = self._extract_coordinates(soup)

            # Caracteristicas / amenidades
            prop["caracteristicas"] = self._extract_features(soup)

            # Tipo de propiedad (desde breadcrumb o titulo)
            prop["tipo"] = self._extract_text(
                soup,
                ["[class*='breadcrumb']", "[class*='property-type']"],
            )

            # URL de referencia
            prop["url"] = url

        except Exception as e:
            log.error(f"Error scraping detalle {url}: {e}")

        # Limpiar nulos
        return {k: v for k, v in prop.items() if v is not None}

    # ── Selectores y parseo de tarjetas ────────────────────────────────

    def _card_selector(self) -> str:
        """Selectores CSS candidatos para tarjetas de propiedad."""
        return (
            "[class*='property-card'], "
            "[class*='listing-card'], "
            "[class*='card-property'], "
            "[class*='CardProperty'], "
            "[class*='result-card'], "
            "[class*='PropertyCard'], "
            "[class*='inmueble'], "
            "article[class*='card'], "
            "[data-testid*='property']"
        )

    def _find_cards(self, soup: BeautifulSoup) -> list:
        """Encuentra todas las tarjetas de propiedad en la pagina."""
        selectors = [
            "[class*='property-card']",
            "[class*='listing-card']",
            "[class*='card-property']",
            "[class*='CardProperty']",
            "[class*='result-card']",
            "[class*='PropertyCard']",
            "[class*='inmueble']",
            "article[class*='card']",
            "[data-testid*='property']",
        ]

        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                return cards

        # Fallback: buscar links que parezcan propiedades
        links = soup.select("a[href*='/inmueble/'], a[href*='/propiedad/']")
        if links:
            # Subir al padre para obtener la tarjeta completa
            return [link.parent for link in links]

        return []

    def _parse_card(self, card) -> Optional[dict]:
        """Extrae datos basicos de una tarjeta de listing."""
        prop = {}

        try:
            # Link a la propiedad
            link = card.select_one("a[href]")
            if link:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = f"{BASE_URL}{href}"
                prop["url"] = href

                # Intentar extraer codigo del URL
                code_match = re.search(r'/(\d{5,})', href)
                if code_match:
                    prop["codigo"] = code_match.group(1)

            # Precio
            price_el = card.select_one(
                "[class*='price'], [class*='precio'], "
                "[class*='value'], [class*='cost']"
            )
            if price_el:
                prop["precio"] = self._clean_price(price_el.get_text())

            # Area
            area_el = card.select_one(
                "[class*='area'], [class*='size'], [class*='m2']"
            )
            if area_el:
                area_num = re.search(r'[\d.,]+', area_el.get_text())
                if area_num:
                    prop["area"] = float(
                        area_num.group().replace(",", ".")
                    )

            # Habitaciones
            rooms_el = card.select_one(
                "[class*='room'], [class*='bed'], [class*='hab']"
            )
            if rooms_el:
                rooms_num = re.search(r'\d+', rooms_el.get_text())
                if rooms_num:
                    prop["habitaciones"] = int(rooms_num.group())

            # Banos
            bath_el = card.select_one(
                "[class*='bath'], [class*='bano']"
            )
            if bath_el:
                bath_num = re.search(r'\d+', bath_el.get_text())
                if bath_num:
                    prop["banos"] = int(bath_num.group())

            # Ubicacion
            loc_el = card.select_one(
                "[class*='location'], [class*='address'], "
                "[class*='ubicacion'], [class*='barrio']"
            )
            if loc_el:
                prop["ubicacion"] = loc_el.get_text(strip=True)

            # Imagen
            img_el = card.select_one("img")
            if img_el:
                prop["image"] = (
                    img_el.get("src")
                    or img_el.get("data-src")
                    or img_el.get("data-lazy-src")
                )

            # Titulo / tipo
            title_el = card.select_one(
                "[class*='title'], h2, h3, [class*='name']"
            )
            if title_el:
                prop["titulo"] = title_el.get_text(strip=True)

        except Exception as e:
            log.debug(f"Error parseando tarjeta: {e}")
            return None

        # Solo retornar si tiene datos minimamente utiles
        if prop.get("url") or prop.get("precio"):
            return prop
        return None

    # ── Paginacion ────────────────────────────────────────────────────

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Verifica si hay pagina siguiente."""
        # Buscar boton/link de siguiente pagina
        next_selectors = [
            "[class*='next']",
            "[aria-label*='next']",
            "[aria-label*='siguiente']",
            "a[rel='next']",
            "[class*='pagination'] li:last-child a",
            "[class*='Pagination'] button:last-child",
        ]
        for selector in next_selectors:
            el = soup.select_one(selector)
            if el:
                # Verificar que no esta deshabilitado
                if el.get("disabled") is not None:
                    return False
                if "disabled" in el.get("class", []):
                    return False
                return True

        return False

    def _scroll_page(self):
        """Scroll gradual para cargar contenido lazy."""
        try:
            total_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )
            scroll_step = total_height // 4

            for i in range(1, 5):
                self.driver.execute_script(
                    f"window.scrollTo(0, {scroll_step * i});"
                )
                time.sleep(0.5)

            # Volver arriba
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)
        except Exception:
            pass

    # ── Helpers de extraccion ─────────────────────────────────────────

    def _extract_text(
        self,
        soup: BeautifulSoup,
        selectors: list[str],
    ) -> Optional[str]:
        """Prueba multiples selectores y retorna el primer texto."""
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_number(
        self,
        soup: BeautifulSoup,
        selectors: list[str],
    ) -> Optional[float]:
        """Extrae un numero de los selectores dados."""
        text = self._extract_text(soup, selectors)
        if text:
            num = re.search(r'[\d.,]+', text)
            if num:
                try:
                    return float(num.group().replace(",", "."))
                except ValueError:
                    pass
        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extrae el precio de la pagina."""
        selectors = [
            "[class*='price']", "[class*='precio']",
            "[class*='value']", "[class*='cost']",
            "h2[class*='Price']", "span[class*='Price']",
        ]
        text = self._extract_text(soup, selectors)
        if text:
            return self._clean_price(text)
        return None

    def _clean_price(self, text: str) -> Optional[float]:
        """Limpia string de precio a float."""
        if not text:
            return None
        # Remover simbolo de moneda y texto
        cleaned = re.sub(r'[^\d.,]', '', text)
        # Manejar formato colombiano: 350.000.000 o 350,000,000
        if cleaned.count('.') > 1:
            cleaned = cleaned.replace('.', '')
        elif cleaned.count(',') > 1:
            cleaned = cleaned.replace(',', '')
        elif '.' in cleaned and ',' in cleaned:
            # 350.000,50 -> 350000.50
            cleaned = cleaned.replace('.', '').replace(',', '.')

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _extract_coordinates(
        self, soup: BeautifulSoup
    ) -> tuple[Optional[float], Optional[float]]:
        """Busca coordenadas lat/lon en la pagina."""
        # Buscar en data attributes
        map_el = soup.select_one(
            "[data-lat], [data-latitude], [class*='map']"
        )
        if map_el:
            lat = map_el.get("data-lat") or map_el.get("data-latitude")
            lon = map_el.get("data-lon") or map_el.get("data-longitude") or map_el.get("data-lng")
            if lat and lon:
                try:
                    return float(lat), float(lon)
                except ValueError:
                    pass

        # Buscar en scripts (Google Maps, Leaflet, etc.)
        page_text = str(soup)
        lat_match = re.search(
            r'(?:lat(?:itude)?|"lat")\s*[:=]\s*(-?\d+\.\d+)', page_text
        )
        lon_match = re.search(
            r'(?:lng|lon(?:gitude)?|"lon"|"lng")\s*[:=]\s*(-?\d+\.\d+)',
            page_text,
        )
        if lat_match and lon_match:
            try:
                return float(lat_match.group(1)), float(lon_match.group(1))
            except ValueError:
                pass

        return None, None

    def _extract_features(self, soup: BeautifulSoup) -> list[str]:
        """Extrae lista de caracteristicas/amenidades."""
        features = []
        feature_containers = soup.select(
            "[class*='feature'], [class*='amenity'], "
            "[class*='amenitie'], [class*='caracteristic']"
        )
        for container in feature_containers:
            items = container.select("li, span, div")
            if items:
                for item in items:
                    text = item.get_text(strip=True)
                    if text and len(text) < 100:
                        features.append(text)
            else:
                text = container.get_text(strip=True)
                if text and len(text) < 100:
                    features.append(text)

        return list(set(features)) if features else []
