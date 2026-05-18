"""
Main Script para Scraper de Properati Colombia.
Soporta dos modos de extraccion:
  1. BigQuery (primario) - requiere GOOGLE_APPLICATION_CREDENTIALS
  2. Web scraping (fallback) - requests + BeautifulSoup

Patron basado en habi/main.py: connect_to_mongodb(), iterar ciudades, guardar, trigger pipeline.
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

from config import (
    PROPERATI_CIUDADES,
    PROPERATI_TIPOS,
    PROPERATI_TRANSACCIONES,
    MONGO_DB,
    BIGQUERY_FULL_TABLE,
    get_collection_name,
)

# Configuracion
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


# ── MongoDB ─────────────────────────────────────────────────────────

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
        # Local fallback
        client = MongoClient("mongodb://localhost:27017/")

    db = client[MONGO_DB]
    log.info(f"Conectado a MongoDB, base de datos: {MONGO_DB}")
    return db


def agregar_fecha_y_metadata(data: list, ciudad: str) -> list:
    """Agrega fecha y metadata a cada documento."""
    for documento in data:
        documento["fecha"] = datetime.now()
        documento["ciudad"] = ciudad
        documento["pagina"] = "properati"
    return data


def guardar_o_actualizar_en_mongodb(data: list, db, collection_name: str) -> dict:
    """
    Guarda o actualiza documentos en MongoDB via upsert.
    Usa id_properati como clave unica.
    Returns: {'inserted': int, 'updated': int, 'skipped': int}
    """
    collection = db[collection_name]
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    # Crear indice unico si no existe
    try:
        collection.create_index("id_properati", unique=True, sparse=True)
    except Exception:
        pass  # Ya existe o no se puede crear

    for documento in data:
        codigo = documento.get("id_properati") or documento.get("id")
        if not codigo:
            stats["skipped"] += 1
            continue

        documento["id_properati"] = str(codigo)
        filtro = {"id_properati": str(codigo)}
        result = collection.update_one(filtro, {"$set": documento}, upsert=True)

        if result.upserted_id:
            stats["inserted"] += 1
        elif result.modified_count > 0:
            stats["updated"] += 1

    return stats


# ── BigQuery ────────────────────────────────────────────────────────

def bigquery_available() -> bool:
    """Verifica si BigQuery esta disponible (credenciales configuradas)."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.isfile(creds_path):
        log.info(f"BigQuery: credenciales encontradas en {creds_path}")
        return True
    log.info("BigQuery: GOOGLE_APPLICATION_CREDENTIALS no configurado o archivo no existe")
    return False


