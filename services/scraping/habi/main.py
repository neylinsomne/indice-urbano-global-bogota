"""
Main Script para Scraper de Habi
Soporta múltiples ciudades y tipos de propiedad configurables desde config.py
"""
import sys
import os
import json
import logging
import time
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

# Agregar path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from propiedades import scrape_info_for_pages
from links import dicc_links

# PostgreSQL deshabilitado: migración se hace desde panel de admin
# from postgres_pipeline import guardar_en_postgresql
POSTGRES_ENABLED = False
def guardar_en_postgresql(data): return {'errors': 0}
try:
    from config import (
        HABI_CIUDADES, HABI_TIPOS, HABI_BASE_URL, 
        MONGO_DB, MONGO_COLLECTION_HABI, get_habi_urls
    )
except ImportError:
    # Fallback si no existe config
    HABI_CIUDADES = ["bogota", "medellin", "cali", "barranquilla", "cajica", "chia", "madrid"]
    HABI_TIPOS = ["apartamentos"]
    HABI_BASE_URL = "https://habi.co/venta-{tipo}/{ciudad}"
    MONGO_DB = "Real_state_tesis"
    MONGO_COLLECTION_HABI = "habi_newera"
    def get_habi_urls():
        return [{'url': HABI_BASE_URL.format(tipo=t, ciudad=c), 'tipo': t, 'ciudad': c} 
                for t in HABI_TIPOS for c in HABI_CIUDADES]

# Configuración
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def connect_to_mongodb():
    """Conecta a MongoDB usando credenciales de .env"""
    username = os.getenv('MONGO_DB_USERNAME')
    password = os.getenv('MONGO_DB_PSW')
    mongo_uri = os.getenv('MONGO_URI')
    
    if mongo_uri:
        client = MongoClient(mongo_uri)
    elif username and password:
        client = MongoClient(f'mongodb+srv://{username}:{password}@realstatecolombia.hhtn5cb.mongodb.net/')
    else:
        # Local fallback
        client = MongoClient('mongodb://localhost:27017/')
    
    db = client[MONGO_DB]
    return db


def agregar_fecha_y_metadata(data: list, ciudad: str) -> list:
    """Agrega fecha y metadata de ciudad a cada documento"""
    for documento in data:
        documento['fecha'] = datetime.now()
        documento['ciudad'] = ciudad
        documento['pagina'] = 'habi'
    return data


def guardar_o_actualizar_en_mongodb(data: list, db, collection_name: str) -> dict:
    """
    Guarda o actualiza documentos en MongoDB.
    Returns: {'inserted': int, 'updated': int}
    """
    collection = db[collection_name]
    stats = {'inserted': 0, 'updated': 0}
    
    for documento in data:
        # Usar codigo_habi como identificador único
        codigo = documento.get('codigo_habi') or documento.get('code')
        if not codigo:
            continue
            
        filtro = {'codigo_habi': codigo}
        result = collection.update_one(filtro, {'$set': documento}, upsert=True)
        
        if result.upserted_id:
            stats['inserted'] += 1
        elif result.modified_count > 0:
            stats['updated'] += 1
    
    return stats


def scrape_ciudad(ciudad: str, db, tipos: list = None) -> dict:
    """Scrapea una ciudad específica, iterando sobre los tipos de propiedad"""
    if tipos is None:
        tipos = HABI_TIPOS

    total_all = 0
    total_inserted = 0
    total_updated = 0
    pg_inserted_all = 0
    pg_errors_all = 0

    for tipo in tipos:
        url = f"https://habi.co/venta-{tipo}/{ciudad}"
        log.info(f"🏠 Scrapeando {ciudad}/{tipo}: {url}")
        ciudad_start = time.time()

        try:
            # Paso 1: Obtener links de propiedades
            log.info(f"  📋 Obteniendo links de {ciudad}/{tipo}...")
            t0 = time.time()
            links_dict = dicc_links(url)
            t_links = time.time() - t0

            total_links = sum(len(links) for links in links_dict.values())
            log.info(f"  ✅ Encontrados {total_links} links en {len(links_dict)} páginas ({t_links:.1f}s)")

            if total_links == 0:
                log.warning(f"  ⚠️ No se encontraron propiedades en {ciudad}/{tipo}")
                continue

            # Paso 2: Scrapear detalles de cada propiedad
            log.info(f"  🔍 Scrapeando detalles de {total_links} propiedades...")
            t0 = time.time()
            all_info = scrape_info_for_pages(links_dict)
            t_scrape = time.time() - t0
            log.info(f"  🔍 Scraping completado: {len(all_info)}/{total_links} propiedades extraidas ({t_scrape:.1f}s)")

            # Paso 3: Agregar metadata
            all_info_con_fecha = agregar_fecha_y_metadata(all_info, ciudad)
            for doc in all_info_con_fecha:
                doc['tipo_inmueble'] = tipo

            # Paso 4: Guardar en MongoDB (backup)
            log.info(f"  💾 Guardando {len(all_info_con_fecha)} docs en MongoDB...")
            stats = guardar_o_actualizar_en_mongodb(all_info_con_fecha, db, MONGO_COLLECTION_HABI)

            # Paso 5: Guardar en PostgreSQL (producción)
            pg_stats = {'inserted': 0, 'updated': 0, 'errors': 0}
            if POSTGRES_ENABLED:
                log.info(f"  🐘 Guardando {len(all_info_con_fecha)} docs en PostgreSQL...")
                try:
                    pg_stats = guardar_en_postgresql(all_info_con_fecha)
                    log.info(f"  ✅ PostgreSQL: ins={pg_stats.get('inserted',0)}, upd={pg_stats.get('updated',0)}, err={pg_stats.get('errors',0)}")
                except Exception as e:
                    log.warning(f"  ⚠️ PostgreSQL error: {e}")

            ciudad_dur = time.time() - ciudad_start
            log.info(f"  ✅ {ciudad}/{tipo}: {len(all_info)} propiedades en {ciudad_dur:.1f}s (MongoDB ins:{stats['inserted']} upd:{stats['updated']} | PG ins:{pg_stats.get('inserted',0)} err:{pg_stats.get('errors',0)})")

            total_all += len(all_info)
            total_inserted += stats['inserted']
            total_updated += stats['updated']
            pg_inserted_all += pg_stats.get('inserted', 0)
            pg_errors_all += pg_stats.get('errors', 0)

        except Exception as e:
            ciudad_dur = time.time() - ciudad_start
            log.error(f"  ❌ Error en {ciudad}/{tipo} después de {ciudad_dur:.1f}s: {e}")

    return {
        'ciudad': ciudad,
        'total': total_all,
        'inserted': total_inserted,
        'updated': total_updated,
        'pg_inserted': pg_inserted_all,
        'pg_errors': pg_errors_all
    }


