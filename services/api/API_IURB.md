# API I_URB - Documentación

Endpoints para el Indicador Urbanístico Global (I_URB) y análisis de oportunidades inmobiliarias.

---

## Base URL

```
http://localhost:8000/api/iurb
```

---

## Endpoints

### 1. Obtener I_URB de un Inmueble

**GET** `/api/iurb/{id_inmueble}`

Obtiene I_URB e indicadores completos de un inmueble existente.

**Parámetros:**
- `id_inmueble` (path): ID del inmueble

**Respuesta:**
```json
{
  "id_inmueble": 123,
  "ubicacion": "Calle 100 #15-20, Bogotá",
  "tipo_inmueble": "Apartamento",
  "precio": 450000000,
  "area": 85.0,
  "iurb": 4.2,
  "iacc": 4.5,
  "iseg": 3.8,
  "ihed": 4.3,
  "ipnu": 4.1,
  "precio_por_iurb": 107142857.14,
  "precio_m2": 5294117.65,
  "categoria_oportunidad": "Buena Oportunidad",
  "interpretacion": "Muy Bueno"
}
```

**Ejemplo cURL:**
```bash
curl -X GET "http://localhost:8000/api/iurb/123"
```

---

### 2. Calcular I_URB para Coordenadas

**POST** `/api/iurb/calcular`

Calcula I_URB para coordenadas específicas (inmueble nuevo).

**Body:**
```json
{
  "latitud": 4.711,
  "longitud": -74.072,
  "tipo_inmueble": "Apartamento"
}
```

**Respuesta:**
```json
{
  "coordenadas": {
    "latitud": 4.711,
    "longitud": -74.072
  },
  "tipo_inmueble": "Apartamento",
  "indicadores": {
    "iurb": 4.1,
    "iacc": 4.3,
    "iseg": 3.9,
    "ihed": 4.2,
    "ipnu": 4.0
  },
  "interpretacion": "Muy Bueno",
  "pot": {
    "tratamiento": "Consolidación",
    "edificabilidad": "3",
    "area_actividad": "AAPRSU",
    "area_actividad_nombre": "Área de Proximidad Receptora de Soporte Urbano"
  }
}
```

**Ejemplo cURL:**
```bash
curl -X POST "http://localhost:8000/api/iurb/calcular" \
  -H "Content-Type: application/json" \
  -d '{
    "latitud": 4.711,
    "longitud": -74.072,
    "tipo_inmueble": "Apartamento"
  }'
```

---

### 3. Buscar Oportunidades

**GET** `/api/iurb/oportunidades`

Busca mejores oportunidades basadas en ratio precio/I_URB.

**Parámetros Query:**
- `tipo_inmueble` (opcional): Filtrar por tipo (Apartamento, Casa, etc.)
- `iurb_min` (default 3.5): I_URB mínimo requerido
- `precio_max` (opcional): Precio máximo
- `limit` (default 20): Número de resultados

**Respuesta:**
```json
[
  {
    "id_inmueble": 456,
    "ubicacion": "Carrera 7 #80-45, Bogotá",
    "tipo_inmueble": "Apartamento",
    "precio": 380000000,
    "iurb": 4.3,
    "precio_por_iurb": 88372093.02,
    "categoria_oportunidad": "Excelente Oportunidad",
    "percentil_ratio": 12.5
  },
  {
    "id_inmueble": 789,
    "ubicacion": "Calle 127 #52-10, Bogotá",
    "tipo_inmueble": "Apartamento",
    "precio": 420000000,
    "iurb": 4.5,
    "precio_por_iurb": 93333333.33,
    "categoria_oportunidad": "Muy Buena Oportunidad",
    "percentil_ratio": 18.7
  }
]
```

**Ejemplos cURL:**

```bash
# Todas las oportunidades
curl -X GET "http://localhost:8000/api/iurb/oportunidades?limit=10"

# Solo apartamentos con I_URB >= 4.0
curl -X GET "http://localhost:8000/api/iurb/oportunidades?tipo_inmueble=Apartamento&iurb_min=4.0&limit=20"

# Con precio máximo
curl -X GET "http://localhost:8000/api/iurb/oportunidades?precio_max=500000000&iurb_min=3.5"
```

---

### 4. Estudio Individual Completo

**POST** `/api/iurb/estudio-individual`

Genera informe completo para estudio individual (valoración + indicadores).

