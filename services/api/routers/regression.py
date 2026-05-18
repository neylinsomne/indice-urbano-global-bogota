"""
Router Regression - Analisis de mercado por regresion.

Endpoints:
  POST /regression/train           -> Entrenar modelos (admin)
  GET  /regression/market-overview  -> Resumen de mercado por tipo
  GET  /regression/{id_inmueble}    -> Analisis de regresion por inmueble
  WS   /regression/ws              -> WebSocket para notificaciones en tiempo real
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
import asyncpg

from db.postgre import get_db_pool
from services.auth_service import require_admin
from services.regression_service import train_all_models, _market_label
from websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regression", tags=["regression"])


@router.post("/train")
async def train_regression_models(
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Entrena modelos de regresion en background y notifica via WebSocket."""

    async def entrenar_y_notificar():
        try:
            await manager.broadcast({
                "event": "regression_training_started",
                "message": "Entrenamiento de modelos iniciado",
            })

            async with db.acquire() as conn:
                result = await train_all_models(conn, admin['id'])

            # Leer el market-overview actualizado para enviar al frontend
            async with db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT tipo_inmueble, r2_ols, r2_ridge, r2_lasso, r2_elastic_net,
                           cv_mean_ols, best_model, active_model,
                           n_properties, n_overpriced, n_fair, n_underpriced,
                           avg_market_ratio, median_market_ratio,
                           avg_q25_pm2, avg_q75_pm2, avg_predicted_pm2,
                           top_features, updated_at,
                           iaao_cod, iaao_prd, iaao_prb, iaao_median_ratio,
                           iaao_cod_ok, iaao_prd_ok, iaao_level_ok
                    FROM iug.regression_market_summary
                    ORDER BY n_properties DESC
                """)

            overview = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get('top_features'), str):
                    d['top_features'] = json.loads(d['top_features'])
                if d.get('updated_at') and hasattr(d['updated_at'], 'isoformat'):
                    d['updated_at'] = d['updated_at'].isoformat()
                for key in ['r2_ols', 'r2_ridge', 'r2_lasso', 'r2_elastic_net', 'cv_mean_ols',
                             'avg_market_ratio', 'median_market_ratio',
                             'avg_q25_pm2', 'avg_q75_pm2', 'avg_predicted_pm2',
                             'iaao_cod', 'iaao_prd', 'iaao_prb', 'iaao_median_ratio']:
                    if d.get(key) is not None:
                        d[key] = float(d[key])
                for key in ['n_properties', 'n_overpriced', 'n_fair', 'n_underpriced']:
                    if d.get(key) is not None:
                        d[key] = int(d[key])
                overview.append(d)

            await manager.broadcast({
                "event": "regression_training_complete",
                "data": overview,
                "tipos_entrenados": result.get("tipos_entrenados", 0),
            })

            logger.info(f"Regression training complete, broadcast sent to {manager.total_connections} clients")

        except Exception as e:
            logger.error(f"Error en entrenamiento regression: {e}", exc_info=True)
            await manager.broadcast({
                "event": "regression_training_error",
                "error": str(e),
            })

    background_tasks.add_task(entrenar_y_notificar)

    return {"status": "processing", "message": "Entrenamiento de modelos iniciado"}


@router.get("/market-overview")
async def get_market_overview(
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Resumen de mercado por tipo de inmueble para la pagina principal."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT tipo_inmueble, r2_ols, r2_ridge, r2_lasso, r2_elastic_net,
                   cv_mean_ols, best_model, active_model,
                   n_properties, n_overpriced, n_fair, n_underpriced,
                   avg_market_ratio, median_market_ratio,
                   avg_q25_pm2, avg_q75_pm2, avg_predicted_pm2,
                   top_features, updated_at,
                   iaao_cod, iaao_prd, iaao_prb, iaao_median_ratio,
                   iaao_cod_ok, iaao_prd_ok, iaao_level_ok,
                   spatial_cv_rmse, spatial_cv_r2,
                   spatial_leakage_ratio, spatial_leakage_flag,
                   spatial_n_groups
            FROM iug.regression_market_summary
            ORDER BY n_properties DESC
        """)

    if not rows:
        return []

    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get('top_features'), str):
            d['top_features'] = json.loads(d['top_features'])
        if d.get('updated_at') and hasattr(d['updated_at'], 'isoformat'):
            d['updated_at'] = d['updated_at'].isoformat()
        # Numeric fields from asyncpg come as Decimal
        for key in ['r2_ols', 'r2_ridge', 'r2_lasso', 'r2_elastic_net', 'cv_mean_ols',
                     'avg_market_ratio', 'median_market_ratio',
                     'avg_q25_pm2', 'avg_q75_pm2', 'avg_predicted_pm2',
                     'iaao_cod', 'iaao_prd', 'iaao_prb', 'iaao_median_ratio',
                     'spatial_cv_rmse', 'spatial_cv_r2', 'spatial_leakage_ratio']:
            if d.get(key) is not None:
                d[key] = float(d[key])
        result.append(d)

    return result


