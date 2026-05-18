"""
Router Admin Dashboard - Panel de control y monitoreo (solo admin).

Endpoints:
  GET  /admin/dashboard/scraping-status    -> Estado del scraping (MongoDB)
  GET  /admin/dashboard/pipeline-status    -> Estado del pipeline ETL
  GET  /admin/dashboard/data-health        -> Salud de datos en PostgreSQL
  POST /admin/dashboard/trigger-pipeline   -> Disparar pipeline completo
  GET  /admin/dashboard/cache-stats        -> Estadisticas de Redis
  POST /admin/dashboard/cache-clear        -> Limpiar cache Redis
  GET  /admin/dashboard/usage-metrics      -> Metricas de uso de la plataforma
  GET  /admin/dashboard/activity-log       -> Log de actividad reciente

Todos los endpoints requieren autenticacion de admin (JWT + role=admin).
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from db.postgre import get_db_pool
from db.redis_cache import get_redis
from services.auth_service import require_admin
from routers.pipeline import _last_pipeline_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

MONGO_URI = os.environ.get("MONGO_URI")

# MongoDB collections to check for scraping status
_SCRAPING_COLLECTIONS = [
    ("bogota", "apartamentos_venta"),
    ("bogota", "casas_venta"),
    ("bogota", "locales_venta"),
    ("bogota", "lotes_venta"),
    ("bogota", "bodegas_venta"),
    ("bogota", "apartamentos_arriendo"),
    ("bogota", "casas_arriendo"),
    ("medellin", "apartamentos_venta"),
    ("medellin", "casas_venta"),
    ("cali", "apartamentos_venta"),
    ("cali", "casas_venta"),
    ("barranquilla", "apartamentos_venta"),
    ("barranquilla", "casas_venta"),
    ("Real_state_tesis", "habi_newera"),
    ("properati", "properati_raw"),
    ("bancolombia_reo", "reo_raw"),
    ("sae", "sae_raw"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(val: Any) -> str | None:
    """Safely convert a datetime-like value to ISO string."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


