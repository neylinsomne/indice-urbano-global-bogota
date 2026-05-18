"""
Orchestrator Package

Sistema de orquestación event-driven para:
- Batch scraping → ETL → Refresh → Notificaciones
- Individual inserts → Eventos en tiempo real

Componentes:
- event_bus: Sistema de eventos pub/sub
- post_scraping: Handler para scraping completado (batch)
- individual_insert: Listener PostgreSQL NOTIFY (tiempo real)
"""

from .event_bus import event_bus, EventType
from .post_scraping import setup as setup_post_scraping
from .individual_insert import setup as setup_individual_insert

import logging

logger = logging.getLogger(__name__)


async def start_orchestrator():
    """
    Inicia el orquestador completo

    Llama a esto desde main.py de FastAPI en startup event:

    @app.on_event("startup")
    async def startup():
        from services.orchestrator import start_orchestrator
        await start_orchestrator()

    NOTA: La carga de datos estáticos se ha movido a services/database/orquestador_carga.py
          que se ejecuta como job separado en GitHub Actions después del scraping.
          El orchestrator ahora solo maneja eventos en tiempo real.
    """
    logger.info("="*60)
    logger.info(" INICIANDO ORQUESTADOR DE EVENTOS")
    logger.info("="*60)

    # Setup event handlers
    await setup_post_scraping()
    await setup_individual_insert()

    logger.info(f"[ORCHESTRATOR] Event bus stats: {event_bus.stats}")
    logger.info("[ORCHESTRATOR] ✓ Orquestador de eventos iniciado")




__all__ = [
    'event_bus',
    'EventType',
    'start_orchestrator'
]
