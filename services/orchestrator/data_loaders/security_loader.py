"""
Security Data Loader

Carga automática de datos de seguridad (sectores policiales, CAI) cuando las tablas están vacías.
"""

import os
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

# Paths de archivos (ajustar según estructura)
BASE_PATH = Path('/app/services/database/archivos/archivos')


def check_table_empty(conn, table_name):
    """Verifica si una tabla está vacía"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        return count == 0


async def load_sectores_policia_if_empty():
    """
    Carga sectores policiales si la tabla está vacía
    
    Nota: Normalmente estos datos vienen de archivos GeoJSON/Shapefile
    específicos de la Policía Nacional. Si no existen, esta función
    solo registra un warning.
    """
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        if check_table_empty(conn, 'iug.sectores_policia'):
            logger.warning("Tabla sectores_policia vacía")
            logger.warning("Estos datos deben cargarse manualmente desde fuentes oficiales")
            logger.warning("Archivo esperado: sectores_policia.geojson o similar")
            
            # Si existe archivo, cargar aquí
            # Por ahora solo warning
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error verificando sectores_policia: {e}")


async def load_cai_if_empty():
    """
    Carga CAI (Comandos de Atención Inmediata) si la tabla está vacía
    """
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        if check_table_empty(conn, 'iug.cai'):
            logger.warning("Tabla cai vacía")
            logger.warning("Estos datos deben cargarse manualmente desde fuentes oficiales")
            logger.warning("Archivo esperado: cai.geojson o similar")
            
            # Si existe archivo, cargar aquí
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error verificando cai: {e}")


async def load_all_security_data():
    """Carga todos los datos de seguridad si están vacíos"""
    
    logger.info("Verificando datos de seguridad...")
    
    await load_sectores_policia_if_empty()
    await load_cai_if_empty()
    
    logger.info("Verificación de seguridad completada")
