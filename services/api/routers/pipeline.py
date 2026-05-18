"""
Router Pipeline - Trigger automatico del pipeline de analisis post-scraping.

Endpoints:
  POST /pipeline/run       → Evaluacion de umbrales + ejecucion DBSCAN y/o Regresion.
  POST /pipeline/complete  → Ciclo completo: MongoDB→PostgreSQL + DBSCAN + Regresion.
  GET  /pipeline/status    → Estado del ultimo pipeline ejecutado.

Autenticados via X-Pipeline-Secret (secreto compartido entre
el scraper y la API). No requiere JWT de usuario.

Flujo /complete (post-scraping):
  Scraper termina → POST /pipeline/complete
    → migrate_mongo_to_pg()  (MongoDB Atlas → PostgreSQL)
    → should_reclassify()?   → DBSCAN
    → should_retrain()?      → Regresion
    → Retorna reporte completo
"""
import logging
import os
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException

from db.postgre import get_db_pool
from services.outlier_service import run_outlier_classification, should_reclassify
from services.regression_service import train_all_models, should_retrain
from services.migration_service import migrate_mongo_to_pg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _get_pipeline_secret() -> str:
    return os.getenv("PIPELINE_SECRET", "")


async def _verify_secret(x_pipeline_secret: str = Header(None)):
    secret = _get_pipeline_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Pipeline no configurado: define PIPELINE_SECRET en el entorno",
        )
    if x_pipeline_secret != secret:
        raise HTTPException(status_code=403, detail="Pipeline secret invalido")


@router.post("/run")
async def run_pipeline(
    db: asyncpg.Pool = Depends(get_db_pool),
    _: None = Depends(_verify_secret),
):
    """
    Punto de entrada del pipeline automatico post-scraping.
    El scraper llama a este endpoint al finalizar cada batch de datos.

    Evalua independientemente:
      1. should_reclassify() → si hay suficientes datos nuevos, corre DBSCAN
      2. should_retrain()    → si el dataset limpio cambio significativamente, re-entrena regresion

    Retorna un reporte completo del pipeline.
    """
    report = {
        'dbscan_triggered': False,
        'dbscan_trigger_reasons': [],
        'dbscan_n_new': 0,
        'dbscan': None,
        'regression_triggered': False,
        'regression_trigger_reasons': [],
        'regression_n_new_clean': 0,
        'regression': None,
    }

    async with db.acquire() as conn:
        # ── Paso 1: evaluar y ejecutar DBSCAN ──
        dbscan_trigger = await should_reclassify(conn)
        report['dbscan_trigger_reasons'] = dbscan_trigger.get('reasons', [])
        report['dbscan_n_new'] = dbscan_trigger.get('n_new', 0)

        if dbscan_trigger['trigger']:
            report['dbscan_triggered'] = True
            logger.info(f"Pipeline: auto-DBSCAN disparado — {dbscan_trigger['reasons']}")
            try:
                # admin_id=None → triggered_by queda NULL (pipeline automatico)
                report['dbscan'] = await run_outlier_classification(conn, admin_id=None)
            except Exception as e:
                logger.error(f"Pipeline DBSCAN fallo: {e}")
                report['dbscan'] = {'error': str(e)}
        else:
            logger.info(
                f"Pipeline: DBSCAN no disparado — "
                f"{dbscan_trigger.get('message', 'umbrales no alcanzados')}"
            )

        # ── Paso 2: evaluar y ejecutar Regresion ──
        # (corre independientemente del DBSCAN — puede que haya suficientes
        # datos limpios aunque DBSCAN no se haya disparado esta vez)
        regression_trigger = await should_retrain(conn)
        report['regression_trigger_reasons'] = regression_trigger.get('reasons', [])
        report['regression_n_new_clean'] = regression_trigger.get('new_clean', 0)

        if regression_trigger['trigger']:
            report['regression_triggered'] = True
            logger.info(f"Pipeline: auto-Regresion disparada — {regression_trigger['reasons']}")
            try:
                report['regression'] = await train_all_models(
                    conn, admin_id=None, trigger_reason='auto_pipeline',
                )
            except Exception as e:
                logger.error(f"Pipeline Regresion fallo: {e}")
                report['regression'] = {'error': str(e)}
        else:
            logger.info(
                f"Pipeline: Regresion no disparada — "
                f"{regression_trigger.get('message', 'umbrales no alcanzados')}"
            )

    return report


# ── Estado in-memory del último pipeline ──
_last_pipeline_status = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'stage': None,
    'result': None,
}


