# 🎯 Orquestador de Eventos

Sistema event-driven para coordinar automáticamente:
- **Batch Scraping** → ETL → Refresh Views → Notificaciones
- **Inserts Individuales** → Eventos Tiempo Real → WebSocket

---

## 📁 Estructura

```
orchestrator/
├── __init__.py                      # start_orchestrator()
├── event_bus.py                     # Pub/Sub event system
├── post_scraping.py                 # Handler SCRAPING_COMPLETED (batch)
├── individual_insert.py             # PostgreSQL NOTIFY listener (tiempo real)
└── fastapi_integration_example.py  # Ejemplo integración
```

---

## 🔄 Flujo A: Batch Scraping (Muchos Registros)

```
┌─────────────────────────────────────┐
│ SCRAPER                             │
├─────────────────────────────────────┤
│ 1. Scrape 1000 inmuebles            │
│ 2. INSERT batch en BD               │
│    └─> Triggers SQL calculan scores│
│ 3. POST /api/scraping/{id}/complete│
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ EVENT BUS                           │
├─────────────────────────────────────┤
│ Emite: SCRAPING_COMPLETED           │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ POST_SCRAPING HANDLER               │
├─────────────────────────────────────┤
│ 1. ✅ ETL características           │
│ 2. ✅ Refresh vistas materializadas │
│ 3. ✅ Calcular stats agregadas      │
│ 4. ✅ Emitir VIEWS_REFRESHED        │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ WEBSOCKET MANAGER                   │
├─────────────────────────────────────┤
│ Broadcast a todos los clientes:     │
│ {                                   │
│   "event": "scraping_processed",    │
│   "n_inmuebles": 1000,              │
│   "stats": {...}                    │
│ }                                   │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ FRONTEND                            │
├─────────────────────────────────────┤
│ ws.on('scraping_processed', () => { │
│   refetchData() // Actualiza UI    │
│ })                                  │
└─────────────────────────────────────┘
```

---

## ⚡ Flujo B: Insert Individual (1 Registro)

```
┌─────────────────────────────────────┐
│ API / MANUAL                        │
├─────────────────────────────────────┤
│ INSERT INTO iug.inmueble (...)      │
│ VALUES (...)                        │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ POSTGRESQL TRIGGERS                 │
├─────────────────────────────────────┤
│ 1. trg_inmueble_indicadores (scores)│
│ 2. trg_inmueble_seguridad           │
│ 3. trg_inmueble_dimension           │
│ 4. trg_notify_inmueble_created ✨   │
│    └─> PERFORM pg_notify(...)       │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ POSTGRESQL NOTIFY LISTENER (Python) │
├─────────────────────────────────────┤
│ Escucha canal 'inmueble_created'    │
│ Payload: {id, tipo, ...}            │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ EVENT BUS                           │
├─────────────────────────────────────┤
│ Emite: INMUEBLE_CREATED             │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ WEBSOCKET MANAGER                   │
├─────────────────────────────────────┤
│ Broadcast inmediato:                │
│ {                                   │
│   "event": "inmueble_created",      │
│   "id_inmueble": 12345              │
│ }                                   │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ FRONTEND (Tiempo Real)              │
├─────────────────────────────────────┤
│ ws.on('inmueble_created', (data) => │
│   showNotification(data)            │
│   updateMap(data.id_inmueble)       │
│ })                                  │
└─────────────────────────────────────┘
```

---

## 🚀 Uso

### 1. Aplicar Migración SQL

```bash
# Reiniciar Docker para aplicar V24
docker restart iug-postgres
```

La migración V24 crea triggers `NOTIFY` que emiten eventos.

### 2. Integrar con FastAPI

```python
# services/api/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager
from services.orchestrator import start_orchestrator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await start_orchestrator()  # ✅ Inicia orquestador
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)
```

### 3. Emitir Evento de Scraping Completado

```python
# Desde el scraper, cuando termina batch:

import requests

requests.post(
    'http://localhost:8000/api/scraping/batch_001/complete',
    json={'n_inmuebles': 1000}
)

# → Dispara automáticamente:
#    ETL + Refresh Views + WebSocket Broadcast
```

### 4. Frontend Conecta a WebSocket

```javascript
// React/Vue/etc
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.event) {
    // Batch completado
    case 'scraping_processed':
      console.log(`Procesados ${data.n_inmuebles} inmuebles`);
      refetchIndicadores();
      break;
    
    // Individual en tiempo real
    case 'inmueble_created':
      console.log(`Nuevo inmueble #${data.id_inmueble}`);
      addMarkerToMap(data.id_inmueble);
      break;
  }
};
```

---

## 📊 Tipos de Eventos

```python
from services.orchestrator import EventType

# Scraping
EventType.SCRAPING_STARTED
EventType.SCRAPING_COMPLETED
EventType.SCRAPING_FAILED

# Inserts
EventType.INMUEBLE_CREATED
EventType.INMUEBLE_UPDATED

# ETL
EventType.ETL_STARTED
EventType.ETL_COMPLETED

# Vistas
EventType.VIEWS_REFRESHING
EventType.VIEWS_REFRESHED

# Modelos
EventType.MODEL_UPDATED
```

---

## 🔧 Configuración

### Variables de Entorno

```bash
# PostgreSQL
PG_HOST=localhost
PG_PORT=5434
PG_DATABASE=postgres
PG_USER=postgres
PG_PASSWORD=postgres

# MongoDB
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DATABASE=prueba
```

---

## 🎯 Endpoints API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/scraping/{id}/complete` | POST | Marca scraping completado, dispara orquestación |
| `/api/events/recent` | GET | Obtiene eventos recientes del event bus |
| `/api/orchestrator/stats` | GET | Estadísticas del orquestador |

---

## 📝 Logging

```python
import logging

# Ver eventos en tiempo real
logging.basicConfig(level=logging.INFO)

# Logs importantes:
# [EVENT] scraping_completed | api | {n_inmuebles: 1000}
# [ORCHESTRATOR] Procesando scraping completado: batch_001
# [ETL] Inicio carga características...
# [VIEWS] Refreshing iug.indicador_transporte_final...
# [LISTENER] Nuevo inmueble #12345 (Apartamento)
```

---

## 🧪 Testing

```python
# Simular evento de scraping completado
from services.orchestrator import event_bus, EventType

await event_bus.emit(
    EventType.SCRAPING_COMPLETED,
    {
        'scraping_id': 'test_001',
        'n_inmuebles': 100,
        'pagina': 'finca_raiz'
    }
)

# → Dispara post_scraping.py automáticamente
```

---

## ⚡ Performance

- **Event Bus:** In-memory (sin latencia)
- **PostgreSQL NOTIFY:** < 10ms latency
- **WebSocket Broadcast:** Asíncrono, no bloquea
- **ETL Batch:** Thread pool, no bloquea API

---

## 🔮 Futuro (Producción)

### Redis Pub/Sub (Para múltiples workers)

```python
import aioredis

redis = await aioredis.create_redis_pool('redis://localhost')

async def emit(event_type, data):
    await redis.publish(
        f'iug:events:{event_type}',
        json.dumps(data)
    )
```

### Celery (Tareas pesadas)

```python
# tasks.py
@celery.task
def run_heavy_etl():
    # ETL muy pesado
    pass
```

---

## 📖 Referencias

- [PostgreSQL NOTIFY/LISTEN](https://www.postgresql.org/docs/current/sql-notify.html)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Event-Driven Architecture](https://martinfowler.com/articles/201701-event-driven.html)