def run_all_cities(ciudades: list = None):
    """Ejecuta el scraper para todas las ciudades configuradas"""
    if ciudades is None:
        ciudades = HABI_CIUDADES
    
    log.info("=" * 60)
    log.info("🏠 SCRAPER HABI - MULTI-CIUDAD")
    log.info(f"📍 Ciudades: {ciudades}")
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    # Conectar a MongoDB
    db = connect_to_mongodb()
    
    # Scrapear cada ciudad (con pausa entre cada una para que Selenium se recupere)
    results = []
    for i, ciudad in enumerate(ciudades):
        if i > 0:
            log.info("⏳ Pausa de 10s entre ciudades para liberar recursos de Selenium...")
            time.sleep(10)
        result = scrape_ciudad(ciudad, db)
        results.append(result)
    
    # Resumen
    duration = (datetime.now() - start_time).total_seconds()
    total_props = sum(r.get('total', 0) for r in results)
    total_inserted = sum(r.get('inserted', 0) for r in results)
    total_updated = sum(r.get('updated', 0) for r in results)
    
    log.info("=" * 60)
    log.info("📊 RESUMEN FINAL")
    log.info("=" * 60)
    for r in results:
        status = "✅" if 'error' not in r else "❌"
        log.info(f"  {status} {r['ciudad']}: {r.get('total', 0)} propiedades")
    log.info(f"\n  Total: {total_props} propiedades")
    log.info(f"  Insertadas: {total_inserted}, Actualizadas: {total_updated}")
    log.info(f"  Duración: {duration:.1f}s")
    log.info("=" * 60)
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Scraper Habi Multi-Ciudad")
    parser.add_argument("--ciudades", nargs="+", default=None, 
                        help="Ciudades a scrapear (default: todas del config)")
    parser.add_argument("--ciudad", type=str, default=None,
                        help="Una sola ciudad a scrapear")
    
    args = parser.parse_args()
    
    ciudades = args.ciudades
    if args.ciudad:
        ciudades = [args.ciudad]
    
    results = run_all_cities(ciudades)

    # ── Trigger pipeline completo (MongoDB→PG + DBSCAN + Regresión) ──
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")
    total_scraped = sum(r.get('total', 0) for r in (results or []))

    if pipeline_secret and total_scraped > 0:
        log.info(f"🔄 Llamando pipeline completo: {api_url}/pipeline/complete")
        try:
            import requests
            resp = requests.post(
                f"{api_url}/pipeline/complete",
                headers={"X-Pipeline-Secret": pipeline_secret},
                timeout=600,
            )
            if resp.ok:
                data = resp.json()
                mig = data.get('migration', {})
                log.info(f"✅ Pipeline completo: "
                         f"migración={mig.get('total_inserted', 0)} ins, "
                         f"DBSCAN={'sí' if data.get('dbscan_triggered') else 'no'}, "
                         f"Regresión={'sí' if data.get('regression_triggered') else 'no'}")
            else:
                log.warning(f"Pipeline respondió {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Error llamando pipeline: {e}")
    elif not pipeline_secret:
        log.warning("PIPELINE_SECRET no configurado, pipeline no ejecutado")
