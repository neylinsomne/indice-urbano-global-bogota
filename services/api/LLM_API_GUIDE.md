# Guía del API LLM - Consultas Inteligentes

## Descripción General

El módulo LLM proporciona tres formas de consultar datos inmobiliarios:

1. **Tools Predefinidas**: Funciones optimizadas para consultas específicas (sin LLM)
2. **SQL Agent**: Preguntas en lenguaje natural procesadas con LLM (requiere OpenAI API)
3. **Análisis de Propiedades**: Evaluación automática de inmuebles con comparables

**Características clave:**
- ✅ **Caché automático**: Resultados se cachean 30 minutos (no se registran en BD)
- ✅ **Sin persistencia**: Solo en memoria, ideal para análisis exploratorios
- ✅ **Vistas optimizadas**: Consultas rápidas sobre datos agregados
- ✅ **LRU eviction**: Caché inteligente con límite de 100 entries

---

## Instalación

### 1. Instalar dependencias

```bash
pip install -r requirements_rag_ahp.txt
```

### 2. Configurar variables de entorno (opcional para SQL Agent)

```bash
# .env
OPENAI_API_KEY=sk-...  # Solo si quieres usar /api/llm/query
PG_HOST=localhost
PG_PORT=5434
PG_DB=postgres
PG_USER=postgres
PG_PASSWORD=xd
```

### 3. Ejecutar migraciones

```bash
# Crear vistas optimizadas para LLM
flyway migrate
```

---

## Endpoints

### 1. Listar Tools Disponibles

**GET** `/api/llm/tools`

Retorna todas las tools disponibles con descripciones.

**Respuesta:**
```json
{
  "tools": {
    "get_estadisticas_localidad": {
      "description": "Obtiene estadísticas de inmuebles agrupadas por localidad",
      "parameters": {
        "nombre_localidad": "Nombre de la localidad (opcional)"
      }
    },
    "get_top_oportunidades": {
      "description": "Encuentra las mejores oportunidades (mejor relación precio/calidad)",
      "parameters": {
        "limite": "Número de resultados",
        "tipo_inmueble": "Tipo de inmueble (opcional)",
        "iurb_min": "I_URB mínimo requerido"
      }
    }
    // ... más tools
  },
  "total": 8
}
```

---

### 2. Ejecutar Tool Específica

**POST** `/api/llm/tool/execute`

Ejecuta una tool predefinida con parámetros.

**Request Body:**
```json
{
  "tool_name": "get_top_oportunidades",
  "params": {
    "limite": 5,
    "tipo_inmueble": "Apartamento",
    "iurb_min": 3.5
  }
}
```

**Respuesta:**
```json
{
  "tool": "get_top_oportunidades",
  "cached": false,
  "result": [
    {
      "id_inmueble": 12345,
      "tipo_inmueble": "Apartamento",
      "precio": 350000000,
      "ubicacion": "Chapinero, Bogotá",
      "area": 85,
      "habitaciones": 3,
      "banos": 2,
      "iurb": 4.25,
      "precio_por_iurb": 82352941.18,
      "percentil_oportunidad": 0.05
    }
    // ... más resultados
  ]
}
```

**Tools disponibles:**

| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `get_estadisticas_localidad` | Estadísticas por localidad | `nombre_localidad?` |
| `get_top_oportunidades` | Mejores oportunidades | `limite`, `tipo_inmueble?`, `iurb_min` |
| `get_precios_por_tipo` | Precios por tipo | - |
| `get_ranking_zonas` | Ranking de zonas | `ordenar_por` (iurb, iacc, iseg, ihed, ipnu) |
| `get_inmuebles_contexto` | Inmuebles con contexto | `id_inmueble?`, `localidad?`, `limite` |
| `get_dotaciones_por_zona` | Dotaciones por zona | `lat?`, `lon?`, `radio_km` |
| `buscar_inmuebles_similares` | Inmuebles similares | `precio_referencia`, `area_referencia`, `tipo_inmueble`, `margen_precio?`, `margen_area?`, `limite` |
| `get_estadisticas_generales` | Estadísticas globales | - |

---

### 3. Consulta en Lenguaje Natural

**POST** `/api/llm/query`

Pregunta en lenguaje natural procesada con SQL Agent.

**Requiere:** `OPENAI_API_KEY` configurado

**Request Body:**
```json
{
  "question": "¿Cuál es el precio promedio de apartamentos en Chapinero?"
}
```

**Respuesta:**
```json
{
  "question": "¿Cuál es el precio promedio de apartamentos en Chapinero?",
  "answer": "El precio promedio de apartamentos en Chapinero es de $450,250,000 COP, basado en 142 inmuebles disponibles. El rango va desde $280,000,000 hasta $850,000,000.",
  "cached": false
}
```

