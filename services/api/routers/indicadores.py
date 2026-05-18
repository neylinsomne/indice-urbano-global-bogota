"""
Router de Indicadores de Transporte

Endpoints:
- POST /api/indicadores/recalcular-pca: Recalcular pesos PCA (después de batch scraping)
- POST /api/indicadores/refresh-scores: Refrescar vista materializada
- GET /api/indicadores/{id_inmueble}: Obtener indicadores de un inmueble
- WebSocket /ws/indicadores: Conexión para notificaciones en tiempo real
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks
from typing import Optional
import asyncpg
import logging

from websocket_manager import manager
from services.pca_service import get_pca_service
from db.postgre import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/indicadores", tags=["indicadores"])


@router.post("/recalcular-pca")
async def recalcular_pca(
    background_tasks: BackgroundTasks,
    tipo_inmueble: Optional[str] = None,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Recalcula pesos PCA para uno o todos los tipos de inmueble.
    
    Se ejecuta típicamente después de:
    - Batch de scraping completo
    - Inserción manual de muchos inmuebles
    
    Args:
        tipo_inmueble: Tipo específico o None para todos
    """
    pca_service = get_pca_service()
    
    async def calcular_y_notificar():
        try:
            if tipo_inmueble:
                # Calcular solo un tipo
                resultado = await pca_service.calcular_pesos_por_tipo(tipo_inmueble)
                resultados = {tipo_inmueble: resultado} if resultado else {}
            else:
                # Calcular todos los tipos
                resultados = await pca_service.calcular_todos_los_tipos()
            
            # Notificar vía WebSocket
            await manager.broadcast({
                "event": "pca_recalculado",
                "tipos_actualizados": list(resultados.keys()),
                "detalles": resultados
            })
            
            logger.info(f"PCA recalculado: {list(resultados.keys())}")
            
        except Exception as e:
            logger.error(f"Error en recálculo PCA: {e}", exc_info=True)
            await manager.broadcast({
                "event": "pca_error",
                "error": str(e)
            })
    
    # Ejecutar en background
    background_tasks.add_task(calcular_y_notificar)
    
    return {
        "status": "processing",
        "message": f"Recálculo PCA iniciado para: {tipo_inmueble or 'todos los tipos'}"
    }


@router.post("/refresh-scores")
async def refresh_scores(
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Refresca la vista materializada de scores finales.
    
    Ejecutar después de:
    - Actualizar pesos PCA
    - Batch de nuevos inmuebles
    """
    async def refresh_y_notificar():
        try:
            async with db.acquire() as conn:
                # Refrescar vista materializada
                await conn.execute("SELECT iug.refresh_indicadores_transporte()")
            
            # Contar registros actualizados
            async with db.acquire() as conn:
                total = await conn.fetchval("""
                    SELECT COUNT(*) FROM iug.indicador_transporte_final
                """)
            
            # Notificar vía WebSocket
            await manager.broadcast({
                "event": "scores_actualizados",
                "total_inmuebles": total,
                "timestamp": "now"
            })
            
            logger.info(f"Vista materializada refrescada: {total} inmuebles")
            
        except Exception as e:
            logger.error(f"Error refrescando scores: {e}", exc_info=True)
            await manager.broadcast({
                "event": "refresh_error",
                "error": str(e)
            })
    
    background_tasks.add_task(refresh_y_notificar)
    
    return {
        "status": "processing",
        "message": "Refresh de scores iniciado"
    }


@router.get("/{id_inmueble}")
async def obtener_indicadores(
    id_inmueble: int,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """Obtiene indicadores de un inmueble específico"""
    async with db.acquire() as conn:
        # Obtener scores raw
        raw = await conn.fetchrow("""
            SELECT * FROM iug.indicador_transporte_raw
            WHERE id_inmueble = $1
        """, id_inmueble)
        
        # Obtener score final
        final = await conn.fetchrow("""
            SELECT * FROM iug.indicador_transporte_final
            WHERE id_inmueble = $1
        """, id_inmueble)
    
    if not raw:
        raise HTTPException(404, "Inmueble no tiene indicadores calculados")
    
    return {
        "id_inmueble": id_inmueble,
        "scores_raw": dict(raw) if raw else None,
        "score_final": dict(final) if final else None
    }


# ============================================
# WebSocket Endpoint
# ============================================
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket para notificaciones en tiempo real.
    
    Eventos que se envían:
    - pca_recalculado: Cuando se actualizan pesos PCA
    - scores_actualizados: Cuando se refresca la vista materializada
    - pca_error / refresh_error: Errores en procesos
    """
    client_id = websocket.query_params.get("client_id", "anonymous")
    
    await manager.connect(websocket, client_id)
    
    try:
        # Enviar confirmación de conexión
        await websocket.send_json({
            "event": "connected",
            "client_id": client_id,
            "message": "Conectado al sistema de indicadores"
        })
        
        # Mantener conexión abierta y escuchar mensajes del cliente
        while True:
            data = await websocket.receive_json()
            
            # Cliente puede solicitar su score actual
            if data.get("action") == "get_score":
                id_inmueble = data.get("id_inmueble")
                # ... implementar lógica de consulta
                await websocket.send_json({
                    "event": "score_response",
                    "id_inmueble": id_inmueble,
                    "data": {}  # Placeholder
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)
        logger.info(f"Cliente {client_id} desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket {client_id}: {e}")
        manager.disconnect(websocket, client_id)
