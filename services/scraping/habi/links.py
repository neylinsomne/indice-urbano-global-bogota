from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
#from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import time
import json
import os

def safe_find_links(container, retries=3):
    for _ in range(retries):
        try:
            elementos = container.find_elements(By.XPATH, './/article/div/header/a')
            return [elemento.get_attribute('href') for elemento in elementos]
        except StaleElementReferenceException:
            time.sleep(0.5)
    return []

# Configura el WebDriver
def dicc_links(url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    selenium_url = os.getenv("SELENIUM_URL") or os.getenv("SELENIUM_URLS", "http://localhost:4444/wd/hub").split(",")[0]
    driver = webdriver.Remote(command_executor=selenium_url, options=options)

    dic = {}
    try:
        driver.get(url)

        tiempoEspera = 3
        time.sleep(3)

        # Intentar encontrar la paginación; si no existe, extraer solo la primera página
        try:
            ult = '//*[@id="5"]/button'
            elemento = WebDriverWait(driver, tiempoEspera).until(
                EC.presence_of_element_located((By.XPATH, ult))
            )
            cant_total = int(elemento.text) if elemento.text.isdigit() else 1
        except Exception:
            print(f"⚠️ No se encontró paginación en {url}, intentando extraer página única...")
            cant_total = 1

        print(f"Son estas páginas: {cant_total}")

        for i in range(1, cant_total + 1):
            time.sleep(tiempoEspera)
            try:
                cont = WebDriverWait(driver, tiempoEspera).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'properties-cards'))
                )
                href_values = safe_find_links(cont)
                dic[f"Pagina {i}"] = href_values
                print(f"\nSe encontraron: {len(href_values)} links en la página {i}")
            except (StaleElementReferenceException, NoSuchElementException, Exception) as e:
                print(f"Error en página {i}: {e}")
                continue

            if i < cant_total:
                try:
                    elemento = WebDriverWait(driver, tiempoEspera).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'pagination'))
                    )
                    botones = driver.find_element(By.XPATH, '//*[@id="gatsby-focus-wrapper"]/main/article/div[1]/section[3]/ul')
                    button = botones.find_element(By.XPATH, '//button[@name="Siguiente"]')
                    driver.execute_script("arguments[0].scrollIntoView();", button)
                    driver.execute_script("arguments[0].click();", button)
                except Exception as e:
                    print(f"⚠️ No se pudo navegar a página {i+1}: {e}")
                    break
    finally:
        driver.quit()

    # Guardar en ruta relativa al proyecto
    ruta_archivo_json = os.path.join(os.path.dirname(__file__), "dataa", "bogota_links.json")
    os.makedirs(os.path.dirname(ruta_archivo_json), exist_ok=True)
    with open(ruta_archivo_json, "w", encoding="utf-8") as archivo:
        json.dump(dic, archivo, ensure_ascii=False, indent=2)

    return dic


if __name__ == "__main__":
    
    url = "https://habi.co/venta-apartamentos/bogota"
    resultado = dicc_links(url)

    print("\nResumen final (con enlaces):")
    for pagina, links in resultado.items():
        print(f"\n{pagina} ({len(links)} enlaces):")
        for link in links:
            print(f"  - {link}")
#xd=dicc_links("https://habi.co/venta-apartamentos/bogota?page=1")
