# Indicador Urbanístico Global (I_URB)

## Descripción
El **Indicador Urbanístico Global (I_URB)** es una **suma ponderada** de todos los indicadores individuales del sistema, proporcionando una calificación integral de la calidad y potencial de cada ubicación inmobiliaria.

---

## 🧮 Fórmula

```
I_URB = (w₁ × I_ACC) + (w₂ × I_SEG) + (w₃ × I_HED) + (w₄ × I_PNU)
```

### Pesos por Defecto (Equilibrados)

```python
w₁ = 0.25  # I_ACC - Accesibilidad (25%)
w₂ = 0.20  # I_SEG - Seguridad (20%)
w₃ = 0.25  # I_HED - Calidad Hedónica (25%)
w₄ = 0.30  # I_PNU - Potencial Normativo (30%)
```

**Resultado**: Escala 0-5, donde 5 = ubicación premium con máximo potencial integral.

---

## 📊 Componentes

| Indicador | Sigla | Peso | Descripción |
|-----------|-------|------|-------------|
| **Accesibilidad** | I_ACC | 25% | Proximidad a transporte público (SITP, TransMilenio) |
| **Seguridad** | I_SEG | 20% | Seguridad objetiva basada en criminalidad |
| **Calidad Hedónica** | I_HED | 25% | Calidad estructural y dotaciones urbanas |
| **Potencial Normativo** | I_PNU | 30% | Potencial de desarrollo según POT 555 |

### Composición de I_HED
```
I_HED = I_Dim + I_Dot

- I_Dim: Dimensión (calidad estructural del inmueble)
- I_Dot: Dotaciones (proximidad a servicios urbanos)
```

---

## ⚖️ Esquemas de Pesos Alternativos

### 1. Pesos Iguales (Democrático)
```python
I_ACC = 25%  |  I_SEG = 25%  |  I_HED = 25%  |  I_PNU = 25%
```
**Uso:** Análisis exploratorio sin sesgo hacia ningún factor.

### 2. Perfil Inversión (Desarrollo Inmobiliario)
```python
I_ACC = 20%  |  I_SEG = 15%  |  I_HED = 20%  |  I_PNU = 45%
```
**Uso:** Identificar oportunidades de desarrollo con alto potencial normativo.

### 3. Perfil Residencial (Calidad de Vida)
```python
I_ACC = 30%  |  I_SEG = 30%  |  I_HED = 30%  |  I_PNU = 10%
```
**Uso:** Priorizar accesibilidad, seguridad y calidad para usuarios finales.

---

## 🔧 Implementación

### Cálculo Masivo
```python
from services.indicators.global_urban import calculate_iurb_bulk
import psycopg2

conn = psycopg2.connect(...)
n_actualizados = calculate_iurb_bulk(conn)
print(f"Calculado I_URB para {n_actualizados} inmuebles")
```

### Cálculo Individual
```python
from services.indicators.global_urban import calculate_iurb

iurb = calculate_iurb(
    iacc=4.2,
    iseg=3.8,
    ihed=4.5,
    ipnu=3.9
)
# Resultado: iurb ≈ 4.1
```

### Obtener I_URB + Interpretación
```python
from services.indicators.global_urban import get_iurb_for_inmueble

result = get_iurb_for_inmueble(id_inmueble=123, conn=conn)
print(result)
# {
#     'iurb': 4.1,
#     'iacc': 4.2,
#     'iseg': 3.8,
#     'ihed': 4.5,
#     'ipnu': 3.9,
#     'interpretation': {
#         'categoria': 'muy_bueno',
#         'label': 'Muy Bueno',
#         'descripcion': '...'
#     },
#     'alerts': []
# }
```

---

## 📈 Interpretación

| I_URB | Categoría | Descripción | Recomendación |
|-------|-----------|-------------|---------------|
| **4.5 - 5.0** | Excelente | Ubicación premium. Alto potencial de desarrollo y calidad de vida. | Inversión prioritaria. ROI alto esperado. |
| **4.0 - 4.5** | Muy Bueno | Ubicación muy atractiva. Buen balance entre desarrollo y calidad. | Muy recomendado. Valorización esperada. |
| **3.5 - 4.0** | Bueno | Ubicación sólida. Potencial de valorización medio-alto. | Recomendado. Inversión segura. |
| **3.0 - 3.5** | Regular | Ubicación promedio. Algunas limitaciones. | Evaluar caso por caso. |
| **2.5 - 3.0** | Por Debajo del Promedio | Ubicación con restricciones. Potencial limitado. | Inversión conservadora. |
| **2.0 - 2.5** | Deficiente | Ubicación poco atractiva. Múltiples limitaciones. | No recomendado. |
| **< 2.0** | Muy Deficiente | Ubicación no recomendada. Restricciones severas. | Evitar. |