**Ejemplos de preguntas:**

```javascript
// Pregunta simple
{
  "question": "¿Cuántos inmuebles hay en Usaquén?"
}

// Comparación
{
  "question": "Compara los precios promedio de apartamentos vs casas"
}

// Ranking
{
  "question": "¿Qué localidades tienen mejor indicador de seguridad?"
}

// Estadísticas
{
  "question": "Dame las estadísticas de precios para apartamentos de 3 habitaciones"
}

// Análisis
{
  "question": "¿Dónde están las mejores oportunidades con I_URB superior a 4.0?"
}
```

---

### 4. Análisis Completo de Inmueble

**POST** `/api/llm/analyze/property`

Genera análisis completo con comparables y evaluación.

**Request Body:**
```json
{
  "id_inmueble": 12345
}
```

**Respuesta:**
```json
{
  "inmueble": {
    "id_inmueble": 12345,
    "tipo_inmueble": "Apartamento",
    "precio": 350000000,
    "ubicacion": "Chapinero, Bogotá",
    "area": 85,
    "iurb": 4.25,
    "nombre_localidad": "Chapinero",
    "salud_500m": 3,
    "educacion_500m": 5,
    "recreacion_500m": 2,
    "transmilenio_500m": 1
  },
  "similares": [
    {
      "id_inmueble": 67890,
      "precio": 365000000,
      "area": 88,
      "iurb": 4.15,
      "diferencia_precio": 15000000
    }
    // ... 4 más
  ],
  "estadisticas_localidad": {
    "nombre_localidad": "Chapinero",
    "total_inmuebles": 142,
    "precio_promedio": 450250000,
    "iurb_promedio": 4.02
  },
  "evaluacion": {
    "categoria": "Buena Oportunidad",
    "mensaje": "Precio 4.3% menor que similares con I_URB comparable",
    "precio_promedio_similares": 366000000,
    "diferencia_precio_pct": -4.37,
    "iurb_promedio_similares": 4.18,
    "diferencia_iurb": 0.07,
    "total_similares": 5
  }
}
```

**Categorías de evaluación:**
- **Excelente Oportunidad**: Precio <-10% y mejor I_URB
- **Buena Oportunidad**: Precio menor e I_URB comparable
- **Precio de Mercado**: Precio y calidad alineados
- **Sobrevalorado**: Precio >+10% con peor I_URB

---

### 5. Estadísticas del Caché

**GET** `/api/llm/cache/stats`

Métricas del caché LLM.

**Respuesta:**
```json
{
  "size": 35,
  "max_size": 100,
  "hit_count": 142,
  "miss_count": 58,
  "hit_rate": 71.0,
  "ttl_minutes": 30
}
```

---

### 6. Limpiar Caché

**POST** `/api/llm/cache/clear`

Limpia todo el caché (útil después de actualizar datos).

**Respuesta:**
```json
{
  "message": "Caché limpiado exitosamente",
  "cache_stats": {
    "size": 0,
    "hit_count": 0,
    "miss_count": 0
  }
}
```

---

### 7. Ejemplos de Uso

**GET** `/api/llm/examples`

Retorna ejemplos completos para cada endpoint.

---

## Vistas Disponibles

El módulo LLM consulta vistas optimizadas (schema `iug`):

### v_estadisticas_localidad
Estadísticas agregadas por localidad.

**Campos:**
- `nombre_localidad`
- `total_inmuebles`, `precio_promedio`, `precio_minimo`, `precio_maximo`
- `iurb_promedio`, `iacc_promedio`, `iseg_promedio`, `ihed_promedio`, `ipnu_promedio`
- `precio_por_iurb_promedio`
- `total_apartamentos`, `total_casas`

### v_top_oportunidades
Inmuebles con mejor precio/I_URB.

**Campos:**
- Todos los campos de inmueble
- `percentil_oportunidad` (0.0-1.0)

### v_precios_por_tipo
Estadísticas por tipo de inmueble.

**Campos:**
- `tipo_inmueble`, `total`
- `precio_promedio`, `precio_mediana`, `precio_p25`, `precio_p75`
- `area_promedio`, `precio_m2_promedio`

### v_ranking_zonas
Ranking de localidades por indicador.

**Campos:**
- `nombre_localidad`, `total_inmuebles`
- `iurb_promedio`, `iacc_promedio`, `iseg_promedio`, `ihed_promedio`, `ipnu_promedio`
- `ranking_iurb`, `ranking_iacc`, `ranking_iseg`, `ranking_ihed`, `ranking_ipnu`

### v_inmuebles_contexto
Inmuebles con contexto completo.

