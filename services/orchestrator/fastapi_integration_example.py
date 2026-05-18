"""
Ejemplo de integración del orquestador con FastAPI

Agregar a services/api/main.py
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager

# Import orquestador
from services.orchestrator import start_orchestrator, event_bus, EventType


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events para FastAPI"""
    
    # Startup
    print("\n🚀 Iniciando aplicación...")
    
    # Iniciar orquestador
    await start_orchestrator()
    
    yield
    
    # Shutdown
    print("\n� � Cerrando aplicación...")


# Crear app con lifespan
app = FastAPI(
    title="IUG API",
    version="2.0.0",
    lifespan=lifespan
)


# Ejemplo de endpoint que emite evento de scraping completado
@app.post("/api/scraping/{scraping_id}/complete")
async def mark_scraping_completed(scraping_id: str, n_inmuebles: int):
    """
    Marca scraping como completado y dispara orquestación
    
    Llamar desde scraper cuando termina batch:
    
    ```python
    # Al final del scraper:
    requests.post('http://localhost:8000/api/scraping/batch_001/complete', 
                  json={'n_inmuebles': 1000})
    ```
    """
    
    # Emitir evento SCRAPING_COMPLETED
    await event_bus.emit(
        EventType.SCRAPING_COMPLETED,
        {
            'scraping_id': scraping_id,
            'n_inmuebles': n_inmuebles,
            'pagina': 'finca_raiz',  # O detectar automáticamente
            'duration_seconds': 0  # Calcular si se tiene timestamp inicio
        },
        source='api'
    )
    
    return {
        'status': 'ok',
        'message': f'Scraping {scraping_id} marcado como completado',
        'n_inmuebles': n_inmuebles,
        'processing': 'Orquestador procesando en background'
    }


# Endpoint para obtener eventos recientes
@app.get("/api/events/recent")
async def get_recent_events(event_type: str = None, limit: int = 10):
    """Obtiene eventos recientes del event bus"""
    
    event_type_enum = EventType(event_type) if event_type else None
    events = event_bus.get_recent_events(event_type_enum, limit)
    
    return {
        'events': [e.to_dict() for e in events],
        'count': len(events)
    }


# Endpoint para stats del orquestador
@app.get("/api/orchestrator/stats")
async def get_orchestrator_stats():
    """Estadísticas del orquestador"""
    
    return {
        'event_bus': event_bus.stats,
        'status': 'running'
    }
