"""
Script para probar el scraping de URLs específicas de FincaRaiz.
Uso: python test_scrape_urls.py
"""
import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime


# URLs de prueba
TEST_URLS = [
    "https://www.fincaraiz.com.co/proyectos-vivienda/gran-central-apartamentos-en-venta-en-gran-america-bogota/15017862",
    "https://www.fincaraiz.com.co/apartamento-en-venta-en-chico-norte-bogota/193228796",
]


async def scrape_property(page, url: str) -> list[dict]:
    """Scrapea una propiedad y retorna los items extraídos."""
    items = []
    
    print(f"\n{'='*60}")
    print(f"🔍 Scrapeando: {url}")
    print(f"{'='*60}")
    
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)  # Esperar carga dinámica
    
    is_project = "proyectos" in url
    print(f"📋 Tipo: {'Proyecto' if is_project else 'Propiedad Individual'}")
    
    # Extraer JSON-LD
    script_data = await page.evaluate('''
        () => {
            const script = document.querySelector('script[type="application/ld+json"]');
            return script ? script.textContent : null;
        }
    ''')
    
    precio = None
    inmobiliaria = None
    descripcion = None
    image_url = None
    direccion = None
    latitude = None
    longitude = None
    
    if script_data:
        try:
            data = json.loads(script_data)
            priceinfo = data.get('priceSpecification', {})
            precio = priceinfo.get('price')
            lord_data = data.get('landlord', {})
            inmobiliaria = lord_data.get('name')
            descripcion = data.get('description', '')[:100] + '...'
            image_url = data.get('image')
            geo_data = data.get('object', {})
            direccion = geo_data.get('address')
            geo = geo_data.get('geo', {})
            latitude = geo.get('latitude')
            longitude = geo.get('longitude')
            print(f"✅ JSON-LD procesado")
        except json.JSONDecodeError as e:
            print(f"❌ Error JSON-LD: {e}")
    
    # Extraer ubicación
    ubicacion_principal = await page.evaluate('''
        () => {
            const el = document.querySelector('div.location-header .ant-col:first-child p.body-regular');
            return el ? el.textContent.trim() : null;
        }
    ''')
    
    ubicacion_asociada = await page.evaluate('''
        () => {
            const el = document.querySelector('div.location-header .ant-col:nth-child(2) p.body-regular');
            return el ? el.textContent.trim() : null;
        }
    ''')
    
    print(f"📍 Ubicación: {ubicacion_principal}")
    
    # Extraer características
    caracteristicas = await page.evaluate('''
        () => {
            const elements = document.querySelectorAll('div.CO-facility-batch span.ant-typography:not(.ant-typography-secondary)');
            return Array.from(elements).map(el => el.textContent.trim()).filter(t => t.length > 0);
        }
    ''')
    print(f"🏠 Características: {len(caracteristicas)} encontradas")
    
    # Código del inmueble
    codigo_fr = url.split('/')[-1]
    fecha = datetime.now().strftime("%d-%m-%Y")
    
    # Base común
    valores_base = {
        "pagina": "finca_raiz",
        "ubicacion": ubicacion_principal,
        "ubicacion_asociada": ubicacion_asociada,
        "codigo_fr": codigo_fr,
        "image": image_url,
        "direccion": direccion,
        "latitud": latitude,
        "longitud": longitude,
        "inmobiliaria": inmobiliaria,
        "descripcion": descripcion,
        "fecha": fecha,
        "caracteristicas": caracteristicas,
    }
    
    if is_project:
        # Proyecto: extraer tabla de tipos
        tipos = await page.evaluate('''
            () => {
                const cells = document.querySelectorAll('tbody.ant-table-tbody td.ant-table-cell');
                return Array.from(cells).map(el => el.textContent.trim());
            }
        ''')
        
        # Extraer info del proyecto (estado, estrato)
        estado = None
        estrato = None
        info_items = await page.evaluate('''
            () => {
                const items = document.querySelectorAll('div.ant-list.project-info li.ant-list-item');
                const result = {};
                items.forEach(item => {
                    const key = item.querySelector('b');
                    const value = item.querySelector('.ant-col:last-child');
                    if (key && value) {
                        const keyText = key.textContent.trim();
                        const valueText = value.textContent.trim();
                        if (valueText !== '¡Pregúntale!') {
                            result[keyText] = valueText;
                        }
                    }
                });
                return result;
            }
        ''')
        
        estado = info_items.get('Estado')
        estrato = info_items.get('Estrato')
        
        valores_base["proyecto"] = True
        valores_base["estado"] = estado
        valores_base["estrato"] = estrato
        valores_base["antiguedad"] = "nuevo"
        
        print(f"📊 Estado: {estado}, Estrato: {estrato}")
        
        if tipos:
            columnas = ['area_construida', 'area_privada', 'tipo_de_inmueble', 'habitaciones', 'banos', 'precio']
            num_inmu = len(tipos) // len(columnas)
            print(f"🏢 Unidades en proyecto: {num_inmu}")
            
            for i in range(num_inmu):
                inicio = i * len(columnas)
                fin = inicio + len(columnas)
                info_apto = tipos[inicio:fin]
                
                if len(info_apto) == len(columnas):
                    apartamento = dict(zip(columnas, info_apto))
                    item = valores_base.copy()
                    item.update(apartamento)
                    items.append(item)
        else:
            print("⚠️ No se encontraron tipos/unidades")
            
    else:
        # Propiedad individual: extraer ficha técnica
        detalles = await page.evaluate('''
            () => {
                const rows = document.querySelectorAll('div.technical-sheet div.ant-row.ant-row-space-between');
                const result = {};
                rows.forEach(row => {
                    const keyEl = row.querySelector('.ant-col:first-child span.ant-typography:not(.ant-typography-secondary)');
                    const valueEl = row.querySelector('.ant-col:last-child strong');
                    if (keyEl) {
                        const key = keyEl.textContent.trim();
                        const value = valueEl ? valueEl.textContent.trim() : null;
                        result[key] = value;
                    }
                });
                return result;
            }
        ''')
        
        print(f"📝 Detalles extraídos: {len(detalles)} campos")
        for k, v in list(detalles.items())[:5]:
            print(f"   - {k}: {v}")
        
        valores_base["proyecto"] = False
        valores_base["precio"] = precio
        valores_base.update(detalles)
        items.append(valores_base)
    
    return items