**Campos:**
- Todos los campos de inmueble
- `nombre_localidad`
- `salud_500m`, `educacion_500m`, `recreacion_500m` (conteos)
- `transmilenio_500m` (conteo de estaciones)
- `tasa_hurto_localidad`

### v_dotaciones_por_zona
Grid 1km x 1km con conteo de dotaciones.

**Campos:**
- `lat_centro`, `lon_centro`
- `total_salud`, `total_educacion`, `total_comercio`, `total_cultura`, `total_recreacion`
- `total_dotaciones`

---

## Ejemplos de Código

### JavaScript/Frontend

```javascript
// 1. Obtener mejores oportunidades
async function getMejoresOportunidades() {
  const response = await fetch('http://localhost:8000/api/llm/tool/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tool_name: 'get_top_oportunidades',
      params: {
        limite: 10,
        tipo_inmueble: 'Apartamento',
        iurb_min: 3.5
      }
    })
  });

  const data = await response.json();
  console.log('Oportunidades:', data.result);
  console.log('Desde caché:', data.cached);
}

// 2. Pregunta en lenguaje natural (requiere OpenAI API Key)
async function preguntarLLM(pregunta) {
  const response = await fetch('http://localhost:8000/api/llm/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: pregunta })
  });

  const data = await response.json();
  console.log('Respuesta:', data.answer);
}

// 3. Analizar inmueble específico
async function analizarInmueble(id) {
  const response = await fetch('http://localhost:8000/api/llm/analyze/property', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_inmueble: id })
  });

  const analisis = await response.json();
  console.log('Evaluación:', analisis.evaluacion.categoria);
  console.log('Mensaje:', analisis.evaluacion.mensaje);
  console.log('Similares:', analisis.similares.length);
}

// 4. Estadísticas de caché
async function verCacheStats() {
  const response = await fetch('http://localhost:8000/api/llm/cache/stats');
  const stats = await response.json();
  console.log(`Hit rate: ${stats.hit_rate}%`);
  console.log(`Cache size: ${stats.size}/${stats.max_size}`);
}
```

### Python

```python
import requests

BASE_URL = "http://localhost:8000/api/llm"

# 1. Obtener estadísticas por localidad
def get_stats_localidad(nombre):
    response = requests.post(f"{BASE_URL}/tool/execute", json={
        "tool_name": "get_estadisticas_localidad",
        "params": {"nombre_localidad": nombre}
    })
    return response.json()

# 2. Ranking de zonas
def get_ranking(indicador="iurb"):
    response = requests.post(f"{BASE_URL}/tool/execute", json={
        "tool_name": "get_ranking_zonas",
        "params": {"ordenar_por": indicador}
    })
    return response.json()

# 3. Buscar similares para análisis comparativo
def buscar_comparables(precio, area, tipo):
    response = requests.post(f"{BASE_URL}/tool/execute", json={
        "tool_name": "buscar_inmuebles_similares",
        "params": {
            "precio_referencia": precio,
            "area_referencia": area,
            "tipo_inmueble": tipo,
            "limite": 10
        }
    })
    return response.json()

# Uso
stats = get_stats_localidad("Chapinero")
print(f"Precio promedio: ${stats['result'][0]['precio_promedio']:,}")

ranking = get_ranking("iacc")
print(f"Mejor zona en accesibilidad: {ranking['result'][0]['nombre_localidad']}")
```

### cURL

```bash
# 1. Listar tools
curl http://localhost:8000/api/llm/tools

# 2. Ejecutar tool
curl -X POST http://localhost:8000/api/llm/tool/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "get_top_oportunidades",
    "params": {"limite": 5, "iurb_min": 4.0}
  }'

# 3. Pregunta natural (requiere OPENAI_API_KEY)
curl -X POST http://localhost:8000/api/llm/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cuáles son las mejores zonas de Bogotá?"
  }'

# 4. Analizar inmueble
curl -X POST http://localhost:8000/api/llm/analyze/property \
  -H "Content-Type: application/json" \
  -d '{"id_inmueble": 12345}'

# 5. Stats de caché
curl http://localhost:8000/api/llm/cache/stats

# 6. Limpiar caché
curl -X POST http://localhost:8000/api/llm/cache/clear
```

---

## Casos de Uso

### 1. Dashboard de Oportunidades

```javascript
// Frontend: Mostrar mejores oportunidades en tiempo real
async function updateDashboard() {
  const oportunidades = await fetch('/api/llm/tool/execute', {
    method: 'POST',
    body: JSON.stringify({
      tool_name: 'get_top_oportunidades',
      params: { limite: 20, iurb_min: 3.0 }
    })
  }).then(r => r.json());

  renderOportunidades(oportunidades.result);
}
```

### 2. Comparación de Zonas