@router.get("/{id_inmueble}")
async def get_property_regression(
    id_inmueble: int,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Analisis de regresion para un inmueble especifico."""
    async with db.acquire() as conn:
        pred = await conn.fetchrow("""
            SELECT p.*,
                   m.metrics, m.n_samples AS model_n_samples
            FROM iug.regression_prediction p
            LEFT JOIN iug.regression_model m
                ON m.tipo_inmueble = p.tipo_inmueble
                AND m.model_type = COALESCE(p.best_model, 'ols')
            WHERE p.id_inmueble = $1
        """, id_inmueble)

    if pred is None:
        raise HTTPException(status_code=404, detail="No hay datos de regresion para este inmueble")

    d = dict(pred)

    # Parse JSONB
    if isinstance(d.get('lasso_top_features'), str):
        d['lasso_top_features'] = json.loads(d['lasso_top_features'])
    if isinstance(d.get('metrics'), str):
        d['metrics'] = json.loads(d['metrics'])

    metrics = d.pop('metrics', {}) or {}

    result = {
        'id_inmueble': d['id_inmueble'],
        'tipo_inmueble': d['tipo_inmueble'],
        'actual_precio_m2': float(d['actual_precio_m2']) if d.get('actual_precio_m2') else None,
        'predicted_precio_m2': float(d['predicted_precio_m2']) if d.get('predicted_precio_m2') else None,
        'market_ratio': float(d['market_ratio']) if d.get('market_ratio') else None,
        'market_label': _market_label(float(d['market_ratio'])) if d.get('market_ratio') else None,
        'quantile_25_pm2': float(d['quantile_25_pm2']) if d.get('quantile_25_pm2') else None,
        'quantile_75_pm2': float(d['quantile_75_pm2']) if d.get('quantile_75_pm2') else None,
        'quantile_position': d.get('quantile_position'),
        'lasso_top_features': d.get('lasso_top_features', []),
        'best_model': d.get('best_model', 'ols'),
        'model_r2': metrics.get('r2'),
        'model_cv_rmse': metrics.get('cv_rmse_mean'),
        'model_cv_mean': metrics.get('cv_r2_mean'),
        'model_n_samples': d.get('model_n_samples'),
    }

    return result


# ============================================
# WebSocket Endpoint
# ============================================
@router.websocket("/ws")
async def regression_websocket(websocket: WebSocket):
    """
    WebSocket para notificaciones en tiempo real de regression.

    Eventos:
    - regression_training_started: Entrenamiento iniciado
    - regression_training_complete: Entrenamiento terminado (incluye data actualizada)
    - regression_training_error: Error durante entrenamiento
    """
    client_id = websocket.query_params.get("client_id", "anonymous")

    await manager.connect(websocket, client_id)

    try:
        await websocket.send_json({
            "event": "connected",
            "client_id": client_id,
            "message": "Conectado al canal de regression",
        })

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)
    except Exception as e:
        logger.error(f"Error en WebSocket regression {client_id}: {e}")
        manager.disconnect(websocket, client_id)
