"""
Main Script para Scraper de Ciencuadras.
Portal inmobiliario colombiano (~130K listings).

Estrategia:
  1. Intentar API client (Next.js / REST / GraphQL)
  2. Fallback a Selenium scraper
  3. Matriz: ciudades x tipos x transacciones
  4. Almacenamiento en MongoDB con metadata
  5. Trigger pipeline al finalizar
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

from config import (
    CIUDADES, TIPOS, TRANSACCIONES,
    MONGO_DB, MAX_PAGES,
    get_matrix, collection_name,
)
from api_client import CiencuadrasAPIClient
from scraper import CiencuadrasScraper

# ── Config ────────────────────────────────────────────────────────────
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

PAGINA = "ciencuadras"


# ── MongoDB ───────────────────────────────────────────────────────────

def connect_to_mongodb():
    """Conecta a MongoDB usando credenciales de .env."""
    username = os.getenv("MONGO_DB_USERNAME")
    password = os.getenv("MONGO_DB_PSW")
    mongo_uri = os.getenv("MONGO_URI")

    if mongo_uri:
        client = MongoClient(mongo_uri)
    elif username and password:
        client = MongoClient(
            f"mongodb+srv://{username}:{password}"
            f"@realstatecolombia.hhtn5cb.mongodb.net/"
        )
    else:
        client = MongoClient("mongodb://localhost:27017/")

    db = client[MONGO_DB]
    return db


def agregar_metadata(
    data: list,
    ciudad: str,
    tipo: str,
    transaccion: str,
) -> list:
    """Agrega fecha y metadata a cada documento."""
    now = datetime.now()
    for doc in data:
        doc["fecha"] = now
        doc["ciudad"] = ciudad
        doc["tipo_inmueble"] = tipo
        doc["transaccion"] = transaccion
        doc["pagina"] = PAGINA
    return data


def guardar_en_mongodb(data: list, db, col_name: str) -> dict:
    """
    Guarda o actualiza documentos en MongoDB usando upsert.
    Returns: {'inserted': int, 'updated': int, 'skipped': int}
    """
    collection = db[col_name]
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    for doc in data:
        # Identificador unico: codigo o URL
        codigo = doc.get("codigo")
        url = doc.get("url")

        if not codigo and not url:
            stats["skipped"] += 1
            continue

        if codigo:
            filtro = {"codigo": codigo}
        else:
            filtro = {"url": url}

        result = collection.update_one(filtro, {"$set": doc}, upsert=True)

        if result.upserted_id:
            stats["inserted"] += 1
        elif result.modified_count > 0:
            stats["updated"] += 1

    return stats


# ── Scraping ──────────────────────────────────────────────────────────

def scrape_combo(
    ciudad: str,
    tipo: str,
    transaccion: str,
    api_client: CiencuadrasAPIClient,
    web_scraper: CiencuadrasScraper,
    use_api: bool,
    db,
) -> dict:
    """Scrapea una combinacion ciudad/tipo/transaccion."""
    combo_label = f"{ciudad}/{tipo}/{transaccion}"
    col_name = collection_name(ciudad, tipo, transaccion)
    t0 = time.time()

    log.info(f"Scrapeando {combo_label} -> coleccion: {col_name}")

    listings = []

    # Intentar API primero
    if use_api:
        try:
            listings = api_client.fetch_listings(ciudad, tipo, transaccion)
            if listings:
                log.info(
                    f"  API: {len(listings)} listings para {combo_label}"
                )
        except Exception as e:
            log.warning(f"  API fallo para {combo_label}: {e}")

    # Fallback a Selenium
    if not listings:
        try:
            log.info(f"  Usando scraper web para {combo_label}")
            listings = web_scraper.scrape_listings(
                ciudad, tipo, transaccion
            )
            log.info(
                f"  Scraper web: {len(listings)} listings para {combo_label}"
            )
        except Exception as e:
            log.error(f"  Scraper web fallo para {combo_label}: {e}")

    if not listings:
        log.warning(f"  Sin resultados para {combo_label}")
        return {
            "combo": combo_label,
            "total": 0,
            "inserted": 0,
            "updated": 0,
            "duration": time.time() - t0,
        }

    # Agregar metadata
    listings = agregar_metadata(listings, ciudad, tipo, transaccion)

    # Guardar en MongoDB
    log.info(f"  Guardando {len(listings)} docs en {col_name}...")
    stats = guardar_en_mongodb(listings, db, col_name)

    duration = time.time() - t0
    log.info(
        f"  {combo_label}: {len(listings)} propiedades en {duration:.1f}s "
        f"(ins:{stats['inserted']} upd:{stats['updated']} "
        f"skip:{stats['skipped']})"
    )

    return {
        "combo": combo_label,
        "collection": col_name,
        "total": len(listings),
        "inserted": stats["inserted"],
        "updated": stats["updated"],
        "skipped": stats["skipped"],
        "duration": duration,
    }


def run(
    ciudades: list = None,
    tipos: list = None,
    transacciones: list = None,
):
    """
    Ejecuta el scraper iterando la matriz
    ciudades x tipos x transacciones.
    """
    ciudades = ciudades or CIUDADES
    tipos = tipos or TIPOS
    transacciones = transacciones or TRANSACCIONES

    total_combos = len(ciudades) * len(tipos) * len(transacciones)
    log.info("=" * 60)
    log.info(f"SCRAPER CIENCUADRAS - {total_combos} combinaciones")
    log.info(f"Ciudades:      {ciudades}")
    log.info(f"Tipos:         {tipos}")
    log.info(f"Transacciones: {transacciones}")
    log.info("=" * 60)

    start_time = datetime.now()

    # Conectar a MongoDB
    db = connect_to_mongodb()

    # Intentar descubrir API
    api_client = CiencuadrasAPIClient()
    use_api = api_client.discover()
    if use_api:
        log.info("API descubierta, se usara como metodo primario")
    else:
        log.info("API no disponible, se usara Selenium como metodo primario")

    # Crear scraper web (se inicializa lazy)
    web_scraper = CiencuadrasScraper()

    # Iterar la matriz
    results = []
    combo_idx = 0

    try:
        for ciudad in ciudades:
            for tipo in tipos:
                for transaccion in transacciones:
                    combo_idx += 1
                    log.info(
                        f"\n[{combo_idx}/{total_combos}] "
                        f"{ciudad}/{tipo}/{transaccion}"
                    )

                    result = scrape_combo(
                        ciudad, tipo, transaccion,
                        api_client, web_scraper,
                        use_api, db,
                    )
                    results.append(result)

                    # Pausa entre combinaciones
                    if combo_idx < total_combos:
                        time.sleep(2)

    finally:
        web_scraper.close()

    # ── Resumen ───────────────────────────────────────────────────────
    duration = (datetime.now() - start_time).total_seconds()
    total_props = sum(r.get("total", 0) for r in results)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_updated = sum(r.get("updated", 0) for r in results)
    combos_con_datos = sum(1 for r in results if r.get("total", 0) > 0)

    log.info("\n" + "=" * 60)
    log.info("RESUMEN FINAL CIENCUADRAS")
    log.info("=" * 60)
    for r in results:
        status = "OK" if r.get("total", 0) > 0 else "VACIO"
        log.info(
            f"  [{status}] {r['combo']}: "
            f"{r.get('total', 0)} propiedades "
            f"({r.get('duration', 0):.1f}s)"
        )
    log.info(f"\n  Combinaciones con datos: {combos_con_datos}/{total_combos}")
    log.info(f"  Total propiedades: {total_props}")
    log.info(f"  Insertadas: {total_inserted}, Actualizadas: {total_updated}")
    log.info(f"  Duracion total: {duration:.1f}s")
    log.info("=" * 60)

    return results


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Scraper Ciencuadras - Portal inmobiliario colombiano"
    )
    parser.add_argument(
        "--ciudades", nargs="+", default=None,
        help="Ciudades a scrapear (default: todas del config)",
    )
    parser.add_argument(
        "--tipos", nargs="+", default=None,
        help="Tipos de propiedad (default: todos del config)",
    )
    parser.add_argument(
        "--transacciones", nargs="+", default=None,
        help="Transacciones: venta, arriendo (default: ambas)",
    )

    args = parser.parse_args()

    results = run(
        ciudades=args.ciudades,
        tipos=args.tipos,
        transacciones=args.transacciones,
    )

    # ── Trigger pipeline completo (MongoDB -> PG + DBSCAN + Regresion) ──
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")
    total_scraped = sum(r.get("total", 0) for r in (results or []))

    if pipeline_secret and total_scraped > 0:
        log.info(
            f"Llamando pipeline completo: {api_url}/pipeline/complete"
        )
        try:
            import requests

            resp = requests.post(
                f"{api_url}/pipeline/complete",
                headers={"X-Pipeline-Secret": pipeline_secret},
                json={"source": PAGINA, "total_scraped": total_scraped},
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
                log.warning(
                    f"Pipeline respondio {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
        except Exception as e:
            log.warning(f"Error llamando pipeline: {e}")
    elif not pipeline_secret:
        log.warning(
            "PIPELINE_SECRET no configurado, pipeline no ejecutado"
        )