async def _safe_fetchval(conn: asyncpg.Connection, query: str, *args) -> Any:
    """Execute a fetchval, returning None if the table/column does not exist."""
    try:
        return await conn.fetchval(query, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return None
    except Exception as e:
        logger.warning(f"Dashboard query failed: {e}")
        return None


async def _safe_fetch(conn: asyncpg.Connection, query: str, *args) -> list:
    """Execute a fetch, returning [] if the table/column does not exist."""
    try:
        return await conn.fetch(query, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return []
    except Exception as e:
        logger.warning(f"Dashboard query failed: {e}")
        return []


async def _safe_fetchrow(conn: asyncpg.Connection, query: str, *args) -> Any:
    """Execute a fetchrow, returning None if the table/column does not exist."""
    try:
        return await conn.fetchrow(query, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return None
    except Exception as e:
        logger.warning(f"Dashboard query failed: {e}")
        return None


# ---------------------------------------------------------------------------
# 1. GET /admin/dashboard/scraping-status
# ---------------------------------------------------------------------------

@router.get("/scraping-status")
async def scraping_status(
    admin: dict = Depends(require_admin),
):
    """
    Returns MongoDB scraping status:
      - Last scraping date (latest document per collection)
      - Document counts per collection
      - Runner status placeholder
    """
    if not MONGO_URI:
        return {
            "status": "disabled",
            "detail": "MONGO_URI not configured",
            "collections": [],
            "runner_status": "unknown",
        }

    def _read_mongo_status():
        from pymongo import MongoClient
        results = []
        try:
            with MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000) as client:
                client.admin.command("ping")
                global_latest = None

                for db_name, coll_name in _SCRAPING_COLLECTIONS:
                    db = client[db_name]
                    coll = db[coll_name]
                    count = coll.estimated_document_count()

                    # Try to find the latest document date
                    last_date = None
                    try:
                        latest_doc = coll.find_one(
                            sort=[("_id", -1)],
                            projection={"_id": 1},
                        )
                        if latest_doc and hasattr(latest_doc["_id"], "generation_time"):
                            last_date = latest_doc["_id"].generation_time.isoformat()
                            gen_time = latest_doc["_id"].generation_time
                            if global_latest is None or gen_time > global_latest:
                                global_latest = gen_time
                    except Exception:
                        pass

                    results.append({
                        "db": db_name,
                        "collection": coll_name,
                        "count": count,
                        "last_document_date": last_date,
                    })

                return {
                    "status": "ok",
                    "last_scraping_date": global_latest.isoformat() if global_latest else None,
                    "collections": results,
                    "runner_status": "placeholder",
                }
        except Exception as e:
            return {
                "status": "error",
                "detail": str(e),
                "collections": [],
                "runner_status": "unknown",
            }

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = await loop.run_in_executor(pool, _read_mongo_status)

    return result


# ---------------------------------------------------------------------------
# 2. GET /admin/dashboard/pipeline-status
# ---------------------------------------------------------------------------

@router.get("/pipeline-status")
async def pipeline_status(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Returns pipeline status:
      - In-memory pipeline status from pipeline.py
      - Last regression run from iug.regression_run_history
      - Last DBSCAN run from iug.outlier_run_history
    """
    async with db.acquire() as conn:
        # Last regression run
        reg_row = await _safe_fetchrow(conn, """
            SELECT id, run_date, tipos, results, trigger_reason, triggered_by
            FROM iug.regression_run_history
            ORDER BY run_date DESC
            LIMIT 1
        """)
        last_regression = None
        if reg_row:
            last_regression = {
                "id": reg_row["id"],
                "run_date": _iso(reg_row["run_date"]),
                "tipos": reg_row["tipos"],
                "results": reg_row["results"],
                "trigger_reason": reg_row.get("trigger_reason"),
                "triggered_by": reg_row.get("triggered_by"),
            }

        # Last DBSCAN run
        dbscan_row = await _safe_fetchrow(conn, """
            SELECT id, run_date, total_classified, total_outliers,
                   total_inliers, triggered_by
            FROM iug.outlier_run_history
            ORDER BY run_date DESC
            LIMIT 1
        """)
        last_dbscan = None
        if dbscan_row:
            last_dbscan = {
                "id": dbscan_row["id"],
                "run_date": _iso(dbscan_row["run_date"]),
                "total_classified": dbscan_row.get("total_classified"),
                "total_outliers": dbscan_row.get("total_outliers"),
                "total_inliers": dbscan_row.get("total_inliers"),
                "triggered_by": dbscan_row.get("triggered_by"),
            }

    return {
        "pipeline_in_memory": _last_pipeline_status,
        "last_regression": last_regression,
        "last_dbscan": last_dbscan,
    }


# ---------------------------------------------------------------------------
# 3. GET /admin/dashboard/data-health
# ---------------------------------------------------------------------------

@router.get("/data-health")
async def data_health(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Returns data health metrics for iug.inmueble:
      - Total inmuebles
      - Counts of records missing key fields
      - Breakdown by tipo_inmueble and estado_oferta
    """
    async with db.acquire() as conn:
        total = await _safe_fetchval(conn, "SELECT COUNT(*) FROM iug.inmueble")
        sin_barrio = await _safe_fetchval(
            conn, "SELECT COUNT(*) FROM iug.inmueble WHERE id_barrio IS NULL"
        )
        sin_localidad = await _safe_fetchval(
            conn, "SELECT COUNT(*) FROM iug.inmueble WHERE id_localidad IS NULL"
        )
        sin_indicadores = await _safe_fetchval(
            conn, "SELECT COUNT(*) FROM iug.inmueble WHERE iug IS NULL OR iug = 0"
        )
        sin_precio = await _safe_fetchval(
            conn, "SELECT COUNT(*) FROM iug.inmueble WHERE precio IS NULL"
        )
        sin_geom = await _safe_fetchval(
            conn, "SELECT COUNT(*) FROM iug.inmueble WHERE geom IS NULL"
        )

        # Breakdown by tipo_inmueble
        tipo_rows = await _safe_fetch(conn, """
            SELECT tipo_inmueble, COUNT(*) AS count
            FROM iug.inmueble
            GROUP BY tipo_inmueble
            ORDER BY count DESC
        """)
        por_tipo = {r["tipo_inmueble"]: r["count"] for r in tipo_rows}

        # Breakdown by estado_oferta
        estado_rows = await _safe_fetch(conn, """
            SELECT estado_oferta, COUNT(*) AS count
            FROM iug.inmueble
            GROUP BY estado_oferta
            ORDER BY count DESC
        """)
        por_estado = {r["estado_oferta"]: r["count"] for r in estado_rows}

    return {
        "total_inmuebles": total,
        "sin_barrio": sin_barrio,
        "sin_localidad": sin_localidad,
        "sin_indicadores": sin_indicadores,
        "sin_precio": sin_precio,
        "sin_geom": sin_geom,
        "por_tipo_inmueble": por_tipo,
        "por_estado_oferta": por_estado,
    }


# ---------------------------------------------------------------------------
# 4. POST /admin/dashboard/trigger-pipeline
# ---------------------------------------------------------------------------

@router.post("/trigger-pipeline")
async def trigger_pipeline(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Triggers the complete ETL pipeline (MongoDB -> PostgreSQL + DBSCAN + Regression).
    Delegates to the pipeline/complete logic.
    """
    from routers.pipeline import run_complete_pipeline, _verify_secret, _get_pipeline_secret

    # The admin is already authenticated; we bypass the pipeline secret
    # by invoking the internal logic directly.
    if _last_pipeline_status.get("running"):
        raise HTTPException(
            status_code=409,
            detail="Pipeline ya en ejecucion, espera a que termine",
        )

    # Run the complete pipeline reusing its logic
    try:
        result = await run_complete_pipeline(db=db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin trigger-pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "triggered_by": admin["email"],
        "result": result,
    }


# ---------------------------------------------------------------------------
# 5. GET /admin/dashboard/cache-stats
# ---------------------------------------------------------------------------

@router.get("/cache-stats")
async def cache_stats(
    admin: dict = Depends(require_admin),
):
    """
    Returns Redis cache statistics:
      - Memory usage
      - Total keys
      - Key pattern breakdown (geo:*, ranking:*, bl:*, etc.)
    """
    redis = await get_redis()
    if redis is None:
        return {
            "status": "unavailable",
            "detail": "Redis not connected",
        }

    try:
        # Memory info
        info = await redis.info("memory")
        memory_used = info.get("used_memory_human", "unknown")
        memory_used_bytes = info.get("used_memory", 0)
        memory_peak = info.get("used_memory_peak_human", "unknown")

        # Total keys
        db_size = await redis.dbsize()

        # Key pattern breakdown
        patterns = ["geo:*", "ranking:*", "bl:*", "acm:*", "search:*", "iurb:*"]
        pattern_counts = {}
        for pattern in patterns:
            try:
                keys = await redis.keys(pattern)
                if keys:
                    pattern_counts[pattern] = len(keys)
            except Exception:
                pattern_counts[pattern] = 0

        # Count "other" keys
        known_count = sum(pattern_counts.values())
        pattern_counts["other"] = max(0, db_size - known_count)

        return {
            "status": "ok",
            "memory_used": memory_used,
            "memory_used_bytes": memory_used_bytes,
            "memory_peak": memory_peak,
            "total_keys": db_size,
            "key_patterns": pattern_counts,
        }
    except Exception as e:
        logger.error(f"cache-stats failed: {e}")
        return {
            "status": "error",
            "detail": str(e),
        }


# ---------------------------------------------------------------------------
# 6. POST /admin/dashboard/cache-clear
# ---------------------------------------------------------------------------

@router.post("/cache-clear")
async def cache_clear(
    admin: dict = Depends(require_admin),
):
    """
    Clears all Redis cache (FLUSHALL).
    """
    redis = await get_redis()
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail="Redis not connected",
        )

    try:
        await redis.flushall()
        logger.info(f"Redis cache cleared by admin {admin['email']}")
        return {
            "status": "ok",
            "message": "Cache cleared successfully",
            "cleared_by": admin["email"],
        }
    except Exception as e:
        logger.error(f"cache-clear failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 7. GET /admin/dashboard/usage-metrics
# ---------------------------------------------------------------------------

@router.get("/usage-metrics")
async def usage_metrics(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Returns platform usage metrics:
      - Users by role
      - PDF generations (today / week / month)
      - Active users (last 7 days)
    """
    now_utc = datetime.now(timezone.utc)

    async with db.acquire() as conn:
        # Users by role
        role_rows = await _safe_fetch(conn, """
            SELECT role, COUNT(*) AS count
            FROM iug.users
            GROUP BY role
            ORDER BY count DESC
        """)
        users_by_role = {r["role"]: r["count"] for r in role_rows}

        total_users = await _safe_fetchval(conn, "SELECT COUNT(*) FROM iug.users")

        # PDF generations - today / week / month
        pdf_today = await _safe_fetchval(conn, """
            SELECT COUNT(*) FROM iug.acm_report
            WHERE created_at >= CURRENT_DATE
        """)
        pdf_week = await _safe_fetchval(conn, """
            SELECT COUNT(*) FROM iug.acm_report
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """)
        pdf_month = await _safe_fetchval(conn, """
            SELECT COUNT(*) FROM iug.acm_report
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        """)

        # Active users (last 7 days by last_login)
        active_users = await _safe_fetchval(conn, """
            SELECT COUNT(*) FROM iug.users
            WHERE last_login >= $1
        """, now_utc - timedelta(days=7))

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "pdf_generations": {
            "today": pdf_today,
            "week": pdf_week,
            "month": pdf_month,
        },
        "active_users_7d": active_users,
    }


# ---------------------------------------------------------------------------
# 8. GET /admin/dashboard/activity-log
# ---------------------------------------------------------------------------

@router.get("/activity-log")
async def activity_log(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Returns last 50 activities across:
      - PDF reports generated (acm_report)
      - Pipeline / regression runs (regression_run_history)
      - DBSCAN runs (outlier_run_history)
      - User registrations (users)
    Merged and sorted by date descending.
    """
    activities: list[dict] = []

    async with db.acquire() as conn:
        # PDFs generated
        pdf_rows = await _safe_fetch(conn, """
            SELECT r.id, r.created_at, u.email AS user_email,
                   r.id_inmueble
            FROM iug.acm_report r
            LEFT JOIN iug.users u ON u.id = r.user_id
            ORDER BY r.created_at DESC
            LIMIT 50
        """)
        for r in pdf_rows:
            activities.append({
                "type": "pdf_generated",
                "date": _iso(r["created_at"]),
                "detail": {
                    "report_id": r["id"],
                    "user_email": r.get("user_email"),
                    "id_inmueble": r.get("id_inmueble"),
                },
            })

        # Regression runs
        reg_rows = await _safe_fetch(conn, """
            SELECT id, run_date, tipos, trigger_reason, triggered_by
            FROM iug.regression_run_history
            ORDER BY run_date DESC
            LIMIT 50
        """)
        for r in reg_rows:
            activities.append({
                "type": "regression_run",
                "date": _iso(r["run_date"]),
                "detail": {
                    "run_id": r["id"],
                    "tipos": r.get("tipos"),
                    "trigger_reason": r.get("trigger_reason"),
                    "triggered_by": r.get("triggered_by"),
                },
            })

        # DBSCAN runs
        dbscan_rows = await _safe_fetch(conn, """
            SELECT id, run_date, total_classified, total_outliers, triggered_by
            FROM iug.outlier_run_history
            ORDER BY run_date DESC
            LIMIT 50
        """)
        for r in dbscan_rows:
            activities.append({
                "type": "dbscan_run",
                "date": _iso(r["run_date"]),
                "detail": {
                    "run_id": r["id"],
                    "total_classified": r.get("total_classified"),
                    "total_outliers": r.get("total_outliers"),
                    "triggered_by": r.get("triggered_by"),
                },
            })

        # User registrations
        user_rows = await _safe_fetch(conn, """
            SELECT id, email, username, role, created_at
            FROM iug.users
            ORDER BY created_at DESC
            LIMIT 50
        """)
        for r in user_rows:
            activities.append({
                "type": "user_registered",
                "date": _iso(r["created_at"]),
                "detail": {
                    "user_id": r["id"],
                    "email": r["email"],
                    "username": r.get("username"),
                    "role": r["role"],
                },
            })

    # Sort all activities by date descending, then take the 50 most recent
    activities.sort(key=lambda a: a["date"] or "", reverse=True)
    activities = activities[:50]

    return {
        "total": len(activities),
        "activities": activities,
    }
