"""
Main Script para Scraper Bancolombia REO (propiedades recuperadas).
Soporta multiples ciudades configurables desde config.py.

tipo_operacion = 'REO'
pagina = 'bancolombia_reo'
"""
import sys
import os
import logging
import time
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

# Agregar path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BANCOLOMBIA_CIUDADES, MONGO_DB, MONGO_COLLECTION
from scraper import scrape_ciudad_completa

# Configuracion
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


# ── MongoDB ────────────────────────────────────────────────────────

def connect_to_mongodb():
    """Conecta a MongoDB usando credenciales de .env"""
    username = os.getenv("MONGO_DB_USERNAME")
    password = os.getenv("MONGO_DB_PSW")
    mongo_uri = os.getenv("MONGO_URI")

    if mongo_uri:
        client = MongoClient(mongo_uri)
    elif username and password:
        client = MongoClient(
            f"mongodb+srv://{username}:{password}@realstatecolombia.hhtn5cb.mongodb.net/"
        )
    else:
        client = MongoClient("mongodb://localhost:27017/")

    db = client[MONGO_DB]
    return db


# ── Metadata ───────────────────────────────────────────────────────

def agregar_fecha_y_metadata(data: list, ciudad: str) -> list:
    """Agrega fecha y metadata REO a cada documento."""
    for documento in data:
        documento["fecha"] = datetime.now()
        documento["ciudad"] = ciudad
        documento["pagina"] = "bancolombia_reo"
        documento["tipo_operacion"] = "REO"
    return data


# ── Upsert en MongoDB ─────────────────────────────────────────────

def guardar_o_actualizar_en_mongodb(data: list, db, collection_name: str) -> dict:
    """
    Guarda o actualiza documentos en MongoDB.
    Usa codigo o url_detalle como identificador unico.
    """
    collection = db[collection_name]
    stats = {"inserted": 0, "updated": 0}

    for documento in data:
        # Identificador unico: codigo si existe, sino url_detalle
        codigo = documento.get("codigo")
        url_det = documento.get("url_detalle")

        if codigo:
            filtro = {"codigo": codigo}
        elif url_det:
            filtro = {"url_detalle": url_det}
        else:
            # Sin identificador, insertar como nuevo
            collection.insert_one(documento)
            stats["inserted"] += 1
            continue

        result = collection.update_one(filtro, {"$set": documento}, upsert=True)

        if result.upserted_id:
            stats["inserted"] += 1
        elif result.modified_count > 0:
            stats["updated"] += 1

    return stats


# ── Scraping por ciudad ───────────────────────────────────────────

def scrape_ciudad(ciudad: str, db) -> dict:
    """Scrapea una ciudad especifica de Bancolombia REO."""
    log.info(f"Scrapeando REO Bancolombia: {ciudad}")
    ciudad_start = time.time()

    try:
        # Paso 1: Scraping completo (listado + detalles)
        log.info(f"  Obteniendo propiedades REO de {ciudad}...")
        t0 = time.time()
        propiedades = scrape_ciudad_completa(ciudad)
        t_scrape = time.time() - t0

        log.info(
            f"  Scraping completado: {len(propiedades)} propiedades "
            f"extraidas ({t_scrape:.1f}s)"
        )

        if not propiedades:
            log.warning(f"  No se encontraron propiedades REO en {ciudad}")
            return {"ciudad": ciudad, "total": 0, "inserted": 0, "updated": 0}

        # Paso 2: Agregar metadata
        propiedades = agregar_fecha_y_metadata(propiedades, ciudad)

        # Paso 3: Guardar en MongoDB
        log.info(f"  Guardando {len(propiedades)} docs en MongoDB...")
        stats = guardar_o_actualizar_en_mongodb(propiedades, db, MONGO_COLLECTION)

        ciudad_dur = time.time() - ciudad_start
        log.info(
            f"  {ciudad}: {len(propiedades)} propiedades REO en {ciudad_dur:.1f}s "
            f"(ins:{stats['inserted']} upd:{stats['updated']})"
        )

        return {
            "ciudad": ciudad,
            "total": len(propiedades),
            "inserted": stats["inserted"],
            "updated": stats["updated"],
        }

    except Exception as exc:
        ciudad_dur = time.time() - ciudad_start
        log.error(f"  Error en {ciudad} despues de {ciudad_dur:.1f}s: {exc}")
        return {"ciudad": ciudad, "total": 0, "inserted": 0, "updated": 0, "error": str(exc)}


# ── Ejecucion principal ───────────────────────────────────────────

def run_all_cities(ciudades: list = None):
    """Ejecuta el scraper para todas las ciudades configuradas."""
    if ciudades is None:
        ciudades = BANCOLOMBIA_CIUDADES

    log.info("=" * 60)
    log.info("SCRAPER BANCOLOMBIA REO - PROPIEDADES RECUPERADAS")
    log.info(f"Ciudades: {ciudades}")
    log.info("=" * 60)

    start_time = datetime.now()

    # Conectar a MongoDB
    db = connect_to_mongodb()

    # Scrapear cada ciudad (con pausa entre cada una para liberar Selenium)
    results = []
    for i, ciudad in enumerate(ciudades):
        if i > 0:
            log.info("Pausa de 10s entre ciudades para liberar recursos de Selenium...")
            time.sleep(10)
        result = scrape_ciudad(ciudad, db)
        results.append(result)

    # Resumen
    duration = (datetime.now() - start_time).total_seconds()
    total_props = sum(r.get("total", 0) for r in results)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_updated = sum(r.get("updated", 0) for r in results)

    log.info("=" * 60)
    log.info("RESUMEN FINAL")
    log.info("=" * 60)
    for r in results:
        status = "OK" if "error" not in r else "ERROR"
        log.info(f"  [{status}] {r['ciudad']}: {r.get('total', 0)} propiedades REO")
    log.info(f"  Total: {total_props} propiedades")
    log.info(f"  Insertadas: {total_inserted}, Actualizadas: {total_updated}")
    log.info(f"  Duracion: {duration:.1f}s")
    log.info("=" * 60)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper Bancolombia REO")
    parser.add_argument(
        "--ciudades",
        nargs="+",
        default=None,
        help="Ciudades a scrapear (default: todas del config)",
    )
    parser.add_argument(
        "--ciudad",
        type=str,
        default=None,
        help="Una sola ciudad a scrapear",
    )

    args = parser.parse_args()

    ciudades = args.ciudades
    if args.ciudad:
        ciudades = [args.ciudad]

    results = run_all_cities(ciudades)

    # ── Trigger pipeline completo (MongoDB -> PG + DBSCAN + Regresion) ──
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")
    total_scraped = sum(r.get("total", 0) for r in (results or []))

    if pipeline_secret and total_scraped > 0:
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
                mig = data.get("migration", {})
                log.info(
                    f"Pipeline completo: "
                    f"migracion={mig.get('total_inserted', 0)} ins, "
                    f"DBSCAN={'si' if data.get('dbscan_triggered') else 'no'}, "
                    f"Regresion={'si' if data.get('regression_triggered') else 'no'}"
                )
            else:
                log.warning(f"Pipeline respondio {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            log.warning(f"Error llamando pipeline: {exc}")
    elif not pipeline_secret:
        log.warning("PIPELINE_SECRET no configurado, pipeline no ejecutado")