@router.post("/complete")
async def run_complete_pipeline(
    db: asyncpg.Pool = Depends(get_db_pool),
    _: None = Depends(_verify_secret),
):
    """
    Pipeline completo post-scraping:
      1. Migración MongoDB Atlas → PostgreSQL (f_upsert_inmueble)
      2. Evaluación + ejecución DBSCAN (outliers)
      3. Evaluación + ejecución Regresión (modelos)

    Llamado automáticamente por los scrapers al terminar,
    o manualmente vía admin con X-Pipeline-Secret.
    """
    global _last_pipeline_status

    if _last_pipeline_status['running']:
        raise HTTPException(
            status_code=409,
            detail="Pipeline ya en ejecución, espera a que termine",
        )

    _last_pipeline_status = {
        'running': True,
        'started_at': datetime.utcnow().isoformat(),
        'finished_at': None,
        'stage': 'migration',
        'result': None,
    }

    report = {
        'migration': None,
        'spatial_assignment': None,
        'indicators': None,
        'dbscan_triggered': False,
        'dbscan': None,
        'regression_triggered': False,
        'regression': None,
    }

    try:
        async with db.acquire() as conn:
            # ── Paso 1: Migración MongoDB → PostgreSQL ──
            _last_pipeline_status['stage'] = 'migration'
            logger.info("Pipeline complete: iniciando migración MongoDB → PostgreSQL")
            try:
                report['migration'] = await migrate_mongo_to_pg(conn)
                n_ins = report['migration']['total_inserted']
                logger.info(f"Pipeline complete: migración OK — {n_ins} nuevos insertados")
            except Exception as e:
                logger.error(f"Pipeline complete: migración falló — {e}")
                report['migration'] = {'error': str(e)}

            # ── Paso 1.5: Asignar barrios/localidades espacialmente ──
            _last_pipeline_status['stage'] = 'spatial_assignment'
            logger.info("Pipeline complete: asignando barrios y localidades")
            try:
                row = await conn.fetchrow("SELECT * FROM iug.f_asignar_barrio_localidad()")
                if row:
                    report['spatial_assignment'] = {
                        'intersect': row['total_asignados'],
                        'nearest': row['total_por_cercania'],
                    }
                    logger.info(f"Pipeline complete: barrios asignados — {row['total_asignados']} intersect, {row['total_por_cercania']} nearest")
            except Exception as e:
                logger.warning(f"Pipeline complete: asignación espacial falló — {e}")
                report['spatial_assignment'] = {'error': str(e)}

            # ── Paso 1.6: Recalcular indicadores ──
            _last_pipeline_status['stage'] = 'indicators'
            logger.info("Pipeline complete: recalculando indicadores")
            try:
                row = await conn.fetchrow("SELECT * FROM iug.f_recalcular_indicadores()")
                if row:
                    report['indicators'] = {'inmuebles_actualizados': row['inmuebles_actualizados']}
                    logger.info(f"Pipeline complete: indicadores recalculados — {row['inmuebles_actualizados']} inmuebles")
            except Exception as e:
                logger.warning(f"Pipeline complete: indicadores fallaron — {e}")
                report['indicators'] = {'error': str(e)}

            # ── Paso 2: DBSCAN ──
            _last_pipeline_status['stage'] = 'dbscan'
            dbscan_trigger = await should_reclassify(conn)
            if dbscan_trigger['trigger']:
                report['dbscan_triggered'] = True
                logger.info(f"Pipeline complete: DBSCAN disparado — {dbscan_trigger['reasons']}")
                try:
                    report['dbscan'] = await run_outlier_classification(conn, admin_id=None)
                except Exception as e:
                    logger.error(f"Pipeline complete: DBSCAN falló — {e}")
                    report['dbscan'] = {'error': str(e)}

            # ── Paso 3: Regresión ──
            _last_pipeline_status['stage'] = 'regression'
            regression_trigger = await should_retrain(conn)
            if regression_trigger['trigger']:
                report['regression_triggered'] = True
                logger.info(f"Pipeline complete: Regresión disparada — {regression_trigger['reasons']}")
                try:
                    report['regression'] = await train_all_models(
                        conn, admin_id=None, trigger_reason='auto_pipeline_complete',
                    )
                except Exception as e:
                    logger.error(f"Pipeline complete: Regresión falló — {e}")
                    report['regression'] = {'error': str(e)}

    finally:
        _last_pipeline_status.update({
            'running': False,
            'finished_at': datetime.utcnow().isoformat(),
            'stage': 'done',
            'result': report,
        })

    return report


@router.get("/status")
async def pipeline_status():
    """Estado del último pipeline ejecutado."""
    return _last_pipeline_status
