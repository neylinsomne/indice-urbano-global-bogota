"""
Script de migración de datos de MongoDB a PostgreSQL.
Migra inmuebles existentes deduplicando por codigo_fr.

Uso:
    MONGO_URI=... POSTGRES_URI=... python migrate_mongo_to_postgres.py
    
O dentro de Docker:
    docker compose run --rm -e RUN_MODE=migrate scraper
"""
import os
import json
import logging
import math
from datetime import datetime
from pymongo import MongoClient

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Importar normalizadores
try:
    from finca.normalizers import normalize_item
except ImportError:
    from normalizers import normalize_item


def clean_nan_values(obj):
    """
    Recursivamente reemplaza NaN e Inf con None para JSON válido.
    MongoDB puede contener valores float('nan') que no son JSON válidos.
    """
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def connect_mongo():
    """Conecta a MongoDB y retorna el cliente."""
    mongo_uri = os.getenv('MONGO_URI')
    if not mongo_uri:
        raise ValueError("MONGO_URI no configurado")
    return MongoClient(mongo_uri)


def connect_postgres():
    """Conecta a PostgreSQL y retorna la conexión."""
    import psycopg2
    postgres_uri = os.getenv('POSTGRES_URI')
    if not postgres_uri:
        raise ValueError("POSTGRES_URI no configurado")
    return psycopg2.connect(postgres_uri)


def get_all_collections(mongo_client):
    """Obtiene todas las bases de datos y collections de inmuebles."""
    collections_to_migrate = []
    
    # Bases de datos a migrar
    databases = ['bogota', 'medellin', 'antioquia']
    
    for db_name in databases:
        try:
            db = mongo_client[db_name]
            for coll_name in db.list_collection_names():
                # Solo collections de venta/arriendo
                if 'venta' in coll_name or 'arriendo' in coll_name:
                    count = db[coll_name].count_documents({})
                    if count > 0:
                        collections_to_migrate.append({
                            'database': db_name,
                            'collection': coll_name,
                            'count': count
                        })
                        logger.info(f"  📁 {db_name}.{coll_name}: {count} documentos")
        except Exception as e:
            logger.warning(f"Error accediendo a {db_name}: {e}")
    
    return collections_to_migrate


def migrate_collection(mongo_client, pg_conn, db_name: str, coll_name: str, batch_size: int = 100):
    """Migra una collection de MongoDB a PostgreSQL."""
    db = mongo_client[db_name]
    collection = db[coll_name]
    
    stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'errors': 0, 'skipped': 0}
    processed = 0
    
    # Obtener todos los documentos
    cursor = collection.find({})
    
    for doc in cursor:
        processed += 1
        
        try:
            # Convertir ObjectId a string
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            
            # Normalizar el documento
            normalized = normalize_item(doc)
            
            # Validar que tenga codigo_fuente
            if not normalized.get('codigo_fuente'):
                stats['skipped'] += 1
                continue
            
            # Insertar en PostgreSQL
            with pg_conn.cursor() as cur:
                # Castear tipos explícitamente para evitar errores de 'unknown'
                cur.execute("""
                    SELECT * FROM iug.f_upsert_inmueble(
                        p_pagina := %s::TEXT,
                        p_codigo_fuente := %s::TEXT,
                        p_precio := %s::NUMERIC,
                        p_area_construida := %s::NUMERIC,
                        p_habitaciones := %s::SMALLINT,
                        p_banos := %s::SMALLINT,
                        p_estrato := %s::SMALLINT,
                        p_tipo_inmueble := %s::TEXT,
                        p_ubicacion := %s::TEXT,
                        p_direccion := %s::TEXT,
                        p_lat := %s::FLOAT,
                        p_lon := %s::FLOAT,
                        p_image := %s::TEXT,
                        p_descripcion := %s::TEXT,
                        p_inmobiliaria := %s::TEXT,
                         p_proyecto := %s::BOOLEAN,
                        p_raw_data := %s::JSONB
                    )
                """, (
                    clean_nan_values(normalized['pagina'] or 'finca_raiz'),
                    clean_nan_values(normalized['codigo_fuente']),
                    clean_nan_values(normalized['precio']),
                    clean_nan_values(normalized['area_construida']),
                    clean_nan_values(normalized['habitaciones']),
                    clean_nan_values(normalized['banos']),
                    clean_nan_values(normalized['estrato']),
                    clean_nan_values(normalized['tipo_inmueble']),
                    clean_nan_values(normalized['ubicacion']),
                    clean_nan_values(normalized['direccion']),
                    clean_nan_values(normalized['lat']),
                    clean_nan_values(normalized['lon']),
                    clean_nan_values(normalized['image']),
                    clean_nan_values(normalized['descripcion']),
                    clean_nan_values(normalized['inmobiliaria']),
                    normalized['proyecto'] if normalized['proyecto'] is not None else False,
                    json.dumps(clean_nan_values(doc), ensure_ascii=False, default=str)
                ))
                
                result = cur.fetchone()
                if result:
                    id_inmueble, accion, _ = result
                    stats[accion] = stats.get(accion, 0) + 1
                    
                    # Insertar características
                    caracteristicas = normalized.get('caracteristicas', [])
                    for carac in caracteristicas:
                        if carac and isinstance(carac, str):
                            carac_clean = carac.strip()
                            if carac_clean and carac_clean.lower() not in ('ver más', 'ver menos'):
                                try:
                                    cur.execute("""
                                        INSERT INTO iug.inmueble_caracteristica 
                                        (id_inmueble, nombre, valor_bool, fuente)
                                        VALUES (%s, %s, TRUE, 'finca_raiz')
                                        ON CONFLICT (id_inmueble, nombre) DO NOTHING
                                    """, (id_inmueble, carac_clean))
                                except:
                                    pass
                
                pg_conn.commit()
                
        except Exception as e:
            pg_conn.rollback()
            stats['errors'] += 1
            if stats['errors'] <= 5:
                logger.warning(f"Error migrando documento: {e}")
        
        # Progress log cada 500 documentos
        if processed % 500 == 0:
            logger.info(f"    Procesados {processed}...")
    
    return stats


