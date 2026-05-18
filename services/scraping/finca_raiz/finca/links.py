"""
FincaRaiz Link Extractor - Playwright Version
Extrae links de propiedades navegando con paginacion click-through (no reload).
"""
import asyncio
import concurrent.futures
import json
import os
import re
from typing import Optional
from playwright.async_api import async_playwright, Page

# ---------- Config via env ----------
RESULTS_PATH = os.getenv("RESULTS_PATH", "resultados.json")

# ---------- Selectores CSS ----------
SELECTORS = {
    "listings_container": "section.listingsWrapper",
    "property_link_primary": "a.lc-data[href]",
    "property_link_fallback": "section.emblaGalleryCarousel a[href^='/']",
    "property_link_fallback2": ".listingCard a[href^='/']",
    "next_button": "li.ant-pagination-next:not(.ant-pagination-disabled)",
    "pagination_links": "a.ant-pagination-item-link[href*='pagina']",
}

VALID_URL_RE = re.compile(r'fincaraiz\.com\.co/.*-en-(venta|arriendo)')


def _clean_links(hrefs: list[str]) -> list[str]:
    """Filtra y deduplica links de propiedades."""
    seen = set()
    out = []
    for href in hrefs:
        if not href:
            continue
        full = f"https://www.fincaraiz.com.co{href}" if href.startswith('/') else href
        if full not in seen and VALID_URL_RE.search(full):
            seen.add(full)
            out.append(full)
    return out


async def _extract_links(page: Page) -> list[str]:
    """Extrae links de la pagina actual (ya cargada)."""
    for sel in [SELECTORS["property_link_primary"],
                SELECTORS["property_link_fallback"],
                SELECTORS["property_link_fallback2"]]:
        hrefs = await page.eval_on_selector_all(
            sel, "els => els.map(e => e.getAttribute('href'))"
        )
        if hrefs:
            return _clean_links(hrefs)
    return []


async def _get_total_pages(page: Page) -> int:
    """Lee el total de paginas desde la paginacion."""
    try:
        pagination_links = await page.eval_on_selector_all(
            SELECTORS["pagination_links"],
            "els => els.map(e => e.getAttribute('href'))"
        )
        nums = [int(m.group(1)) for link in pagination_links
                if link and (m := re.search(r'pagina(\d+)', link))]
        if nums:
            return max(nums)

        text = await page.text_content("ul.ant-pagination") or ""
        nums = [int(n) for n in re.findall(r'\d+', text)]
        return max(nums) if nums else 1
    except Exception:
        return 1


async def dicc_links_playwright(
    base_url: str,
    max_pages: Optional[int] = None,
    opp: bool = False,
    headless: bool = True,
) -> dict[str, list[str]]:
    """
    Extrae links navegando pagina por pagina con click en 'siguiente'.
    Mucho mas rapido que recargar cada URL desde cero.
    """
    if opp:
        try:
            with open(RESULTS_PATH, "r", encoding="utf-8") as f:
                dic = json.load(f)
            print(f"Usando resultados previos: {len(dic)} paginas")
            return dic
        except FileNotFoundError:
            print("No se encontro resultados.json, scrapeando desde cero...")

    dic = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navegar a la primera pagina
            await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector(
                    SELECTORS["listings_container"], timeout=15000
                )
            except Exception:
                print("Contenedor de listados no encontrado, intentando de todas formas...")

            total_pages = await _get_total_pages(page)
            if max_pages:
                total_pages = min(total_pages, max_pages)
            print(f"Total paginas: {total_pages}")

            # Extraer links de pagina 1 (ya cargada)
            links = await _extract_links(page)
            dic["Pagina 1"] = links
            print(f"  Pagina 1/{total_pages}: {len(links)} links")

            # Navegar pagina por pagina
            for pg in range(2, total_pages + 1):
                navigated = False

                # Intento 1: click en boton "siguiente"
                next_btn = page.locator(SELECTORS["next_button"])
                if await next_btn.count() > 0:
                    try:
                        await next_btn.click()
                        await page.wait_for_url(f"**/pagina{pg}**", timeout=8000)
                        navigated = True
                    except Exception:
                        pass

                # Intento 2: click en link de pagina especifica
                if not navigated:
                    page_link = page.locator(f"a[href*='pagina{pg}']")
                    if await page_link.count() > 0:
                        try:
                            await page_link.first.click()
                            await page.wait_for_url(f"**/pagina{pg}**", timeout=8000)
                            navigated = True
                        except Exception:
                            pass

                # Intento 3: fallback a navegacion directa
                if not navigated:
                    url = f"{base_url}/pagina{pg}"
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    try:
                        await page.wait_for_selector(
                            SELECTORS["listings_container"], timeout=8000
                        )
                    except Exception:
                        pass

                links = await _extract_links(page)
                dic[f"Pagina {pg}"] = links
                print(f"  Pagina {pg}/{total_pages}: {len(links)} links")

        finally:
            await browser.close()

    # Guardar resultados
    try:
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(dic, f, ensure_ascii=False, indent=4)
        print(f"Resultados guardados en {RESULTS_PATH}")
    except Exception as e:
        print(f"Error guardando resultados: {e}")

    total_links = sum(len(v) for v in dic.values())
    print(f"Resumen: {total_links} links de {len(dic)} paginas")
    return dic


def _run_in_thread(url: str, max_pages: Optional[int], opp: bool) -> dict[str, list[str]]:
    """Ejecuta la extraccion async en un event loop nuevo (dentro de un thread)."""
    return asyncio.run(dicc_links_playwright(url, max_pages=max_pages, opp=opp))


def dicc_links_paralelo(url: str, opp: bool = False, max_pages: Optional[int] = None) -> dict[str, list[str]]:
    """
    Wrapper sincrono. Usa un thread separado para evitar conflictos
    con el event loop de Scrapy/Twisted.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_run_in_thread, url, max_pages, opp)
            return future.result(timeout=900)
    else:
        return asyncio.run(dicc_links_playwright(url, max_pages=max_pages, opp=opp))


if __name__ == "__main__":
    url = "https://www.fincaraiz.com.co/venta/apartamentos/bogota"
    print(f"Iniciando extraccion de links desde: {url}")
    result = dicc_links_paralelo(url, max_pages=3)
    print("\nResultados:")
    for pagina, links in result.items():
        print(f"  {pagina}: {len(links)} links")
        for link in links[:3]:
            print(f"    - {link}")