---

## 🚨 Sistema de Alertas

El sistema genera alertas automáticas cuando algún indicador está por debajo de umbrales críticos:

| Alerta | Umbral | Mensaje |
|--------|--------|---------|
| Seguridad Baja | I_SEG < 2.5 | Zona con seguridad por debajo del promedio |
| Accesibilidad Baja | I_ACC < 2.0 | Accesibilidad limitada a transporte público |
| Potencial Muy Bajo | I_PNU < 2.0 | Potencial normativo muy bajo (restricciones POT) |

**Ejemplo:**
```python
result = get_iurb_for_inmueble(456, conn)
print(result['alerts'])
# ['Zona con seguridad por debajo del promedio']
```

---

## 🔄 Actualización

### Automática (Recomendado)
Crear trigger SQL para actualizar I_URB cuando cambie algún sub-indicador:

```sql
CREATE OR REPLACE FUNCTION iug.trg_actualizar_iurb()
RETURNS TRIGGER AS $$
BEGIN
    NEW.iurb = (
        COALESCE(NEW.iacc * 0.25, 0) +
        COALESCE(NEW.iseg * 0.20, 0) +
        COALESCE(NEW.ihed * 0.25, 0) +
        COALESCE(NEW.ipnu * 0.30, 0)
    ) / (
        (CASE WHEN NEW.iacc IS NOT NULL THEN 0.25 ELSE 0 END) +
        (CASE WHEN NEW.iseg IS NOT NULL THEN 0.20 ELSE 0 END) +
        (CASE WHEN NEW.ihed IS NOT NULL THEN 0.25 ELSE 0 END) +
        (CASE WHEN NEW.ipnu IS NOT NULL THEN 0.30 ELSE 0 END)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inmueble_iurb
BEFORE INSERT OR UPDATE OF iacc, iseg, ihed, ipnu
ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trg_actualizar_iurb();
```

### Manual
```python
from services.indicators.global_urban import calculate_iurb_bulk

conn = psycopg2.connect(...)
n = calculate_iurb_bulk(conn)
print(f"{n} inmuebles actualizados")
```

---

## 📊 Análisis y Consultas

### Estadísticas Globales
```python
from services.indicators.global_urban import analyze_iurb_distribution

stats = analyze_iurb_distribution(conn)
print(stats['general'])
# {
#     'total_inmuebles': 4491,
#     'con_iurb': 3066,
#     'cobertura_pct': 68.3,
#     'promedio': 3.85,
#     'mediana': 3.90,
#     ...
# }
```

### Top Inmuebles
```python
from services.indicators.global_urban import get_top_inmuebles

top10 = get_top_inmuebles(conn, limit=10, order_by='iurb')
for inmueble in top10:
    print(f"{inmueble['ubicacion']}: I_URB = {inmueble['iurb']}")
```

### Consultas SQL

#### Inmuebles con I_URB excelente
```sql
SELECT
    id_inmueble,
    ubicacion,
    tipo_inmueble,
    precio,
    iurb,
    iacc, iseg, ihed, ipnu
FROM iug.inmueble
WHERE iurb >= 4.5
ORDER BY iurb DESC, precio ASC
LIMIT 20;
```

#### Distribución por categoría
```sql
SELECT
    CASE
        WHEN iurb >= 4.5 THEN 'Excelente'
        WHEN iurb >= 4.0 THEN 'Muy Bueno'
        WHEN iurb >= 3.5 THEN 'Bueno'
        WHEN iurb >= 3.0 THEN 'Regular'
        ELSE 'Por Debajo del Promedio'
    END as categoria,
    COUNT(*) as cantidad,
    ROUND(AVG(precio)::numeric, 0) as precio_promedio,
    ROUND(AVG(iurb)::numeric, 2) as iurb_promedio
FROM iug.inmueble
WHERE iurb IS NOT NULL
GROUP BY categoria
ORDER BY MIN(iurb) DESC;
```

#### Inmuebles con desequilibrios (un indicador muy bajo)
```sql
SELECT
    id_inmueble,
    ubicacion,
    iurb,
    iacc, iseg, ihed, ipnu,
    CASE
        WHEN iseg < 2.5 THEN 'Seguridad baja'
        WHEN iacc < 2.0 THEN 'Accesibilidad baja'
        WHEN ipnu < 2.0 THEN 'Potencial muy bajo'
        ELSE 'OK'
    END as alerta
FROM iug.inmueble
WHERE iurb IS NOT NULL
  AND (iseg < 2.5 OR iacc < 2.0 OR ipnu < 2.0)
ORDER BY iurb DESC;
```

