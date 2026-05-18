# Guía Completa: RAG + AHP para Búsqueda Inteligente

Sistema avanzado que combina:
1. **RAG (Retrieval-Augmented Generation)**: Búsquedas semánticas en dotaciones urbanas
2. **AHP (Analytical Hierarchy Process)**: Personalización de pesos según preferencias del usuario

---

## Tabla de Contenidos

1. [Instalación y Setup](#instalación-y-setup)
2. [RAG: Búsqueda Semántica](#rag-búsqueda-semántica)
3. [AHP: Personalización de Pesos](#ahp-personalización-de-pesos)
4. [Casos de Uso End-to-End](#casos-de-uso-end-to-end)
5. [Integración con LangChain (Opcional)](#integración-con-langchain)

---

## Instalación y Setup

### Requisitos

```bash
# Básicos (ya instalados)
pip install fastapi uvicorn asyncpg pydantic

# Para RAG (búsqueda semántica)
pip install sentence-transformers

# Para LangChain (opcional, queries avanzadas)
pip install langchain openai
```

### Iniciar API

```bash
cd services/api
uvicorn main:app --reload --port 8000
```

Swagger docs: http://localhost:8000/docs

---

## RAG: Búsqueda Semántica

### 1. Generar Embeddings (Una sola vez)

**Endpoint:** `POST /api/busqueda/embeddings/generar`

```bash
curl -X POST "http://localhost:8000/api/busqueda/embeddings/generar"
```

**Respuesta:**
```json
{
  "status": "processing",
  "message": "Generación de embeddings iniciada en background"
}
```

Este proceso:
- Genera embeddings de ~4,000 dotaciones
- Usa modelo multilingüe `paraphrase-multilingual-MiniLM-L12-v2`
- Guarda cache en `services/api/rag/cache/dotaciones_embeddings.pkl`
- Tarda ~2-3 minutos

### 2. Búsqueda en Lenguaje Natural

**Endpoint:** `POST /api/busqueda/natural`

**Ejemplo 1: Búsqueda sin coordenadas (semántica pura)**

```bash
curl -X POST "http://localhost:8000/api/busqueda/natural" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cerca a hospitales y centros médicos"
  }'
```

**Respuesta:**
```json
{
  "query_original": "cerca a hospitales y centros médicos",
  "query_procesada": {
    "categorias": ["ips"],
    "radio_metros": 500,
    "cantidad_minima": null
  },
  "resultados": [
    {
      "id": 123,
      "nombre": "Hospital San Ignacio",
      "categoria": "ips",
      "latitud": 4.711,
      "longitud": -74.072,
      "similarity_score": 0.92
    },
    ...
  ],
  "total_encontrados": 47
}
```

**Ejemplo 2: Búsqueda con coordenadas (geoespacial)**

```bash
curl -X POST "http://localhost:8000/api/busqueda/natural" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cerca a colegios y universidades a 800 metros",
    "latitud": 4.711,
    "longitud": -74.072,
    "radio_max": 1000
  }'
```

### 3. Queries Soportadas

**Obtener ejemplos:**
```bash
curl -X GET "http://localhost:8000/api/busqueda/ejemplos"
```

**Ejemplos de queries naturales:**
- "cerca a colegios y hospitales"
- "zonas con universidades y parques a 500 metros"
- "sectores cerca de centros comerciales"
- "muy cerca a bibliotecas y teatros"
- "proximidad a plazas de mercado y farmacias"

**Categorías reconocidas:**
- Salud: hospital, clinica, centro medico, farmacia
- Educación: colegio, escuela, universidad, instituto
- Comercio: centro comercial, mall, plaza de mercado
- Cultura: biblioteca, teatro, auditorio
- Recreación: parque, zona verde, cancha

---

## AHP: Personalización de Pesos

### Flujo Completo

```
1. Usuario completa cuestionario AHP
   ↓
2. Sistema calcula pesos personalizados
   ↓
3. Pesos se aplican a cálculo de IDOT
   ↓
4. Usuario obtiene score personalizado según sus prioridades
```

### 1. Obtener Cuestionario

**Endpoint:** `GET /api/busqueda/ahp/cuestionario/{tipo}`

**Tipos disponibles:**
- `dotaciones`: Personalizar pesos de IDOT (salud, educación, comercio, cultura, recreación)
- `transporte`: Personalizar pesos de I_ACC (TransMilenio, SITP, vías)
- `indicadores`: Personalizar pesos de I_URB (I_ACC, I_SEG, I_HED, I_PNU)

**Ejemplo:**
```bash
curl -X GET "http://localhost:8000/api/busqueda/ahp/cuestionario/dotaciones"
```

**Respuesta:**
```json
{
  "tipo": "dotaciones",
  "total_preguntas": 10,
  "criterios": [
    {
      "id": "salud",
      "nombre": "Salud",
      "descripcion": "Cercanía a hospitales, clínicas y farmacias",
      "icono": "🏥"
    },
    ...
  ],
  "preguntas": [
    {
      "id": "salud_vs_educacion",
      "criterio_a_id": "salud",
      "criterio_a_nombre": "🏥 Salud",
      "criterio_b_id": "educacion",
      "criterio_b_nombre": "🎓 Educación",
      "pregunta": "¿Qué es más importante para ti: Salud o Educación?",
      "opciones": [
        {"valor": "9", "texto": "Salud es EXTREMADAMENTE más importante"},
        {"valor": "7", "texto": "Salud es MUY fuertemente más importante"},
        {"valor": "5", "texto": "Salud es FUERTEMENTE más importante"},
        {"valor": "3", "texto": "Salud es MODERADAMENTE más importante"},
        {"valor": "1", "texto": "Ambos tienen IGUAL importancia"},
        {"valor": "0.333", "texto": "Educación es MODERADAMENTE más importante"},
        ...
      ]
    },
    ...
  ],
  "escala_saaty": {
    "1": "Igual importancia",
    "3": "Moderadamente más importante",
    "5": "Fuertemente más importante",
    "7": "Muy fuertemente más importante",
    "9": "Extremadamente más importante"
  }
}
```

### 2. Usuario Responde Cuestionario

**Frontend debe recolectar respuestas:**

```javascript
// Ejemplo JavaScript
const respuestas = {
  "salud_vs_educacion": 5,      // Salud fuertemente más importante
  "salud_vs_comercio": 7,       // Salud muy fuertemente más importante
  "salud_vs_cultura": 9,        // Salud extremadamente más importante
  "salud_vs_recreacion": 5,
  "educacion_vs_comercio": 3,
  "educacion_vs_cultura": 5,
  "educacion_vs_recreacion": 3,
  "comercio_vs_cultura": 1,     // Igual importancia
  "comercio_vs_recreacion": 1,
  "cultura_vs_recreacion": 1
};
```

### 3. Calcular Pesos AHP

**Endpoint:** `POST /api/busqueda/ahp/calcular-pesos`

```bash
curl -X POST "http://localhost:8000/api/busqueda/ahp/calcular-pesos?tipo=dotaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "respuestas": {
      "salud_vs_educacion": 5,
      "salud_vs_comercio": 7,
      "salud_vs_cultura": 9,
      "salud_vs_recreacion": 5,
      "educacion_vs_comercio": 3,
      "educacion_vs_cultura": 5,
      "educacion_vs_recreacion": 3,
      "comercio_vs_cultura": 1,
      "comercio_vs_recreacion": 1,
      "cultura_vs_recreacion": 1
    }
  }'
```

**Respuesta:**
```json
{
  "tipo": "dotaciones",
  "pesos": {
    "salud": 0.5014,
    "educacion": 0.2362,
    "comercio": 0.1042,
    "cultura": 0.0791,
    "recreacion": 0.0791
  },
  "consistency_ratio": 0.0156,
  "is_consistent": true,
  "mensaje": "Pesos calculados exitosamente. Matriz consistente."
}
```

**Interpretación:**
- `salud`: 50.14% - El usuario prioriza fuertemente salud
- `educacion`: 23.62% - Segunda prioridad
- `consistency_ratio`: 0.0156 < 0.10 ✓ (matriz consistente)

### 4. Aplicar Pesos Personalizados

**Endpoint:** `POST /api/busqueda/ahp/idot-personalizado`

```bash
curl -X POST "http://localhost:8000/api/busqueda/ahp/idot-personalizado" \
  -H "Content-Type: application/json" \
  -d '{
    "latitud": 4.711,
    "longitud": -74.072,
    "pesos": {
      "salud": 0.5014,
      "educacion": 0.2362,
      "comercio": 0.1042,
      "cultura": 0.0791,
      "recreacion": 0.0791
    }
  }'
```

**Respuesta:**
```json
{
  "idot_personalizado": 4.35,
  "scores_por_categoria": {
    "salud": 5.0,
    "educacion": 4.0,
    "comercio": 3.0,
    "cultura": 5.0,
    "recreacion": 4.0
  },
  "dotaciones_cercanas": {
    "salud": 5,
    "educacion": 4,
    "comercio": 3,
    "cultura": 5,
    "recreacion": 4
  },
  "pesos_aplicados": {
    "salud": 0.5014,
    "educacion": 0.2362,
    "comercio": 0.1042,
    "cultura": 0.0791,
    "recreacion": 0.0791
  }
}
```

### 5. Comparar Perfiles AHP

**Endpoint:** `GET /api/busqueda/ahp/comparar-perfiles`

```bash
curl -X GET "http://localhost:8000/api/busqueda/ahp/comparar-perfiles?latitud=4.711&longitud=-74.072"
```

**Respuesta:**
```json
{
  "latitud": 4.711,
  "longitud": -74.072,
  "idot_por_perfil": {
    "equilibrado": 4.20,
    "familiar": 4.45,
    "urbano": 3.80,
    "deportivo": 4.10
  },
  "perfiles_disponibles": {
    "equilibrado": "Todas las dotaciones tienen igual importancia",
    "familiar": "Prioridad a salud y educación (ideal para familias)",
    "urbano": "Prioridad a comercio y cultura (vida urbana activa)",
    "deportivo": "Prioridad a recreación y deportes"
  }
}
```

---

## Casos de Uso End-to-End

### Caso 1: Usuario Busca Inmueble Personalizado

**Flujo completo:**

```javascript
// 1. Usuario completa cuestionario AHP
const cuestionario = await fetch('http://localhost:8000/api/busqueda/ahp/cuestionario/dotaciones');
const { preguntas } = await cuestionario.json();

// 2. Usuario responde (frontend)
const respuestas = {
  "salud_vs_educacion": 5,
  // ... resto de respuestas
};

// 3. Calcular pesos personalizados
const pesosResponse = await fetch('http://localhost:8000/api/busqueda/ahp/calcular-pesos?tipo=dotaciones', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ respuestas })
});
const { pesos } = await pesosResponse.json();

// 4. Búsqueda inteligente con pesos personalizados
const resultados = await fetch('http://localhost:8000/api/busqueda/inteligente', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: "cerca a colegios y hospitales",
    pesos_ahp: pesos,
    iurb_min: 4.0,
    precio_max: 500000000,
    limit: 20
  })
});

const inmuebles = await resultados.json();
console.log(`Encontrados: ${inmuebles.total} inmuebles`);
inmuebles.resultados.forEach(inm => {
  console.log(`${inm.ubicacion}: I_URB=${inm.iurb}, IDOT personalizado=${inm.idot_personalizado}`);
});
```

### Caso 2: Valorar Propiedad del Usuario con Preferencias

```javascript
// Usuario proporciona: lat/lon de su casa + características
const estudio = await fetch('http://localhost:8000/api/iurb/estudio-individual', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    latitud: 4.711,
    longitud: -74.072,
    tipo_inmueble: "Apartamento",
    area: 85.0,
    habitaciones: 3,
    banos: 2
  })
});

const informe = await estudio.json();

console.log("Valoración de mercado:", informe.valoracion.precio_estimado);
console.log("I_URB estándar:", informe.indicadores.iurb);

// Ahora con preferencias del usuario
const idotCustom = await fetch('http://localhost:8000/api/busqueda/ahp/idot-personalizado', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    latitud: 4.711,
    longitud: -74.072,
    pesos: pesos  // Obtenidos del cuestionario
  })
});

const { idot_personalizado } = await idotCustom.json();
console.log("IDOT según TUS preferencias:", idot_personalizado);
```

### Caso 3: Explorar Zona Antes de Comprar

```python
import requests

# 1. Usuario ingresa dirección
direccion = "Calle 100 #15-20, Bogotá"
# ... geocoding para obtener lat/lon ...
lat, lon = 4.711, -74.072

# 2. Comparar con diferentes perfiles
resp = requests.get(
    f"http://localhost:8000/api/busqueda/ahp/comparar-perfiles",
    params={"latitud": lat, "longitud": lon}
)
perfiles = resp.json()

print("IDOT según diferentes perfiles:")
for perfil, score in perfiles['idot_por_perfil'].items():
    print(f"  {perfil}: {score}")

# 3. Búsqueda natural de dotaciones
resp = requests.post(
    "http://localhost:8000/api/busqueda/natural",
    json={
        "query": "muy cerca a hospitales y colegios",
        "latitud": lat,
        "longitud": lon,
        "radio_max": 500
    }
)
dotaciones = resp.json()

print(f"\nDotaciones cercanas: {dotaciones['total_encontrados']}")
for dot in dotaciones['resultados'][:5]:
    print(f"  {dot['nombre']} ({dot['categoria']}): {dot['distancia_m']:.0f}m")
```

---

## Integración con LangChain (Opcional)

Para queries complejas en lenguaje natural usando LLM.

### Setup

```bash
pip install langchain openai
export OPENAI_API_KEY="sk-..."
```

### Uso

```python
from services.api.rag.langchain_integration import setup_langchain_agent

# Configurar agente
agent = setup_langchain_agent(
    db_url="postgresql://user:pass@localhost:5432/postgres",
    openai_api_key="sk-...",
    verbose=True
)

# Query compleja en lenguaje natural
result = agent.run("""
    Encuentra los 10 mejores inmuebles que:
    - Estén cerca de universidades (menos de 800m)
    - Tengan I_URB mayor a 4.0
    - Precio menor a 500 millones
    - Ordenados por mejor ratio precio/I_URB
""")

print(result)
```

**Queries soportadas:**
- "Inmuebles con alto potencial de desarrollo en zonas seguras"
- "Apartamentos cerca de TransMilenio con buena accesibilidad"
- "Oportunidades de inversión en zonas de renovación urbana"
- "Propiedades con buen I_HED y cerca de parques"

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────┐
│           Frontend (Usuario)                 │
└────────────┬────────────────────────────────┘
             │
             ├─── Búsqueda Natural ("cerca a colegios")
             ├─── Cuestionario AHP (preferencias)
             └─── Estudio Individual (valoración)
             │
             ▼
┌─────────────────────────────────────────────┐
│        FastAPI Backend (main.py)             │
│                                              │
│  ┌──────────────┐  ┌──────────────┐        │
│  │ RAG Module   │  │  AHP Module  │        │
│  ├──────────────┤  ├──────────────┤        │
│  │ Embeddings   │  │ Questionnaire│        │
│  │ QueryProc    │  │ Calculator   │        │
│  │ Semantic     │  │ Dotaciones   │        │
│  └──────────────┘  └──────────────┘        │
│           │               │                  │
└───────────┼───────────────┼──────────────────┘
            │               │
            ▼               ▼
    ┌─────────────────────────────┐
    │   PostgreSQL + PostGIS       │
    │                              │
    │  - inmueble (iurb, idot)    │
    │  - dotaciones_poi           │
    │  - pot_* (POT 555)          │
    │  - analisis_oportunidades   │
    └─────────────────────────────┘
```

---

## Performance

| Endpoint | Tiempo Promedio | Notas |
|----------|----------------|-------|
| `/busqueda/natural` (sin coords) | ~150ms | Búsqueda semántica en cache |
| `/busqueda/natural` (con coords) | ~80ms | Query geoespacial con índices |
| `/ahp/cuestionario` | ~10ms | Generación de preguntas |
| `/ahp/calcular-pesos` | ~5ms | Cálculo de eigenvectors |
| `/ahp/idot-personalizado` | ~200ms | Queries espaciales + cálculo |
| `/busqueda/inteligente` | ~300ms | Query completa + AHP |
| `/embeddings/generar` | ~2-3 min | Solo una vez (background) |

---

## Próximos Pasos

1. **Cache de pesos AHP**: Guardar perfiles de usuarios para reutilizar
2. **Fine-tuning de embeddings**: Entrenar modelo específico para dotaciones colombianas
3. **Visualización**: Frontend con mapa interactivo mostrando dotaciones + scores
4. **A/B Testing**: Comparar rankings con/sin personalización
5. **Feedback loop**: Aprender de búsquedas exitosas para mejorar rankings

---

## Troubleshooting

### Error: "sentence-transformers no instalado"
```bash
pip install sentence-transformers
```

### Error: "Embeddings cache no encontrado"
Ejecutar primero:
```bash
curl -X POST "http://localhost:8000/api/busqueda/embeddings/generar"
```

### Error: "Matriz inconsistente (CR >= 0.10)"
El usuario dio respuestas contradictorias. Pedir que revise sus comparaciones.

Ejemplo de inconsistencia:
- Dice: A > B (fuertemente)
- Dice: B > C (fuertemente)
- Dice: C > A (fuertemente)
→ Contradicción lógica

### Slow performance en búsquedas
Verificar índices espaciales:
```sql
CREATE INDEX IF NOT EXISTS idx_dotaciones_geom ON iug.dotaciones_poi USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_inmueble_geom ON iug.inmueble USING GIST (geom);
```

---

## Contacto y Soporte

Para preguntas o issues, consultar:
- Swagger Docs: http://localhost:8000/docs
- Documentación adicional: `/services/api/API_IURB.md`
