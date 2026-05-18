"""
Post-Scraping Orchestrator

Handler para evento SCRAPING_COMPLETED.
Ejecuta secuencialmente:
1. ETL de características (si hay nuevas)
2. Refresh de vistas materializadas
3. Notificación vía WebSocket

Para batch de scraping (muchos inmuebles).
"""

import asyncio
import psycopg2
import logging
from datetime import datetime
from typing import Dict

from .event_bus import Event, EventType, event_bus
from ..api.websocket_manager import manager as ws_manager
from ..etl.load_caracteristicas import extraer_caracteristicas_unicas, cargar_catalogo, procesar_inmuebles
from pymongo import MongoClient
import os

logger = logging.getLogger(__name__)

# Config
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', '5434'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

MONGO_CONFIG = {
    'host': os.getenv('MONGO_HOST', 'localhost'),
    'port': int(os.getenv('MONGO_PORT', '27017')),
    'database': os.getenv('MONGO_DATABASE', 'prueba')
}


async def handle_scraping_completed(event: Event):
    """
    Handler principal para SCRAPING_COMPLETED
    
    Event data esperado:
    {
        'scraping_id': str,
        'n_inmuebles': int,
        'pagina': str,
        'duration_seconds': float
    }
    """
    scraping_id = event.data.get('scraping_id')
    n_inmuebles = event.data.get('n_inmuebles', 0)
    pagina = event.data.get('pagina', 'unknown')
    
    logger.info(f"[ORCHESTRATOR] Procesando scraping completado: {scraping_id} ({n_inmuebles} inmuebles)")
    
    # Broadcast inicio de procesamiento
    await ws_manager.broadcast({
        'event': 'scraping_processing_started',
        'scraping_id': scraping_id,
        'n_inmuebles': n_inmuebles,
        'timestamp': datetime.utcnow().isoformat()
    })
    
    try:
        # Paso 1: ETL de características
        await emit_and_run_etl(scraping_id, n_inmuebles)
        
        # Paso 2: Refresh vistas materializadas
        await emit_and_refresh_views(scraping_id)
        
        # Paso 3: Calcular stats agregadas (opcional)
        stats = await calculate_aggregate_stats()
        
        # Paso 4: Broadcast completado
        await ws_manager.broadcast({
            'event': 'scraping_processed',
            'scraping_id': scraping_id,
            'n_inmuebles': n_inmuebles,
            'stats': stats,
            'status': 'completed',
            'timestamp': datetime.utcnow().isoformat()
        })
        
        logger.info(f"[ORCHESTRATOR] ✓ Scraping {scraping_id} procesado exitosamente")
        
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Error procesando scraping {scraping_id}: {e}")
        
        # Broadcast error
        await ws_manager.broadcast({
            'event': 'scraping_processing_failed',
            'scraping_id': scraping_id,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })


async def emit_and_run_etl(scraping_id: str, n_inmuebles: int):
    """Ejecuta ETL de características"""
    
    logger.info(f"[ETL] Inicio carga características para {n_inmuebles} inmuebles")
    
    # Emitir evento ETL_STARTED
    await event_bus.emit(EventType.ETL_STARTED, {
        'scraping_id': scraping_id,
        'type': 'caracteristicas'
    })
    
    # Ejecutar ETL en thread separado (blocking I/O)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_etl_sync)
    
    # Emitir evento ETL_COMPLETED
    await event_bus.emit(EventType.ETL_COMPLETED, {
        'scraping_id': scraping_id,
        'type': 'caracteristicas'
    })
    
    logger.info(f"[ETL] ✓ Características cargadas")


def run_etl_sync():
    """Ejecuta ETL síncrono (blocking)"""
    
    # Conectar a MongoDB y PostgreSQL
    mongo_client = MongoClient(host=MONGO_CONFIG['host'], port=MONGO_CONFIG['port'])
    mongo_db = mongo_client[MONGO_CONFIG['database']]
    
    pg_conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        # 1. Extraer características únicas
        caracteristicas, mapeo_raw = extraer_caracteristicas_unicas(mongo_db)
        
        # 2. Cargar catálogo
        mapeo_ids = cargar_catalogo(pg_conn, caracteristicas)
        
        # 3. Procesar inmuebles
        n_inmuebles, n_relaciones = procesar_inmuebles(mongo_db, pg_conn, mapeo_raw, mapeo_ids)
        
        logger.info(f"[ETL] Procesados {n_inmuebles} inmuebles, {n_relaciones} relaciones")
        
    finally:
        pg_conn.close()
        mongo_client.close()


async def emit_and_refresh_views(scraping_id: str):
    """Refresca vistas materializadas"""
    
    logger.info(f"[VIEWS] Refrescando vistas materializadas")
    
    # Emitir evento VIEWS_REFRESHING
    await event_bus.emit(EventType.VIEWS_REFRESHING, {
        'scraping_id': scraping_id
    })
    
    # Lista de vistas a refrescar
    views = [
        'iug.indicador_transporte_final',
        'iug.indicador_seguridad_final',
        'iug.indicador_dimension_final',
        # 'iug.indicador_hedonic_final',  # Cuando esté implementado
    ]
    
    # Ejecutar refresh en thread separado
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, refresh_views_sync, views)
    
    # Emitir evento VIEWS_REFRESHED
    await event_bus.emit(EventType.VIEWS_REFRESHED, {
        'scraping_id': scraping_id,
        'views': views
    })
    
    logger.info(f"[VIEWS] ✓ Vistas refrescadas: {len(views)}")


def refresh_views_sync(views: list):
    """Refresca vistas materializadas (blocking)"""
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        with conn.cursor() as cur:
            for view in views:
                try:
                    logger.info(f"[VIEWS] Refreshing {view}...")
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                    conn.commit()
                except Exception as e:
                    logger.error(f"[VIEWS] Error refreshing {view}: {e}")
                    conn.rollback()
    finally:
        conn.close()


async def calculate_aggregate_stats() -> Dict:
    """Calcula estadísticas agregadas"""
    
    loop = asyncio.get_event_loop()
    stats = await loop.run_in_executor(None, get_stats_sync)
    
    return stats


def get_stats_sync() -> Dict:
    """Obtiene stats de BD (blocking)"""
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_inmuebles,
                    COUNT(CASE WHEN iacc IS NOT NULL THEN 1 END) as con_transporte,
                    COUNT(CASE WHEN iseg IS NOT NULL THEN 1 END) as con_seguridad,
                    AVG(iacc) as avg_transporte,
                    AVG(iseg) as avg_seguridad
                FROM iug.inmueble
            """)
            
            row = cur.fetchone()
            
            return {
                'total_inmuebles': row[0],
                'con_indicador_transporte': row[1],
                'con_indicador_seguridad': row[2],
                'avg_transporte': float(row[3]) if row[3] else None,
                'avg_seguridad': float(row[4]) if row[4] else None
            }
    finally:
        conn.close()


# Registrar handler en event bus
async def setup():
    """Configura handlers del orquestador"""
    await event_bus.subscribe(EventType.SCRAPING_COMPLETED, handle_scraping_completed)
    logger.info("[ORCHESTRATOR] Post-scraping handler registrado")
