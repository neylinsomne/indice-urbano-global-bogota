"""
Script de prueba para verificar selectores CSS de FincaRaiz con Playwright
Actualizado Enero 2026
"""
from playwright.sync_api import sync_playwright
import time

# Nuevos selectores CSS (Enero 2026)
SELECTORS = {
    "listings_container": "section.listingsWrapper",
    "property_link_primary": "a.lc-data[href]",
    "property_link_fallback": "section.emblaGalleryCarousel a[href^='/']",
    "property_link_fallback2": ".listingCard a[href^='/']",
    "pagination": "a.ant-pagination-item-link[href*='pagina']",
}

TEST_URL = "https://www.fincaraiz.com.co/venta/apartamentos/bogota"


def test_selectors():
    """Prueba todos los selectores CSS en la página de FincaRaiz."""
    print(f"🚀 Probando selectores en: {TEST_URL}\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(TEST_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)  # Esperar carga dinámica
            
            # 1. Probar contenedor de listados
            print("=" * 50)
            print("1️⃣ Probando contenedor de listados...")
            try:
                container = page.query_selector(SELECTORS["listings_container"])
                if container:
                    print(f"   ✅ {SELECTORS['listings_container']} - ENCONTRADO")
                else:
                    print(f"   ❌ {SELECTORS['listings_container']} - NO encontrado")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            # 2. Probar selector principal de links
            print("\n2️⃣ Probando selector principal de links...")
            links_primary = page.query_selector_all(SELECTORS["property_link_primary"])
            print(f"   {'✅' if links_primary else '❌'} {SELECTORS['property_link_primary']}: {len(links_primary)} links")
            
            # 3. Probar selector fallback (galería)
            print("\n3️⃣ Probando selector fallback (galería)...")
            links_fallback = page.query_selector_all(SELECTORS["property_link_fallback"])
            print(f"   {'✅' if links_fallback else '❌'} {SELECTORS['property_link_fallback']}: {len(links_fallback)} links")
            
            # 4. Probar selector fallback2 (listingCard)
            print("\n4️⃣ Probando selector fallback2 (listingCard)...")
            links_fallback2 = page.query_selector_all(SELECTORS["property_link_fallback2"])
            print(f"   {'✅' if links_fallback2 else '❌'} {SELECTORS['property_link_fallback2']}: {len(links_fallback2)} links")
            
            # 5. Probar paginación
            print("\n5️⃣ Probando selector de paginación...")
            pagination = page.query_selector_all(SELECTORS["pagination"])
            print(f"   {'✅' if pagination else '⚠️'} {SELECTORS['pagination']}: {len(pagination)} elementos")
            
            # 6. Mostrar algunos links de ejemplo
            print("\n" + "=" * 50)
            print("📋 Ejemplos de links encontrados:")
            
            # Usar el selector que encontró más links
            best_links = links_primary or links_fallback or links_fallback2
            
            if best_links:
                seen = set()
                count = 0
                for link in best_links:
                    href = link.get_attribute("href")
                    if href and href not in seen and href.startswith("/"):
                        seen.add(href)
                        full_url = f"https://www.fincaraiz.com.co{href}"
                        print(f"   {count + 1}. {full_url}")
                        count += 1
                        if count >= 5:
                            break
            else:
                print("   ⚠️ No se encontraron links de propiedades")
            
            # 7. Mostrar estructura HTML de debug
            print("\n" + "=" * 50)
            print("🔍 Debug - Clases encontradas en el body:")
            try:
                classes = page.evaluate("""
                    () => {
                        const elements = document.querySelectorAll('[class*="listing"]');
                        return [...new Set([...elements].map(el => el.className))].slice(0, 10);
                    }
                """)
                for cls in classes:
                    print(f"   - {cls}")
            except:
                pass
            
        finally:
            browser.close()
    
    print("\n✅ Prueba completada")


if __name__ == "__main__":
    test_selectors()
