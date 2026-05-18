"""
Individual Insert Handler

Maneja eventos de INSERT/UPDATE individual de inmueble.
Los triggers SQL ya calculan los scores, este handler solo emite eventos
para notificaciones en tiempo real vía WebSocket.

Funcionamiento:
1. PostgreSQL NOTIFY cuando se inserta/actualiza inmueble
2. Listener Python recibe notificación
3. Emite evento INMUEBLE_CREATED/UPDATED
4. WebSocket broadcast a frontend
"""

import asyncio
import psycopg2
import psycopg2.extensions
import select
import logging
from typing import Dict
import json
import os

from .event_bus import Event, EventType, event_bus
from ..api.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

# Config
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', '5434'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}


async def handle_inmueble_created(event: Event):
    """
    Handler para INMUEBLE_CREATED
    
    Event data:
    {
        'id_inmueble': int,
        'tipo_inmueble': str,
        'has_coordinates': bool
    }
    """
    id_inmueble = event.data.get('id_inmueble')
    tipo = event.data.get('tipo_inmueble', 'unknown')
    
    logger.info(f"[INDIVIDUAL] Nuevo inmueble #{id_inmueble} ({tipo})")
    
    # Broadcast a frontend
    await ws_manager.broadcast({
        'event': 'inmueble_created',
        'id_inmueble': id_inmueble,
        'tipo_inmueble': tipo,
        'message': f'Nuevo {tipo} agregado',
        'timestamp': event.timestamp
    })


async def handle_inmueble_updated(event: Event):
    """Handler para INMUEBLE_UPDATED"""
    
    id_inmueble = event.data.get('id_inmueble')
    campos = event.data.get('campos_modificados', [])
    
    logger.info(f"[INDIVIDUAL] Inmueble #{id_inmueble} actualizado: {campos}")
    
    # Broadcast a frontend
    await ws_manager.broadcast({
        'event': 'inmueble_updated',
        'id_inmueble': id_inmueble,
        'campos_modificados': campos,
        'timestamp': event.timestamp
    })


class PostgreSQLNotifyListener:
    """
    Listener de PostgreSQL NOTIFY para capturar inserts/updates en tiempo real
    
    Requiere trigger SQL que haga NOTIFY:
    
    CREATE OR REPLACE FUNCTION notify_inmueble_change()
    RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            PERFORM pg_notify('inmueble_created', 
                json_build_object(
                    'id_inmueble', NEW.id_inmueble,
                    'tipo_inmueble', NEW.tipo_inmueble,
                    'has_coordinates', (NEW.geom IS NOT NULL)
                )::text
            );
        ELSIF TG_OP = 'UPDATE' THEN
            PERFORM pg_notify('inmueble_updated',
                json_build_object(
                    'id_inmueble', NEW.id_inmueble
                )::text
            );
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    
    def __init__(self):
        self.conn = None
        self.running = False
    
    async def start(self):
        """Inicia listener en background task"""
        
        logger.info("[LISTENER] Iniciando PostgreSQL NOTIFY listener")
        
        # Conectar
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Subscribe a canales
        cur = self.conn.cursor()
        cur.execute("LISTEN inmueble_created")
        cur.execute("LISTEN inmueble_updated")
        cur.close()
        
        self.running = True
        
        # Loop de escucha
        while self.running:
            await self._check_notifications()
            await asyncio.sleep(0.1)  # Pequeño delay
    
    async def _check_notifications(self):
        """Chequea notificaciones pendientes"""
        
        # select() con timeout
        if select.select([self.conn], [], [], 0.1) == ([], [], []):
            return
        
        self.conn.poll()
        
        while self.conn.notifies:
            notify = self.conn.notifies.pop(0)
            
            try:
                # Parse payload JSON
                data = json.loads(notify.payload)
                
                # Emitir evento correspondiente
                if notify.channel == 'inmueble_created':
                    await event_bus.emit(EventType.INMUEBLE_CREATED, data, source='postgres')
                
                elif notify.channel == 'inmueble_updated':
                    await event_bus.emit(EventType.INMUEBLE_UPDATED, data, source='postgres')
                
            except Exception as e:
                logger.error(f"[LISTENER] Error procesando notificación: {e}")
    
    async def stop(self):
        """Detiene listener"""
        self.running = False
        if self.conn:
            self.conn.close()
        logger.info("[LISTENER] Listener detenido")


# Instancia global
notify_listener = PostgreSQLNotifyListener()


async def setup():
    """Configura handlers y listener"""
    
    # Registrar handlers
    await event_bus.subscribe(EventType.INMUEBLE_CREATED, handle_inmueble_created)
    await event_bus.subscribe(EventType.INMUEBLE_UPDATED, handle_inmueble_updated)
    
    # Iniciar listener en background
    asyncio.create_task(notify_listener.start())
    
    logger.info("[ORCHESTRATOR] Individual insert handler configurado")
