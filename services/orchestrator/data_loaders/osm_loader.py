"""
OSM Data Loader

Carga automática de datos OSM (SITP, TransMilenio, parques, vías) cuando las tablas están vacías.
Usa ogr2ogr en Docker para extraer desde Bogota.osm.pbf
"""

import os
import logging
import subprocess
import psycopg2

logger = logging.getLogger(__name__)

# Config DB
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'postgres'),
    'port': os.getenv('PG_PORT', '5432'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

# Path OSM (dentro del contenedor si se ejecuta desde Docker)
OSM_FILE = '/app/services/database/archivos/archivos/Bogota.osm.pbf'
PG_CONN = f"PG:host={DB_CONFIG['host']} port={DB_CONFIG['port']} dbname={DB_CONFIG['database']} user={DB_CONFIG['user']} password={DB_CONFIG['password']}"


def check_table_empty(conn, table_name):
    """Verifica si una tabla está vacía"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        return count == 0


def extract_osm_layer(layer_sql, target_table, description):
    """
    Extrae una capa de OSM usando ogr2ogr
    
    Args:
        layer_sql: SQL query para ogr2ogr
        target_table: Tabla temporal destino
        description: Descripción para logs
    """
    logger.info(f"Extrayendo {description} desde OSM...")
    
    cmd = [
        'ogr2ogr',
        '-f', 'PostgreSQL',
        PG_CONN,
        OSM_FILE,
        '-sql', layer_sql,
        '-nln', target_table,
        '-lco', 'GEOMETRY_NAME=geom',
        '-overwrite',
        '-progress'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info(f"  ✓ {description} extraído")
            return True
        else:
            logger.error(f"  ✗ Error extrayendo {description}: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"  ✗ Excepción extrayendo {description}: {e}")
        return False


async def load_osm_transport_if_empty():
    """Carga datos de transporte (SITP, TransMilenio)"""
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        # Verificar SITP
        if check_table_empty(conn, 'iug.osm_transport'):
            logger.info("Tabla osm_transport vacía, cargando SITP...")
            
            # Extraer paradas SITP
            sitp_sql = "SELECT * FROM points WHERE amenity='bus_stop'"
            if extract_osm_layer(sitp_sql, 'iug.osm_sitp_temp', 'paradas SITP'):
                # Mover a tabla final
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO iug.osm_transport (type, name, geom)
                        SELECT 'bus_stop', name, geom FROM iug.osm_sitp_temp;
                        DROP TABLE IF EXISTS iug.osm_sitp_temp;
                    """)
                    conn.commit()
                    logger.info(f"  ✓ SITP cargado: {cur.rowcount} paradas")
        
        # Verificar TransMilenio (si existe tabla)
        try:
            if check_table_empty(conn, 'iug.estacion_transmilenio'):
                logger.info("Tabla estacion_transmilenio vacía, cargando...")
                # TransMilenio normalmente viene de archivo específico, no OSM
                # Aquí podrías cargar desde GeoJSON si existe
                pass
        except:
            pass  # Tabla no existe
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error cargando OSM transport: {e}")


async def load_osm_parks_if_empty():
    """Carga parques desde OSM"""
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        if check_table_empty(conn, 'iug.osm_parks'):
            logger.info("Tabla osm_parks vacía, cargando...")
            
            parks_sql = "SELECT * FROM multipolygons WHERE leisure='park' OR landuse='recreation_ground' OR leisure='playground'"
            if extract_osm_layer(parks_sql, 'iug.osm_parks_temp', 'parques'):
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO iug.osm_parks (name, geom)
                        SELECT name, geom FROM iug.osm_parks_temp;
                        DROP TABLE IF EXISTS iug.osm_parks_temp;
                    """)
                    conn.commit()
                    logger.info(f"  ✓ Parques cargados: {cur.rowcount} registros")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error cargando OSM parks: {e}")


async def load_osm_roads_if_empty():
    """Carga vías principales desde OSM"""
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        if check_table_empty(conn, 'iug.osm_main_roads'):
            logger.info("Tabla osm_main_roads vacía, cargando...")
            
            roads_sql = "SELECT * FROM lines WHERE highway IN ('motorway','trunk','primary','secondary','tertiary')"
            if extract_osm_layer(roads_sql, 'iug.osm_roads_temp', 'vías principales'):
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO iug.osm_main_roads (name, highway, geom)
                        SELECT name, highway, geom FROM iug.osm_roads_temp;
                        DROP TABLE IF EXISTS iug.osm_roads_temp;
                    """)
                    conn.commit()
                    logger.info(f"  ✓ Vías cargadas: {cur.rowcount} registros")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error cargando OSM roads: {e}")


async def load_all_osm_data():
    """Carga todos los datos OSM si están vacíos"""
    
    logger.info("Verificando datos OSM...")
    
    # Verificar si archivo OSM existe
    if not os.path.exists(OSM_FILE):
        logger.warning(f"Archivo OSM no encontrado: {OSM_FILE}")
        logger.warning("Saltando carga de datos OSM")
        return
    
    logger.info("="*60)
    logger.info(" CARGANDO DATOS OSM")
    logger.info("="*60)
    
    await load_osm_transport_if_empty()
    await load_osm_parks_if_empty()
    await load_osm_roads_if_empty()
    
    logger.info("="*60)
    logger.info(" ✓ CARGA OSM COMPLETADA")
    logger.info("="*60)
