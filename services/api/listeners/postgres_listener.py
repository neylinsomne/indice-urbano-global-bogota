"""
Listener de PostgreSQL NOTIFY para eventos de base de datos

Escucha el canal 'indicadores_actualizados' y dispara acciones
cuando se completan operaciones en la base de datos.
"""
import asyncpg
import asyncio
import json
import logging
from typing import Callable

from websocket_manager import manager

logger = logging.getLogger(__name__)


async def listen_postgres_notifications(
    db_pool: asyncpg.Pool,
    on_notification: Callable = None
):
    """
    Escucha notificaciones de PostgreSQL y las reenvía vía WebSocket.
    
    Args:
        db_pool: Pool de conexiones asyncpg
        on_notification: Callback opcional para procesamiento adicional
    """
    async with db_pool.acquire() as conn:
        
        async def notification_handler(connection, pid, channel, payload):
            """Handler para notificaciones de PostgreSQL"""
            try:
                data = json.loads(payload)
                logger.info(f"Notificación recibida en canal '{channel}': {data}")
                
                # Reenviar vía WebSocket
                await manager.broadcast({
                    "event": "db_notification",
                    "channel": channel,
                    "data": data
                })
                
                # Callback adicional si existe
                if on_notification:
                    await on_notification(channel, data)
                    
            except json.JSONDecodeError:
                logger.error(f"Payload no es JSON válido: {payload}")
            except Exception as e:
                logger.error(f"Error procesando notificación: {e}", exc_info=True)
        
        # Registrar listener
        await conn.add_listener('indicadores_actualizados', notification_handler)
        logger.info("🎧 Listener PostgreSQL iniciado: 'indicadores_actualizados'")
        
        # Mantener conexión abierta indefinidamente
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Listener PostgreSQL detenido")
            await conn.remove_listener('indicadores_actualizados', notification_handler)