async def main():
    print("🚀 Iniciando prueba de scraping de FincaRaiz")
    print(f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_items = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        try:
            for url in TEST_URLS:
                try:
                    items = await scrape_property(page, url)
                    all_items.extend(items)
                    print(f"✅ Items extraídos: {len(items)}")
                except Exception as e:
                    print(f"❌ Error scrapeando {url}: {e}")
        finally:
            await browser.close()
    
    # Mostrar resumen
    print(f"\n{'='*60}")
    print(f"📊 RESUMEN FINAL")
    print(f"{'='*60}")
    print(f"Total items extraídos: {len(all_items)}")
    
    # Guardar resultados
    output_file = "/app/logs/test_scrape_results.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        print(f"💾 Resultados guardados en: {output_file}")
    except Exception as e:
        print(f"⚠️ No se pudo guardar archivo: {e}")
    
    # Mostrar muestra de datos
    for i, item in enumerate(all_items[:3]):
        print(f"\n--- Item {i+1} ---")
        print(f"  Código: {item.get('codigo_fr')}")
        print(f"  Proyecto: {item.get('proyecto')}")
        print(f"  Ubicación: {item.get('ubicacion')}")
        print(f"  Precio: {item.get('precio')}")
        if item.get('proyecto'):
            print(f"  Área: {item.get('area_construida')}")
            print(f"  Habitaciones: {item.get('habitaciones')}")


if __name__ == "__main__":
    asyncio.run(main())