def scrape_via_bigquery(ciudad: str, tipo: str, transaccion: str) -> list:
    """
    Extrae datos de Properati via BigQuery.
    El dataset publico contiene propiedades de Colombia.
    """
    try:
        from google.cloud import bigquery

        client = bigquery.Client()

        # Mapear tipo a valores de BigQuery
        type_map = {
            "apartamento": "apartment",
            "casa": "house",
            "local": "store",
            "lote": "land",
            "oficina": "office",
        }
        operation_map = {
            "venta": "sell",
            "arriendo": "rent",
        }

        bq_type = type_map.get(tipo, tipo)
        bq_operation = operation_map.get(transaccion, transaccion)

        # Mapear ciudad a ubicaciones en BigQuery
        city_map = {
            "bogota": "Bogotá",
            "medellin": "Medellín",
            "cali": "Cali",
            "barranquilla": "Barranquilla",
        }
        bq_city = city_map.get(ciudad, ciudad.capitalize())

        query = f"""
        SELECT
            id,
            created_on,
            operation,
            property_type,
            place_name,
            place_with_parent_names,
            country_name,
            state_name,
            geonames_id,
            lat,
            lon,
            price,
            currency,
            price_aprox_usd,
            surface_total_in_m2,
            surface_covered_in_m2,
            price_usd_per_m2,
            price_per_m2,
            floor,
            rooms,
            expenses,
            properati_url,
            description,
            title,
            image_thumbnail
        FROM `{BIGQUERY_FULL_TABLE}`
        WHERE
            LOWER(state_name) LIKE @city_pattern
            AND property_type = @property_type
            AND operation = @operation
        ORDER BY created_on DESC
        LIMIT 10000
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "city_pattern", "STRING", f"%{bq_city.lower()}%"
                ),
                bigquery.ScalarQueryParameter(
                    "property_type", "STRING", bq_type
                ),
                bigquery.ScalarQueryParameter(
                    "operation", "STRING", bq_operation
                ),
            ]
        )

        log.info(f"  BigQuery: ejecutando query para {ciudad}/{tipo}/{transaccion}...")
        t0 = time.time()
        query_job = client.query(query, job_config=job_config)
        rows = list(query_job.result())
        duration = time.time() - t0
        log.info(f"  BigQuery: {len(rows)} filas en {duration:.1f}s")

        # Normalizar resultados
        properties = []
        for row in rows:
            prop = {
                "id_properati": str(row.id) if row.id else "",
                "precio": row.price,
                "moneda": row.currency or "COP",
                "precio_usd": row.price_aprox_usd,
                "precio_m2_usd": row.price_usd_per_m2,
                "precio_m2": row.price_per_m2,
                "area": row.surface_total_in_m2,
                "area_cubierta": row.surface_covered_in_m2,
                "habitaciones": row.rooms,
                "piso": row.floor,
                "gastos_admin": row.expenses,
                "tipo_propiedad": tipo,
                "transaccion": transaccion,
                "ciudad": ciudad,
                "ubicacion": row.place_name or "",
                "ubicacion_completa": row.place_with_parent_names or "",
                "departamento": row.state_name or "",
                "latitud": row.lat,
                "longitud": row.lon,
                "imagen": row.image_thumbnail or "",
                "descripcion": row.description or "",
                "titulo": row.title or "",
                "url": row.properati_url or "",
                "fecha_publicacion": row.created_on.isoformat() if row.created_on else None,
                "fuente": "bigquery",
            }
            properties.append(prop)

        return properties

    except ImportError:
        log.error("  google-cloud-bigquery no instalado")
        return []
    except Exception as e:
        log.error(f"  Error en BigQuery: {e}")
        return []


# ── Web Scraping ────────────────────────────────────────────────────

def scrape_via_web(ciudad: str, tipo: str, transaccion: str) -> list:
    """Extrae datos de Properati via web scraping."""
    from scraper import scrape_listings_html

    properties = scrape_listings_html(ciudad, tipo, transaccion)
    for prop in properties:
        prop["fuente"] = "web_scraping"
    return properties


# ── Orquestacion ────────────────────────────────────────────────────

def scrape_ciudad(
    ciudad: str,
    db,
    tipos: list = None,
    transacciones: list = None,
    use_bigquery: bool = False,
) -> dict:
    """Scrapea una ciudad especifica, iterando sobre tipos y transacciones."""
    if tipos is None:
        tipos = PROPERATI_TIPOS
    if transacciones is None:
        transacciones = PROPERATI_TRANSACCIONES

    total_all = 0
    total_inserted = 0
    total_updated = 0

    for tipo in tipos:
        for transaccion in transacciones:
            combo = f"{ciudad}/{tipo}/{transaccion}"
            log.info(f"Scrapeando {combo}...")
            t0 = time.time()

            try:
                # Elegir metodo de extraccion
                if use_bigquery:
                    properties = scrape_via_bigquery(ciudad, tipo, transaccion)
                else:
                    properties = scrape_via_web(ciudad, tipo, transaccion)

                if not properties:
                    log.warning(f"  Sin resultados para {combo}")
                    continue

                # Agregar metadata
                properties = agregar_fecha_y_metadata(properties, ciudad)
                for doc in properties:
                    doc["tipo_inmueble"] = tipo
                    doc["transaccion"] = transaccion

                # Guardar en MongoDB
                collection_name = get_collection_name(ciudad, tipo, transaccion)
                log.info(
                    f"  Guardando {len(properties)} docs en MongoDB "
                    f"({MONGO_DB}.{collection_name})..."
                )
                stats = guardar_o_actualizar_en_mongodb(
                    properties, db, collection_name
                )

                duration = time.time() - t0
                log.info(
                    f"  {combo}: {len(properties)} propiedades en {duration:.1f}s "
                    f"(ins:{stats['inserted']} upd:{stats['updated']} skip:{stats['skipped']})"
                )

                total_all += len(properties)
                total_inserted += stats["inserted"]
                total_updated += stats["updated"]

            except Exception as e:
                duration = time.time() - t0
                log.error(f"  Error en {combo} despues de {duration:.1f}s: {e}")

    return {
        "ciudad": ciudad,
        "total": total_all,
        "inserted": total_inserted,
        "updated": total_updated,
    }


def trigger_pipeline():
    """Llama al endpoint POST /pipeline/complete despues del scraping."""
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")

    if not pipeline_secret:
        log.warning("PIPELINE_SECRET no configurado, pipeline no ejecutado")
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
            mig = data.get("migration", {})
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


def run_all_cities(ciudades: list = None):
    """Ejecuta el scraper para todas las ciudades configuradas."""
    if ciudades is None:
        ciudades = PROPERATI_CIUDADES

    log.info("=" * 60)
    log.info("SCRAPER PROPERATI - MULTI-CIUDAD")
    log.info(f"Ciudades: {ciudades}")
    log.info(f"Tipos: {PROPERATI_TIPOS}")
    log.info(f"Transacciones: {PROPERATI_TRANSACCIONES}")
    log.info("=" * 60)

    start_time = datetime.now()

    # Determinar metodo de extraccion
    use_bigquery = bigquery_available()
    if use_bigquery:
        log.info("Modo: BigQuery (dataset publico)")
    else:
        log.info("Modo: Web scraping (fallback)")

    # Conectar a MongoDB
    db = connect_to_mongodb()

    # Scrapear cada ciudad
    results = []
    for i, ciudad in enumerate(ciudades):
        if i > 0 and not use_bigquery:
            log.info("Pausa de 5s entre ciudades...")
            time.sleep(5)
        result = scrape_ciudad(ciudad, db, use_bigquery=use_bigquery)
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
        log.info(f"  {r['ciudad']}: {r.get('total', 0)} propiedades")
    log.info(f"  Total: {total_props} propiedades")
    log.info(f"  Insertadas: {total_inserted}, Actualizadas: {total_updated}")
    log.info(f"  Duracion: {duration:.1f}s")
    log.info(f"  Metodo: {'BigQuery' if use_bigquery else 'Web scraping'}")
    log.info("=" * 60)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper Properati Multi-Ciudad")
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
    parser.add_argument(
        "--force-web",
        action="store_true",
        help="Forzar web scraping aunque BigQuery este disponible",
    )
    parser.add_argument(
        "--force-bigquery",
        action="store_true",
        help="Forzar BigQuery (falla si no hay credenciales)",
    )

    args = parser.parse_args()

    ciudades = args.ciudades
    if args.ciudad:
        ciudades = [args.ciudad]

    # Override modo de extraccion si se solicita
    if args.force_web:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        log.info("Modo forzado: Web scraping")
    elif args.force_bigquery:
        if not bigquery_available():
            log.error("BigQuery forzado pero GOOGLE_APPLICATION_CREDENTIALS no configurado")
            sys.exit(1)

    results = run_all_cities(ciudades)

    # Trigger pipeline completo
    total_scraped = sum(r.get("total", 0) for r in (results or []))
    if total_scraped > 0:
        trigger_pipeline()
    else:
        log.warning("Sin propiedades scrapeadas, pipeline no ejecutado")
