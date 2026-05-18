from links import dicc_links 
from concurrent.futures import ThreadPoolExecutor
import json
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import SessionNotCreatedException
from concurrent.futures import ThreadPoolExecutor
from unidecode import unidecode
from queue import Queue, Empty
from threading import Thread
import time
import logging
import os
from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
from concurrent.futures import ThreadPoolExecutor



def linea_a_dicc( texto):
    linea=unidecode(texto.lower())
    diccionario={}
    lineas = linea.split("\n")  # Dividir el texto en líneas
    for i in range(0, len(lineas), 2):  # Iterar sobre las líneas de dos en dos
        clave = lineas[i]
        if i + 1 < len(lineas):  # Asegurar que hay un valor después de la clave
            valor = lineas[i + 1]
            diccionario[clave] = valor
    return diccionario



# def scrape_info_for_pages(links_dict):
#     all_info = []
#     options = webdriver.ChromeOptions()
    
#     options.headless = False  # Puedes ajustar esto según tus necesidades
#     try:
#         with ThreadPoolExecutor() as executor:
#             # Itera sobre cada lista de URLs en paralelo
#             futures = []
#             for lista_urls in links_dict.values():
#                 # Crea una nueva instancia de Chrome para cada lista de URLs
#                 driver = webdriver.Remote(command_executor="http://localhost:4444", options=options)
#                 # Ejecuta la tarea de scraping en un hilo separado
#                 futures.append(executor.submit(scrape_info_in_parallel, driver, lista_urls))
                
#             # Espera a que todas las tareas se completen
#             for future in futures:
#                 all_info.extend(future.result())
#     except Exception as e:
#         print(f"Error al procesar las URLs: {e}")
#     return all_info

# def scrape_info_in_parallel(driver, urls):
#     info = []
#     try:
#         for url in urls:
#             result = scrape_info(driver, url)
#             if result:
#                 info.append(result)
#     finally:
#         driver.quit()
#     return info

# URLs configurables via env o valores por defecto
# En Docker: SELENIUM_URLS=http://selenium:4444/wd/hub (1 instancia, N workers)
# Local standalone: múltiples puertos si usas services/scraping/habi/docker-compose.yml
SELENIUM_URLS = os.getenv(
    "SELENIUM_URLS",
    "http://localhost:4444/wd/hub"
).split(",")

def crear_driver_con_url(selenium_url):
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless')  # opcional, para que no abra el navegador si usas VNC
    return webdriver.Remote(
        command_executor=selenium_url,
        options=options
    )

RESTART_EVERY = 30  # Reiniciar Chrome cada N URLs para liberar memoria

def worker(q, selenium_url, results):
    logging.info(f"Iniciando worker con {selenium_url}")
    driver = crear_driver_con_url(selenium_url)
    urls_processed = 0
    urls_ok = 0
    urls_fail = 0

    while True:
        try:
            lista_urls = q.get(timeout=5)
        except Empty:
            break  # No más tareas en la cola

        total_in_batch = len(lista_urls)
        logging.info(f"Worker {selenium_url}: procesando lote de {total_in_batch} URLs")

        try:
            for idx, url in enumerate(lista_urls, 1):
                # Reiniciar driver periódicamente para liberar memoria
                if urls_processed > 0 and urls_processed % RESTART_EVERY == 0:
                    logging.info(f"Reiniciando driver después de {urls_processed} URLs...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    time.sleep(2)
                    driver = crear_driver_con_url(selenium_url)

                dato = scrape_info(driver, url)
                if dato:
                    results.append(dato)
                    urls_ok += 1
                else:
                    urls_fail += 1
                urls_processed += 1

                # Log progreso cada 10 URLs
                if urls_processed % 10 == 0:
                    logging.info(f"  Progreso: {urls_processed} procesadas ({urls_ok} OK, {urls_fail} fallidas) | lote {idx}/{total_in_batch}")
        except (SessionNotCreatedException, WebDriverException) as e:
            logging.error(f"Driver muerto, recreando: {e}")
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(3)
            try:
                driver = crear_driver_con_url(selenium_url)
            except Exception as e2:
                logging.error(f"No se pudo recrear driver: {e2}")
                q.task_done()
                break
        except Exception as e:
            logging.error(f"Error procesando lista: {e}")
        finally:
            q.task_done()

    try:
        driver.quit()
    except Exception:
        pass
    logging.info(f"Worker con {selenium_url} finalizado: {urls_processed} procesadas ({urls_ok} OK, {urls_fail} fallidas)")

def scrape_info_for_pages(links_dict):
    q = Queue()
    results = []

    # Cargar listas de URLs en la cola
    for lista_urls in links_dict.values():
        q.put(lista_urls)

    threads = []
    for selenium_url in SELENIUM_URLS:
        t = Thread(target=worker, args=(q, selenium_url, results))
        t.start()
        threads.append(t)

    # Esperar a que se procesen todas las tareas
    q.join()

    logging.info("Todos los workers finalizaron")
    return results

def scrape_info(driver, url):
    try:
        driver.get(url)
        code = url.split("/")[4]
        bajamos='//*[@id="gatsby-focus-wrapper"]/div/main/section/article'
        elemento = driver.find_element(By.XPATH, bajamos)
        actions = ActionChains(driver)
        # Importante para que cargue la página dinámica en este caso:
        actions.move_to_element(elemento).perform()
        elemento = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="gatsby-focus-wrapper"]/div/main/section/article/section/div/ul/li[1]/div/div[1]'))
        )
        logging.debug(f"Cargada pagina de propiedad: {code}")
        ubic = driver.find_element(By.XPATH, '//*[@id="gatsby-focus-wrapper"]/div/main/section/header/div[2]/div[1]/h2/span').text
        coordenadas = driver.find_element(By.XPATH, '//script[@type="application/ld+json"]')
        script_content = coordenadas.get_attribute("innerHTML")