```python
# Backend: Análisis comparativo de localidades
def comparar_localidades(localidades):
    resultados = []
    for loc in localidades:
        stats = get_stats_localidad(loc)
        if stats['result']:
            resultados.append(stats['result'][0])

    # Ordenar por I_URB promedio
    resultados.sort(key=lambda x: x['iurb_promedio'], reverse=True)
    return resultados
```

### 3. Valoración Automática

```python
# Backend: Estimar si un precio es justo
def valorar_inmueble(precio, area, tipo, lat, lon):
    # Buscar similares
    similares = buscar_comparables(precio, area, tipo)

    # Calcular desviación
    precios = [s['precio'] for s in similares['result']]
    precio_mercado = sum(precios) / len(precios)

    diferencia_pct = ((precio - precio_mercado) / precio_mercado) * 100

    if diferencia_pct < -10:
        return "Excelente precio"
    elif diferencia_pct < 0:
        return "Buen precio"
    elif diferencia_pct < 10:
        return "Precio de mercado"
    else:
        return "Sobrevalorado"
```

### 4. Chatbot Inmobiliario

```javascript
// Frontend: Chat con SQL Agent
async function chatbot(mensaje) {
  const respuesta = await fetch('/api/llm/query', {
    method: 'POST',
    body: JSON.stringify({ question: mensaje })
  }).then(r => r.json());

  return respuesta.answer;
}

// Ejemplos de conversación:
// Usuario: "¿Dónde puedo comprar un apartamento de 3 habitaciones por menos de 400 millones?"
// Usuario: "Compara Chapinero con Usaquén en términos de seguridad"
// Usuario: "¿Cuál es el precio promedio por m² en Bogotá?"
```

---

## Performance

### Benchmarks (hardware promedio)

| Operación | Primera vez | Desde caché |
|-----------|-------------|-------------|
| `get_top_oportunidades` | ~200ms | ~2ms |
| `get_estadisticas_localidad` | ~150ms | ~1ms |
| `get_ranking_zonas` | ~300ms | ~2ms |
| `analyze_property` | ~500ms | ~3ms |
| SQL Agent query | ~2-5s | ~2ms |

### Optimizaciones

1. **Índices en vistas** (automático en migración V101)
2. **Caché LRU** con 100 entries (ajustable)
3. **TTL de 30 minutos** (ajustable)
4. **Queries optimizadas** (sin JOINs innecesarios)

---

## Troubleshooting

### Error: "LLM Agent no inicializado"

**Causa:** El agente no se inicializó en el startup.

**Solución:**
```python
# Verificar en logs:
# ✓ LLM Agent inicializado

# Si no aparece, revisar conexión a DB
```

### Error: "SQL Agent no disponible"

**Causa:** `OPENAI_API_KEY` no configurado o LangChain no instalado.

**Solución:**
```bash
# 1. Instalar dependencias
pip install langchain langchain-openai langchain-community sqlalchemy

# 2. Configurar API key
export OPENAI_API_KEY=sk-...

# 3. Reiniciar servidor
```

### Hit rate bajo (<50%)

**Causa:** TTL muy corto o queries muy variadas.

**Solución:**
```python
# En llm/cache_manager.py, ajustar:
llm_cache = CacheManager(max_size=200, ttl_minutes=60)
```

### Caché crece demasiado

**Causa:** `max_size` muy grande.

**Solución:**
```python
# Reducir tamaño o limpiar periódicamente
POST /api/llm/cache/clear
```

---

## Roadmap

- [ ] Métricas con Prometheus (latencia, hit rate)
- [ ] Cache distribuido con Redis
- [ ] Streaming para respuestas largas del SQL Agent
- [ ] Tools adicionales (predicción de precios, análisis de tendencias)
- [ ] Webhooks para invalidación de caché
- [ ] Multi-idioma (inglés, portugués)

---

## FAQ

**¿Los resultados se guardan en la base de datos?**
No, todo es en memoria (caché). Ideal para análisis exploratorios sin contaminar la BD.

**¿Puedo usar las tools sin OpenAI API Key?**
Sí, las tools predefinidas (`/tool/execute`) funcionan sin LLM. Solo `/query` requiere API key.

**¿Cuánto cuesta usar el SQL Agent?**
Depende del modelo. Con `gpt-4o-mini`: ~$0.0001 por pregunta. El caché reduce costos en queries repetidas.

**¿Cómo ajusto el tamaño del caché?**
Edita `llm/cache_manager.py` y cambia `max_size` y `ttl_minutes`.

**¿Puedo agregar nuevas tools?**
Sí, agrega la función en `llm/tools.py` y regístrala en `AVAILABLE_TOOLS`.

---

## Contacto

Para bugs o sugerencias, crear issue en el repositorio.