**Body:**
```json
{
  "latitud": 4.711,
  "longitud": -74.072,
  "tipo_inmueble": "Apartamento",
  "area": 85.0,
  "habitaciones": 3,
  "banos": 2,
  "estrato": 4
}
```

**Respuesta:**
```json
{
  "resumen": {
    "tipo_inmueble": "Apartamento",
    "area": 85.0,
    "habitaciones": 3,
    "banos": 2
  },
  "valoracion": {
    "precio_estimado": 465000000,
    "precio_m2_estimado": 5470588,
    "metodo": "Regresión basada en inmuebles similares"
  },
  "indicadores": {
    "iurb": 4.1,
    "iacc": 4.3,
    "iseg": 3.9,
    "ihed": 4.2,
    "ipnu": 4.0,
    "interpretacion": "Muy Bueno"
  },
  "comparacion_mercado": {
    "inmuebles_similares": 47,
    "precio_promedio": 478000000,
    "precio_mediana": 460000000,
    "ratio_promedio": 116585365.85
  },
  "recomendaciones": [
    "Muy buena ubicación con alto potencial",
    "Alto potencial de desarrollo según POT"
  ]
}
```

**Ejemplo cURL:**
```bash
curl -X POST "http://localhost:8000/api/iurb/estudio-individual" \
  -H "Content-Type: application/json" \
  -d '{
    "latitud": 4.711,
    "longitud": -74.072,
    "tipo_inmueble": "Apartamento",
    "area": 85.0,
    "habitaciones": 3,
    "banos": 2,
    "estrato": 4
  }'
```

---

### 5. Estadísticas Generales

**GET** `/api/iurb/estadisticas`

Estadísticas generales de I_URB en toda la base de datos.

**Respuesta:**
```json
{
  "total_inmuebles": 4491,
  "con_iurb": 3066,
  "cobertura_pct": 68.3,
  "promedio": 3.85,
  "mediana": 3.90,
  "desviacion": 0.52,
  "minimo": 1.60,
  "maximo": 5.00
}
```

**Ejemplo cURL:**
```bash
curl -X GET "http://localhost:8000/api/iurb/estadisticas"
```

---

### 6. Recalcular I_URB Masivo

**POST** `/api/iurb/recalcular`

Recalcula I_URB para todos los inmuebles (operación pesada, se ejecuta en background).

**Respuesta:**
```json
{
  "status": "processing",
  "message": "Recálculo de I_URB iniciado en background"
}
```

**Ejemplo cURL:**
```bash
curl -X POST "http://localhost:8000/api/iurb/recalcular"
```

---

## Casos de Uso

### Caso 1: Usuario Quiere Valorar su Propiedad

**Flujo:**

1. Usuario ingresa dirección → Frontend obtiene lat/lon (Geocoding API)
2. Usuario ingresa características (área, habitaciones, baños)
3. Frontend llama a `/api/iurb/estudio-individual`
4. Usuario recibe:
   - Valor estimado de mercado
   - Score I_URB de su ubicación
   - Comparación con inmuebles similares
   - Recomendaciones

**Código JavaScript:**
```javascript
const response = await fetch('http://localhost:8000/api/iurb/estudio-individual', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    latitud: 4.711,
    longitud: -74.072,
    tipo_inmueble: 'Apartamento',
    area: 85.0,
    habitaciones: 3,
    banos: 2,
    estrato: 4
  })
});

const informe = await response.json();
console.log(`Precio estimado: $${informe.valoracion.precio_estimado}`);
console.log(`I_URB: ${informe.indicadores.iurb} (${informe.indicadores.interpretacion})`);
```

---

### Caso 2: Buscar Mejores Oportunidades de Inversión

**Estrategia:** Buscar inmuebles con bajo precio/I_URB (alta calidad, precio razonable).

**Código JavaScript:**
```javascript
const response = await fetch(
  'http://localhost:8000/api/iurb/oportunidades?tipo_inmueble=Apartamento&iurb_min=4.0&limit=50'
);

const oportunidades = await response.json();

// Ordenar por percentil (mejores primero)
oportunidades.sort((a, b) => a.percentil_ratio - b.percentil_ratio);

// Mostrar top 10
oportunidades.slice(0, 10).forEach(op => {
  console.log(`${op.ubicacion}: $${op.precio} | I_URB: ${op.iurb} | Ratio: ${op.precio_por_iurb}`);
});
```