#### Comparar inmuebles por perfil
```sql
-- Perfil Inversión vs Perfil Residencial
SELECT
    id_inmueble,
    ubicacion,
    -- Perfil por defecto (equilibrado)
    iurb as iurb_equilibrado,
    -- Perfil inversión (mayor peso a I_PNU)
    (iacc * 0.20 + iseg * 0.15 + ihed * 0.20 + ipnu * 0.45) as iurb_inversion,
    -- Perfil residencial (mayor peso a accesibilidad/seguridad)
    (iacc * 0.30 + iseg * 0.30 + ihed * 0.30 + ipnu * 0.10) as iurb_residencial
FROM iug.inmueble
WHERE iacc IS NOT NULL AND iseg IS NOT NULL
  AND ihed IS NOT NULL AND ipnu IS NOT NULL
ORDER BY iurb_inversion DESC
LIMIT 20;
```

---

## 🗂️ Archivos Relacionados

```
services/indicators/
├── global_urban/
│   ├── README.md           # Este archivo
│   ├── calculator.py       # Funciones de cálculo
│   ├── config.py           # Pesos y configuración
│   └── __init__.py         # Exports

├── transport/              # I_ACC
├── security/               # I_SEG
├── hedonic/                # I_HED
└── normative/              # I_PNU
```

---

## 🔍 Casos de Uso

### 1. Búsqueda de Oportunidades de Inversión
```sql
-- Inmuebles con alto I_URB y precio por debajo de la mediana
WITH mediana_precio AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY precio) as p50
    FROM iug.inmueble
    WHERE precio IS NOT NULL
)
SELECT i.id_inmueble, i.ubicacion, i.precio, i.iurb,
       i.iacc, i.iseg, i.ihed, i.ipnu
FROM iug.inmueble i, mediana_precio m
WHERE i.iurb >= 4.0
  AND i.precio < m.p50
ORDER BY i.iurb DESC, i.precio ASC
LIMIT 50;
```

### 2. Perfilamiento de Portafolio
```sql
-- Distribución del portafolio por calidad
SELECT
    CASE
        WHEN iurb >= 4.5 THEN 'Premium'
        WHEN iurb >= 4.0 THEN 'Alto'
        WHEN iurb >= 3.5 THEN 'Medio-Alto'
        WHEN iurb >= 3.0 THEN 'Medio'
        ELSE 'Bajo'
    END as segmento,
    COUNT(*) as cantidad,
    ROUND(AVG(precio)::numeric, 0) as precio_promedio,
    SUM(precio) as valor_total_segmento
FROM iug.inmueble
WHERE iurb IS NOT NULL AND precio IS NOT NULL
GROUP BY segmento
ORDER BY MIN(iurb) DESC;
```

### 3. Análisis de Sensibilidad a Pesos
```python
# Comparar rankings con diferentes esquemas de pesos
from services.indicators.global_urban import calculate_iurb
from services.indicators.global_urban.config import (
    PESOS_INDICADORES,
    PESOS_INVERSION,
    PESOS_RESIDENCIAL
)

inmuebles = [
    {'iacc': 4.5, 'iseg': 3.0, 'ihed': 3.5, 'ipnu': 4.8},
    {'iacc': 3.0, 'iseg': 4.5, 'ihed': 4.2, 'ipnu': 2.5}
]

for i, data in enumerate(inmuebles):
    print(f"\nInmueble {i+1}:")
    print(f"  Equilibrado: {calculate_iurb(**data, pesos=PESOS_INDICADORES):.2f}")
    print(f"  Inversión:   {calculate_iurb(**data, pesos=PESOS_INVERSION):.2f}")
    print(f"  Residencial: {calculate_iurb(**data, pesos=PESOS_RESIDENCIAL):.2f}")
```

---

## 📚 Referencias

- [I_ACC - Indicador de Transporte](../transport/README.md)
- [I_SEG - Indicador de Seguridad](../security/README.md)
- [I_HED - Indicador Hedónico](../hedonic/README.md)
- [I_PNU - Indicador Normativo](../normative/README.md)

---

## ⚠️ Limitaciones

1. **Cobertura**: I_URB solo puede calcularse para inmuebles con al menos 2 indicadores disponibles.
2. **Geografía**: I_PNU solo aplica para Bogotá (POT 555).
3. **Actualización**: Cambiar pesos requiere recalcular todos los I_URB.
4. **Subjetividad**: Los pesos reflejan prioridades que pueden variar según el usuario.

---

## 🚀 Próximos Pasos

1. **Machine Learning**: Ajustar pesos automáticamente según correlación con precios de mercado.
2. **Segmentación**: Pesos diferentes por tipo de inmueble (casa vs apartamento).
3. **Temporal**: Analizar evolución de I_URB en el tiempo.
4. **Geoespacial**: Mapas de calor con I_URB para análisis territorial.
