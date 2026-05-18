"""
Main Script para Scraper SAE (Sociedad de Activos Especiales)
Ejecuta ambos scrapers (SAE oficial + Activos por Colombia),
fusiona resultados, deduplica por codigo_sae y almacena en MongoDB.
"""
import sys
import os
import logging
import time
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

# Agregar path para imports locales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_sae import scrape_sae
from scraper_activos import scrape_activos

try:
    from config import MONGO_DB, MONGO_COLLECTION_SAE
except ImportError:
    MONGO_DB = "sae"
    MONGO_COLLECTION_SAE = "sae_raw"

# ── Configuracion ────────────────────────────────────────────────────
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


# ── MongoDB ──────────────────────────────────────────────────────────

def connect_to_mongodb():
    """Conecta a MongoDB usando credenciales de .env"""
    username = os.getenv('MONGO_DB_USERNAME')
    password = os.getenv('MONGO_DB_PSW')
    mongo_uri = os.getenv('MONGO_URI')

    if mongo_uri:
        client = MongoClient(mongo_uri)
    elif username and password:
        client = MongoClient(
            f'mongodb+srv://{username}:{password}@realstatecolombia.hhtn5cb.mongodb.net/'
        )
    else:
        client = MongoClient('mongodb://localhost:27017/')

    db = client[MONGO_DB]
    log.info(f"MongoDB conectado: db={MONGO_DB}, collection={MONGO_COLLECTION_SAE}")
    return db


# ── Metadata ─────────────────────────────────────────────────────────

def agregar_metadata(items: list) -> list:
    """Agrega fecha, pagina y tipo_operacion a cada documento."""
    ahora = datetime.now()
    for doc in items:
        doc['fecha'] = ahora
        doc['pagina'] = 'sae'
        doc['tipo_operacion'] = 'Subasta'
    return items


# ── Deduplicacion ────────────────────────────────────────────────────

def deduplicar_por_codigo(items: list) -> list:
    """
    Deduplica por codigo_sae. Prioriza items de 'activos_por_colombia'
    (datos mas estructurados) sobre 'sae' oficial.
    Items sin codigo_sae se conservan todos.
    """
    vistos = {}
    sin_codigo = []

    for item in items:
        codigo = item.get('codigo_sae')
        if not codigo:
            sin_codigo.append(item)
            continue

        if codigo not in vistos:
            vistos[codigo] = item
        else:
            # Preferir activos_por_colombia si tiene mas datos
            existente = vistos[codigo]
            if item.get('fuente') == 'activos_por_colombia' and existente.get('fuente') == 'sae':
                # Merge: mantener datos de activos pero agregar campos extras de sae
                for k, v in existente.items():
                    if k not in item or item[k] is None:
                        item[k] = v
                vistos[codigo] = item
            elif existente.get('fuente') == 'activos_por_colombia':
                # Ya tenemos el mejor, agregar campos faltantes
                for k, v in item.items():
                    if k not in existente or existente[k] is None:
                        existente[k] = v

    result = list(vistos.values()) + sin_codigo
    log.info(
        f"Deduplicacion: {len(items)} items -> {len(result)} unicos "
        f"({len(vistos)} con codigo, {len(sin_codigo)} sin codigo)"
    )
    return result


# ── Guardar en MongoDB ───────────────────────────────────────────────

def guardar_en_mongodb(items: list, db) -> dict:
    """
    Guarda o actualiza documentos en MongoDB usando upsert por codigo_sae.
    Retorna estadisticas.
    """
    collection = db[MONGO_COLLECTION_SAE]
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0}

    for doc in items:
        codigo = doc.get('codigo_sae')
        if not codigo:
            # Sin codigo, insertar directamente (puede ser duplicado)
            try:
                collection.insert_one(doc)
                stats['inserted'] += 1
            except Exception as e:
                log.warning(f"Error insertando doc sin codigo: {e}")
                stats['skipped'] += 1
            continue

        filtro = {'codigo_sae': codigo}
        try:
            result = collection.update_one(filtro, {'$set': doc}, upsert=True)
            if result.upserted_id:
                stats['inserted'] += 1
            elif result.modified_count > 0:
                stats['updated'] += 1
            else:
                stats['skipped'] += 1
        except Exception as e:
            log.warning(f"Error guardando {codigo}: {e}")
            stats['skipped'] += 1

    return stats


