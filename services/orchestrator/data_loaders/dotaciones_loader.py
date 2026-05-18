"""
Dotaciones Data Loader

Carga automática de datos de dotaciones (POIs) cuando la tabla está vacía.
Se ejecuta en startup del orquestador.
"""

import os
import json
import logging
import psycopg2
from pathlib import Path

logger = logging.getLogger(__name__)

# Config DB
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'postgres'),
    'port': os.getenv('PG_PORT', '5432'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

# Ruta base de archivos (ajustar según mounting en Docker)
BASE_PATH = Path('/app/services/database/archivos/archivos/dotaciones')


def check_dotaciones_empty(conn):
    """Verifica si la tabla dotaciones_poiz está vacía"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM iug.dotaciones_poi")
        count = cur.fetchone()[0]
        return count == 0


def load_geojson_to_poi(conn, filepath, categoria, fuente):
    """Carga un GeoJSON a dotaciones_poi"""
    
    if not filepath.exists():
        logger.warning(f"Archivo no encontrado: {filepath}")
        return 0
    
    logger.info(f"Cargando {filepath.name} como '{categoria}'...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    inserted = 0
    
    with conn.cursor() as cur:
        for feature in features:
            try:
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})
                coords = geom.get('coordinates', [])
                
                if not coords or len(coords) < 2:
                    continue
                
                # Extraer nombre (intentar varios campos)
                nombre = (props.get('nombre') or 
                         props.get('NOMBRE') or 
                         props.get('name') or 
                         props.get('Nombre_IPS') or 
                         props.get('NOMBRE_SEDE') or 
                         'Sin nombre')
                
                lon, lat = coords[0], coords[1]
                
                # Validar coordenadas Bogotá
                if not (3 < lat < 5 and -75 < lon < -73):
                    continue
                
                cur.execute("""
                    INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                """, (nombre, categoria, fuente, lon, lat))
                
                inserted += 1
                
            except Exception as e:
                logger.error(f"Error insertando feature: {e}")
                continue
    
    conn.commit()
    logger.info(f"  ✓ Insertados {inserted} registros de {filepath.name}")
    return inserted


def load_csv_to_poi(conn, filepath, categoria, fuente, lat_col='LATITUD', lon_col='LONGITUD', name_col='NAME'):
    """Carga un CSV con lat/lon a dotaciones_poi"""
    
    if not filepath.exists():
        logger.warning(f"Archivo no encontrado: {filepath}")
        return 0
    
    logger.info(f"Cargando {filepath.name} como '{categoria}'...")
    
    import csv
    
    inserted = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        with conn.cursor() as cur:
            for row in reader:
                try:
                    lat = float(row.get(lat_col, '0').replace(',', '.'))
                    lon = float(row.get(lon_col, '0').replace(',', '.'))
                    nombre = row.get(name_col, 'Sin nombre')
                    
                    # Validar
                    if not (3 < lat < 5 and -75 < lon < -73):
                        continue
                    
                    cur.execute("""
                        INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                        VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    """, (nombre, categoria, fuente, lon, lat))
                    
                    inserted += 1
                    
                except Exception as e:
                    continue
    
    conn.commit()
    logger.info(f"  ✓ Insertados {inserted} registros de {filepath.name}")
    return inserted


def load_osm_parks(conn):
    """Copia centroides de osm_parks a dotaciones_poi"""
    
    logger.info("Copiando parques de osm_parks...")
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
            SELECT 
                COALESCE(name, 'Parque'),
                'parque',
                'osm_parks',
                ST_Centroid(geom)
            FROM iug.osm_parks
            WHERE name IS NOT NULL
        """)
        inserted = cur.rowcount
    
    conn.commit()
    logger.info(f"  ✓ Insertados {inserted} parques")
    return inserted


async def load_dotaciones_if_empty():
    """
    Función principal: carga dotaciones si la tabla está vacía
    
    Llamar desde orchestrator/__init__.py en startup
    """
    
    logger.info("Verificando datos de dotaciones...")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        # Verificar si está vacía
        if not check_dotaciones_empty(conn):
            logger.info("Tabla dotaciones_poi ya tiene datos, omitiendo carga")
            conn.close()
            return
        
        logger.info("="*60)
        logger.info(" CARGANDO DATOS DE DOTACIONES (primera vez)")
        logger.info("="*60)
        
        total = 0
        
        # Salud
        total += load_geojson_to_poi(conn, BASE_PATH / 'salud.geojson', 'ips', 'salud.geojson')
        total += load_geojson_to_poi(conn, BASE_PATH / 'farmacias.geojson', 'farmacia', 'farmacias.geojson')
        
        # Educación
        total += load_geojson_to_poi(conn, BASE_PATH / 'colegios12_2024.geojson', 'colegio', 'colegios.geojson')
        
        # Cultura
        total += load_geojson_to_poi(conn, BASE_PATH / 'biblored.geojson', 'biblioteca', 'biblored.geojson')
        
        # Abastecimiento
        total += load_csv_to_poi(conn, BASE_PATH / 'centros_comerciales_bogota.csv', 
                                 'centro_comercial', 'cc_bogota.csv',
                                 lat_col='LATITUD', lon_col='LONGITUD', name_col='NAME')
        
        # Recreación (osm_parks)
        total += load_osm_parks(conn)
        
        logger.info("="*60)
        logger.info(f" ✓ CARGA COMPLETADA: {total} POIs insertados")
        logger.info("="*60)
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error cargando dotaciones: {e}")
        raise