# Convertir el contenido JSON en un diccionario Python
        data = json.loads(script_content)

        # Extraer la latitud y longitud
        latitude = data.get("latitude", None)
        longitude = data.get("longitude", None)
        logging.debug(f"Coordenadas: lat={latitude}, lon={longitude}")
        # fl= data.get("address", {})
        floorLevel = data.get("floorLevel", None)
        try:
            direcc = driver.find_element(By.XPATH, '//*[@id="gatsby-focus-wrapper"]/div/main/section/header/div[2]/div[1]/h2').text
        except:
            direcc=None


    
        try:
            descrip=driver.find_element(By.XPATH,'//*[@id="gatsby-focus-wrapper"]/div/main/section/article/section/div/ul/li[1]/div/div[2]/div/div/div/div/section/p').text
        except:
            descrip=None

        try:
            imagen = driver.find_element(By.XPATH, '//*[@id="gatsby-focus-wrapper"]/div/main/section/div[1]/div/div/div/div/div[1]/div/a').get_attribute('href')
        except:
            imagen=None

        try:
            acercaedif=driver.find_element(By.XPATH,'//*[@id="gatsby-focus-wrapper"]/div/main/section/article/section/div/ul/li[2]/div/div[2]/div/div/div/div/section/article/ul/li[1]/ul').text
        except:
            acercaedif=None

        try:
            lugar_sinT = driver.find_element(By.XPATH,'//*[@id="gatsby-focus-wrapper"]/div/main/section/header/h1').text
            resultado = re.search(r'Venta de apartamento\s+(.*)', lugar_sinT)
            if resultado:
                lugar = resultado.group(1)
            else:
                logging.debug("No se encontro ubicacion despues de 'Venta de apartamento'.")
                lugar=None
        except:
            lugar=None

        try:
            precio_sinT= driver.find_element(By.XPATH, '//*[@id="gatsby-focus-wrapper"]/div/main/section/header/div[3]/p').text
            precio = re.search(r'\d{1,3}(?:\.\d{3})*(?:\.\d{2})?', precio_sinT)
            if precio:
                precio = precio.group(0).replace(".", "")  # Eliminamos los puntos de separación
            else:
                logging.debug("No se encontro precio en el texto.")
                precio=None
        except:
            precio=None
        #print(f"VAMOS A VER precio: {precio}\n")
        
        
        try:
            distinm=driver.find_element(By.XPATH,'//*[@id="gatsby-focus-wrapper"]/div/main/section/article/section/div/ul/li[2]/div/div[2]/div/div/div/div/section/article/ul/li[2]/ul').text
        except:
            distinm=None


        try:
            otrascarac=driver.find_element(By.XPATH,'//*[@id="gatsby-focus-wrapper"]/div/main/section/article/section/div/ul/li[2]/div/div[2]/div/div/div/div/section/article/ul/li[3]/ul').text
        except:
            otrascarac=None

        joa = {
                    "ubicacion": ubic,
                    "direccion": direcc,
                    "descripcion":descrip,
                    "lugar": lugar,
                    "precio": precio,
                    "codigo_habi": code,
                    "imagen": imagen,
                    "latitud":latitude,
                    "longitud":longitude,
                    "floorLevel":floorLevel
                }
        x=linea_a_dicc(acercaedif)
        joa.update(x)
        y=linea_a_dicc(distinm)
        joa.update(y)
        z=linea_a_dicc(otrascarac)
        joa.update(z)
        logging.debug(f"Propiedad scrapeada: codigo={code}, precio={precio}, ubicacion={ubic}")
        return joa
    except Exception as e:
        logging.warning(f"Error al procesar {url}: {e}")
        return None
    
#key={
#    "Pagina 1":[
#        'https://habi.co/venta-apartamentos/7865808925/tekto-san-marcos-apartamento-venta-magdalena-teusaquillo',
#        'https://habi.co/venta-apartamentos/11562330263/parques-bolivar-apartamento-venta-manuela-beltran-soledad'
#    ],
#    "Pagina 2":[
#        'https://habi.co/venta-apartamentos/16239545236/caracas-avenida---apartamento-venta-marco-fidel-suarez-i-rafael-uribe-uribe',
#        'https://habi.co/venta-apartamentos/14545395359/habitat-96---apartamento-duplex-venta-villemar-fontibon'
#    ]
#}

if __name__=="__main__":
    #key=dicc_links("https://habi.co/venta-apartamentos/bogota?page=1")s
    key={
        "Pagina 1":[
            'https://habi.co/venta-apartamentos/21820406843/cadiz---apartamento-venta-tintala-kennedy',
            'https://habi.co/venta-apartamentos/19100557987/armonia---apartamento-venta-valladolid-kennedy'
        ],
        "Pagina 2":[
            'https://habi.co/venta-apartamentos/16239545236/caracas-avenida---apartamento-venta-marco-fidel-suarez-i-rafael-uribe-uribe',
            'https://habi.co/venta-apartamentos/13073003871/bolivia-real-3-apartamento-venta-bolivia-engativa'
        ]
    }
    print(key)
    all_info = scrape_info_for_pages(key)
    print(all_info)
    ruta_archivo_json = "C:/Users/neylp/OneDrive/Escritorio/LUPA/Estudio_inmobiliario/mia/habi/dataa/prueba.json"
    

    with open(ruta_archivo_json, "w") as archivo:
        json.dump(all_info, archivo, separators=(',', ':'))

