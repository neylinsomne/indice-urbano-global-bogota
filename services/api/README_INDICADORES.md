# 🚀 Sistema de Indicadores en Tiempo Real - Guía de Implementación

## 📦 Archivos Creados

### Backend Core
1. **`websocket_manager.py`** - Gestiona conexiones WebSocket
2. **`services/pca_service.py`** - Calcula pesos PCA con scikit-learn
3. **`routers/indicadores.py`** - Endpoints REST + WebSocket
4. **`listeners/postgres_listener.py`** - Escucha eventos de PostgreSQL

### Database
5. **`migrations/V14__transport_indicators.sql`** - Schema completo:
   - Función `calcular_score_transporte_gravity()`
   - Tabla `indicador_transporte_raw` (scores calculados 1 vez)
   - Tabla `pca_pesos_tipo` (pesos PCA actualizables)
   - Vista materializada `indicador_transporte_final`
   - Trigger automático en INSERT

---

## 🛠️ Instalación con Docker

### 1. Aplicar Migración V14

```bash
cd services/database
docker-compose up -d iug-flyway
```

Flyway aplicará automáticamente `V14__transport_indicators.sql`.

### 2. Verificar Tablas Creadas

```bash
docker run --rm --network gisnet -e PGPASSWORD=xd postgis/postgis:16-3.4 psql -h iug-postgres -U postgres -c "\dt iug.indicador*"
```

Deberías ver:
- `iug.indicador_transporte_raw`
- `iug.pca_pesos_tipo`

### 3. Rebuild de la API (con nuevas dependencias)

```bash
cd services/api
docker-compose build app
docker-compose up -d
```

---

## 🔌 Integración en `main.py`

Copia el contenido de `INTEGRATION_EXAMPLE.py` a tu `main.py`:

**Secciones clave:**
1. Imports nuevos
2. `lifespan()` para inicializar servicios
3. Incluir router de indicadores
4. Dependency `get_db_pool()`

---

## 🧪 Testing

### 1. Insertar Inmueble de Prueba

```sql
INSERT INTO iug.inmueble (tipo_inmueble, geom)
VALUES ('Apartamento', ST_SetSRID(ST_MakePoint(-74.0817, 4.6097), 4326))
RETURNING id_inmueble;
```

Esto dispara automáticamente el trigger que calcula gravity scores.

### 2. Verificar Scores Raw

```sql
SELECT * FROM iug.indicador_transporte_raw 
WHERE id_inmueble = <id>;
```

### 3. Recalcular PCA vía API

```bash
curl -X POST http://localhost:8000/api/indicadores/recalcular-pca
```

### 4. Refrescar Vista Materializada

```bash
curl -X POST http://localhost:8000/api/indicadores/refresh-scores
```

### 5. Conectar WebSocket (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/api/indicadores/ws?client_id=test1');

ws.onopen = () => console.log('✅ Conectado');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('📡 Evento:', data);
    
    if (data.event === 'pca_recalculado') {
        console.log(`PCA actualizado para: ${data.tipos_actualizados}`);
    }
    
    if (data.event === 'scores_actualizados') {
        console.log(`Scores refrescados: ${data.total_inmuebles} inmuebles`);
    }
};

ws.send(JSON.stringify({
    action: "get_score",
    id_inmueble: 123
}));
```

---

## 📊 Flujo Completo

### Caso 1: Scraping Batch (100 inmuebles)

```
1. Scraper inserta 100 inmuebles
   └─> Cada INSERT calcula gravity (1 vez por inmueble)
   └─> Guarda en indicador_transporte_raw

2. Scraper termina → llama API:
   POST /api/indicadores/recalcular-pca
   └─> Backend calcula PCA con TODOS los apartamentos
   └─> Actualiza pca_pesos_tipo
   └─> Broadcast WebSocket: "pca_recalculado"

3. Backend llama:
   POST /api/indicadores/refresh-scores
   └─> REFRESH MATERIALIZED VIEW
   └─> Broadcast WebSocket: "scores_actualizados"

4. Frontend recibe eventos y actualiza UI
```

### Caso 2: Inserción Manual (1 inmueble)

```
1. Usuario inserta 1 apartamento
   └─> Calcula gravity → guarda en _raw
   
2. Score final se calcula con pesos existentes
   └─> Sin recalcular PCA (usa pesos guardados)
   
3. (Opcional) Después de N inserciones:
   └─> Administrador puede forzar POST /recalcular-pca
```

---

## 🎯 Endpoints Disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/indicadores/recalcular-pca` | Recalcula pesos PCA (después de batch) |
| `POST` | `/api/indicadores/refresh-scores` | Refresca vista materializada |
| `GET` | `/api/indicadores/{id_inmueble}` | Obtiene indicadores de un inmueble |
| `WS` | `/api/indicadores/ws` | WebSocket para notificaciones |

---

## 🔧 Troubleshooting

### Error: "PCAService no inicializado"
- Verifica que `lifespan()` esté configurado en FastAPI
- Revisa logs de startup

### WebSocket no conecta
- Verifica que el puerto esté expuesto en docker-compose
- Revisa CORS si estás en frontend externo

### Scores no se actualizan
- Ejecuta manualmente: `SELECT iug.refresh_indicadores_transporte();`
- Verifica que la vista materializada exista

---

## 📝 Variables de Entorno

Asegúrate de tener en `.env`:

```env
PG_HOST=iug-postgres
PG_PORT=5432
PG_DB=postgres
PG_USER=postgres
PG_PASSWORD=xd
```

---

## 🚀 Próximos Pasos

1. ✅ Aplicar migración V14
2. ✅ Rebuild API con nuevas dependencias
3. ✅ Integrar código en main.py
4. ⏳ Probar inserción de inmuebles
5. ⏳ Verificar WebSocket
6. ⏳ Integrar con scraper de FincaRaiz