def main():
    logger.info("=" * 60)
    logger.info("🚀 Migración MongoDB → PostgreSQL")
    logger.info("=" * 60)
    
    # Conectar a las bases de datos
    logger.info("\n📡 Conectando a bases de datos...")
    
    try:
        mongo_client = connect_mongo()
        logger.info("  ✅ MongoDB conectado")
    except Exception as e:
        logger.error(f"  ❌ MongoDB error: {e}")
        return
    
    try:
        pg_conn = connect_postgres()
        logger.info("  ✅ PostgreSQL conectado")
    except Exception as e:
        logger.error(f"  ❌ PostgreSQL error: {e}")
        mongo_client.close()
        return
    
    # Obtener collections a migrar
    logger.info("\n📋 Collections encontradas:")
    collections = get_all_collections(mongo_client)
    
    if not collections:
        logger.warning("No se encontraron collections para migrar")
        return
    
    total_docs = sum(c['count'] for c in collections)
    logger.info(f"\n📊 Total a migrar: {total_docs} documentos de {len(collections)} collections")
    
    # Migrar cada collection
    global_stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'errors': 0, 'skipped': 0}
    
    for coll_info in collections:
        db_name = coll_info['database']
        coll_name = coll_info['collection']
        count = coll_info['count']
        
        logger.info(f"\n🔄 Migrando {db_name}.{coll_name} ({count} docs)...")
        
        stats = migrate_collection(mongo_client, pg_conn, db_name, coll_name)
        
        for key, value in stats.items():
            global_stats[key] = global_stats.get(key, 0) + value
        
        logger.info(f"   ✅ inserted={stats['inserted']}, updated={stats['updated']}, "
                   f"unchanged={stats['unchanged']}, errors={stats['errors']}")
    
    # Resumen final
    logger.info("\n" + "=" * 60)
    logger.info("📊 RESUMEN FINAL")
    logger.info("=" * 60)
    logger.info(f"  Insertados:  {global_stats['inserted']}")
    logger.info(f"  Actualizados: {global_stats['updated']}")
    logger.info(f"  Sin cambios: {global_stats['unchanged']}")
    logger.info(f"  Errores:     {global_stats['errors']}")
    logger.info(f"  Saltados:    {global_stats['skipped']}")
    logger.info("=" * 60)
    
    # Cerrar conexiones
    mongo_client.close()
    pg_conn.close()
    
    logger.info("\n✅ Migración completada!")


if __name__ == "__main__":
    main()
