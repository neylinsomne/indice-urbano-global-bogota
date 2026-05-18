"""
Event Bus - Sistema de Eventos para Orquestación

Event-driven architecture simple para conectar:
- Scraping → ETL → Refresh → Notificaciones
- Insert individual → Cálculo → WebSocket broadcast

Sin dependencias externas (Redis opcional para producción).
"""

from typing import Callable, Dict, List, Any
from enum import Enum
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Tipos de eventos del sistema"""
    
    # Scraping events
    SCRAPING_STARTED = "scraping_started"
    SCRAPING_PROGRESS = "scraping_progress"
    SCRAPING_COMPLETED = "scraping_completed"
    SCRAPING_FAILED = "scraping_failed"
    
    # Insert individual
    INMUEBLE_CREATED = "inmueble_created"
    INMUEBLE_UPDATED = "inmueble_updated"
    
    # Indicadores
    INDICATORS_CALCULATING = "indicators_calculating"
    INDICATORS_COMPLETED = "indicators_completed"
    
    # ETL
    ETL_STARTED = "etl_started"
    ETL_COMPLETED = "etl_completed"
    
    # Views
    VIEWS_REFRESHING = "views_refreshing"
    VIEWS_REFRESHED = "views_refreshed"
    
    # Models
    MODEL_TRAINING_STARTED = "model_training_started"
    MODEL_TRAINING_COMPLETED = "model_training_completed"
    MODEL_UPDATED = "model_updated"


class Event:
    """Evento con metadatos"""
    
    def __init__(self, event_type: EventType, data: Dict[str, Any], source: str = "system"):
        self.type = event_type
        self.data = data
        self.source = source
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict:
        """Serializa a diccionario para WebSocket/JSON"""
        return {
            'event': self.type.value,
            'data': self.data,
            'source': self.source,
            'timestamp': self.timestamp
        }


class EventBus:
    """
    Event bus simple en memoria
    
    Para producción, reemplazar con Redis Pub/Sub:
        import aioredis
        redis = await aioredis.create_redis_pool('redis://localhost')
    """
    
    def __init__(self):
        # {event_type: [callback1, callback2, ...]}
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 100
    
    async def subscribe(self, event_type: EventType, callback: Callable):
        """
        Registra callback para un tipo de evento
        
        Args:
            event_type: Tipo de evento a escuchar
            callback: async function(event: Event)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(callback)
        logger.info(f"Subscriber registrado para {event_type.value}")
    
    async def emit(self, event_type: EventType, data: Dict[str, Any], source: str = "system"):
        """
        Emite evento a todos los subscribers
        
        Args:
            event_type: Tipo de evento
            data: Datos del evento
            source: Fuente que emitió el evento
        """
        event = Event(event_type, data, source)
        
        # Guardar en historial
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        logger.info(f"[EVENT] {event_type.value} | {source} | {data}")
        
        # Notificar subscribers
        if event_type in self._subscribers:
            callbacks = self._subscribers[event_type]
            
            # Ejecutar todos los callbacks en paralelo
            tasks = [callback(event) for callback in callbacks]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log errores
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error en callback {i} de {event_type.value}: {result}")
    
    def get_recent_events(self, event_type: EventType = None, limit: int = 10) -> List[Event]:
        """Obtiene eventos recientes del historial"""
        if event_type:
            events = [e for e in self._event_history if e.type == event_type]
        else:
            events = self._event_history
        
        return events[-limit:]
    
    @property
    def stats(self) -> Dict:
        """Estadísticas del event bus"""
        return {
            'total_subscribers': sum(len(cbs) for cbs in self._subscribers.values()),
            'event_types_subscribed': len(self._subscribers),
            'events_in_history': len(self._event_history)
        }


# Instancia global
event_bus = EventBus()