---

### Caso 3: Mapa Interactivo de Calidad Urbana

**Objetivo:** Mostrar I_URB en mapa para exploración geográfica.

**Código JavaScript (con Leaflet/Mapbox):**
```javascript
// Obtener todos los inmuebles con I_URB
const response = await fetch('http://localhost:8000/api/inmueble?tiene_iurb=true&limit=1000');
const inmuebles = await response.json();

// Renderizar en mapa con color según I_URB
inmuebles.forEach(inmueble => {
  const color = getColorByIURB(inmueble.iurb); // Verde: alto, Rojo: bajo

  L.circleMarker([inmueble.latitud, inmueble.longitud], {
    radius: 6,
    fillColor: color,
    color: '#000',
    weight: 1,
    opacity: 1,
    fillOpacity: 0.8
  })
  .bindPopup(`
    <strong>${inmueble.ubicacion}</strong><br>
    I_URB: ${inmueble.iurb}<br>
    Precio: $${inmueble.precio.toLocaleString()}<br>
    Ratio: $${inmueble.precio_por_iurb.toLocaleString()}
  `)
  .addTo(map);
});

function getColorByIURB(iurb) {
  return iurb >= 4.5 ? '#2ECC40' : // Verde oscuro
         iurb >= 4.0 ? '#3D9970' : // Verde
         iurb >= 3.5 ? '#FFDC00' : // Amarillo
         iurb >= 3.0 ? '#FF851B' : // Naranja
                       '#FF4136';  // Rojo
}
```

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000/api/iurb"

# 1. Calcular I_URB para una dirección
response = requests.post(f"{BASE_URL}/calcular", json={
    "latitud": 4.711,
    "longitud": -74.072,
    "tipo_inmueble": "Apartamento"
})
resultado = response.json()
print(f"I_URB: {resultado['indicadores']['iurb']}")

# 2. Buscar oportunidades
response = requests.get(f"{BASE_URL}/oportunidades", params={
    "tipo_inmueble": "Apartamento",
    "iurb_min": 4.0,
    "limit": 20
})
oportunidades = response.json()

for op in oportunidades[:5]:
    print(f"{op['ubicacion']}: ${op['precio']:,.0f} | I_URB: {op['iurb']}")

# 3. Estudio individual
response = requests.post(f"{BASE_URL}/estudio-individual", json={
    "latitud": 4.711,
    "longitud": -74.072,
    "tipo_inmueble": "Apartamento",
    "area": 85.0,
    "habitaciones": 3,
    "banos": 2
})
informe = response.json()

print(f"\nValor estimado: ${informe['valoracion']['precio_estimado']:,.0f}")
print(f"I_URB: {informe['indicadores']['iurb']} ({informe['indicadores']['interpretacion']})")
print("\nRecomendaciones:")
for rec in informe['recomendaciones']:
    print(f"- {rec}")
```

---

## Swagger/OpenAPI

La documentación interactiva está disponible en:

```
http://localhost:8000/docs
```

Permite probar todos los endpoints directamente desde el navegador.

---

## Errores Comunes

### 404 - Inmueble no encontrado
```json
{
  "detail": "Inmueble 999999 no encontrado"
}
```

### 422 - Validación fallida
```json
{
  "detail": [
    {
      "loc": ["body", "latitud"],
      "msg": "ensure this value is greater than or equal to -90",
      "type": "value_error.number.not_ge"
    }
  ]
}
```

---

## Performance

- **GET /api/iurb/{id_inmueble}**: ~50ms (consulta simple con índices)
- **POST /api/iurb/calcular**: ~200ms (cálculos espaciales)
- **GET /api/iurb/oportunidades**: ~100ms (vista materializada)
- **POST /api/iurb/estudio-individual**: ~300ms (regresión + cálculos)
- **POST /api/iurb/recalcular**: Background (varios minutos para miles de inmuebles)

---

## Notas de Implementación

1. **CORS:** Configurado para aceptar todas las origins (`*`). En producción, especificar dominios permitidos.

2. **Autenticación:** No implementada aún. Agregar JWT o API keys según necesidad.

3. **Rate Limiting:** No implementado. Considerar para producción.

4. **Cache:** Los cálculos se hacen en tiempo real. Considerar cachear resultados frecuentes.

5. **Paginación:** `/oportunidades` usa limit. Implementar cursor-based pagination para grandes datasets.