# ── Trigger pipeline ─────────────────────────────────────────────────

def trigger_pipeline(total_scraped: int):
    """Llama al pipeline completo (MongoDB -> PG + DBSCAN + Regresion)."""
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")

    if not pipeline_secret:
        log.warning("PIPELINE_SECRET no configurado, pipeline no ejecutado")
        return

    if total_scraped == 0:
        log.info("Sin datos nuevos, pipeline no ejecutado")
        return

    log.info(f"Llamando pipeline completo: {api_url}/pipeline/complete")
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
            log.info(
                f"Pipeline completo: "
                f"migracion={mig.get('total_inserted', 0)} ins, "
                f"DBSCAN={'si' if data.get('dbscan_triggered') else 'no'}, "
                f"Regresion={'si' if data.get('regression_triggered') else 'no'}"
            )
        else:
            log.warning(f"Pipeline respondio {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log.warning(f"Error llamando pipeline: {e}")


# ── Main ─────────────────────────────────────────────────────────────

def run():
    """Ejecuta el scraper completo de SAE."""
    log.info("=" * 60)
    log.info("SCRAPER SAE - Bienes Incautados")
    log.info("  Fuentes: SAE oficial + Activos por Colombia")
    log.info("=" * 60)

    start_time = datetime.now()

    # ── Paso 1: Scraper SAE oficial ──────────────────────────────────
    log.info("")
    log.info("--- [1/4] Scrapeando SAE oficial ---")
    t0 = time.time()
    try:
        items_sae = scrape_sae()
    except Exception as e:
        log.error(f"Error en scraper SAE oficial: {e}")
        items_sae = []
    t_sae = time.time() - t0
    log.info(f"SAE oficial: {len(items_sae)} inmuebles en {t_sae:.1f}s")

    # ── Paso 2: Scraper Activos por Colombia ─────────────────────────
    log.info("")
    log.info("--- [2/4] Scrapeando Activos por Colombia ---")
    t0 = time.time()
    try:
        items_activos = scrape_activos()
    except Exception as e:
        log.error(f"Error en scraper Activos por Colombia: {e}")
        items_activos = []
    t_activos = time.time() - t0
    log.info(f"Activos por Colombia: {len(items_activos)} inmuebles en {t_activos:.1f}s")

    # ── Paso 3: Merge + deduplicar ───────────────────────────────────
    log.info("")
    log.info("--- [3/4] Fusionando y deduplicando ---")
    all_items = items_sae + items_activos
    log.info(f"Total bruto: {len(all_items)} (SAE={len(items_sae)}, Activos={len(items_activos)})")

    all_items = deduplicar_por_codigo(all_items)
    all_items = agregar_metadata(all_items)

    # ── Paso 4: Guardar en MongoDB ───────────────────────────────────
    log.info("")
    log.info("--- [4/4] Guardando en MongoDB ---")
    db = connect_to_mongodb()
    stats = guardar_en_mongodb(all_items, db)

    duration = (datetime.now() - start_time).total_seconds()

    # ── Resumen ──────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("RESUMEN FINAL")
    log.info("=" * 60)
    log.info(f"  SAE oficial:          {len(items_sae)} inmuebles")
    log.info(f"  Activos por Colombia: {len(items_activos)} inmuebles")
    log.info(f"  Despues de dedup:     {len(all_items)} unicos")
    log.info(f"  MongoDB insertados:   {stats['inserted']}")
    log.info(f"  MongoDB actualizados: {stats['updated']}")
    log.info(f"  MongoDB saltados:     {stats['skipped']}")
    log.info(f"  Duracion total:       {duration:.1f}s")
    log.info("=" * 60)

    # ── Trigger pipeline ─────────────────────────────────────────────
    total_scraped = stats['inserted'] + stats['updated']
    trigger_pipeline(total_scraped)

    return {
        'items_sae': len(items_sae),
        'items_activos': len(items_activos),
        'total_dedup': len(all_items),
        'stats': stats,
        'duration': duration,
    }


if __name__ == "__main__":
    run()
