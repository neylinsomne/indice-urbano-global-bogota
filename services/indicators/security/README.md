# Indicador de Seguridad (I_SEG)

## Descripción
Mide la **seguridad objetiva** combinando:
- Criminalidad por sector policial (ponderada con AHP)
- Proximidad a CAI (Comandos de Atención Inmediata)

---

## 📊 Tablas en Base de Datos

| Tabla | Descripción | Registros |
|-------|-------------|-----------|
| `iug.sectores_policia` | Sectores con estadísticas de crimen | ~20 sectores |
| `iug.cai` | Comandos de Atención Inmediata | ~300 |
| `iug.ahp_pesos_crimen` | Pesos AHP para tipos de crimen | 4 tipos |
| `iug.indicador_seguridad_raw` | Scores por inmueble | N inmuebles |
| `iug.indicador_seguridad_final` | Vista materializada 0-5 | N inmuebles |

---

## 🧮 Fórmula

### Componente 1: Score de Crimen (AHP)
```
Score_Crimen = Σ (w_i × crimen_i)

Donde:
- w_i: Peso AHP del tipo de crimen i
- crimen_i: Tasa normalizada del crimen i en el sector

Pesos AHP (calculados con ahp_weights.py):
- Homicidios: 0.50
- Delitos sexuales: 0.25
- Hurto personas: 0.15
- Otros delitos: 0.10
```

### Componente 2: Proximidad CAI
```
Score_CAI = 1 / (distancia_metros_al_cai_mas_cercano + 100)
```

### Score Final
```
I_SEG_raw = 0.70 × Score_Crimen + 0.30 × Score_CAI
```

### Normalización
```sql
I_SEG_normalizado = 5.0 × PERCENT_RANK() OVER (
    PARTITION BY tipo_inmueble 
    ORDER BY I_SEG_raw
)
```

---

## 📏 Distancias y Radios

| Elemento | Radio/Parámetro |
|----------|-----------------|
| **Sector Policial** | Asignación por geometría (ST_Contains) |
| **CAI más cercano** | Sin límite (se usa el más cercano) |
| **Peso Crimen** | 70% |
| **Peso CAI** | 30% |

---

## 🔧 Scripts y Funciones

### Carga de Datos (Una sola vez)
```sql
-- Sectores policiales y CAI se cargan vía migraciones
-- Ver: services/database/migrations/V16__security_indicator.sql
```

### Entrenamiento AHP (Mensual/Trimestral)
```python
# services/indicators/security/ahp_weights.py
# Calcula pesos AHP basados en matriz de comparación Saaty
python ahp_weights.py
```

### Funciones SQL
```sql
-- Calcula score de seguridad
iug.calcular_score_seguridad(geom)

-- Trigger automático
CREATE TRIGGER trg_inmueble_seguridad
AFTER INSERT OR UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.trg_calcular_seguridad();
```

---

## 🔄 Actualización

### Automática
- ✅ **INSERT/UPDATE individual**: Trigger calcula I_SEG
- ✅ **Batch scraping**: Orquestador refresca vista

### Manual (Actualizar estadísticas crimen)
```sql
-- 1. Actualizar datos de criminalidad en sectores_policia
UPDATE iug.sectores_policia SET
    homicidios = X,
    delitos_sexuales = Y,
    hurto_personas = Z
WHERE id = sector_id;

-- 2. Recalcular AHP
python services/indicators/security/ahp_weights.py

-- 3. Recalcular scores
SELECT iug.recalcular_seguridad_masivo();

-- 4. Refresh vista
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_seguridad_final;
```

---

## 📈 Interpretación

| I_SEG | Interpretación |
|-------|----------------|
| **0.0 - 1.0** | Seguridad muy baja |
| **1.0 - 2.5** | Seguridad baja |
| **2.5 - 3.5** | Seguridad media |
| **3.5 - 4.5** | Seguridad alta |
| **4.5 - 5.0** | Seguridad excelente |

---

## 🗂️ Archivos Relacionados

```
services/
├── indicators/security/
│   ├── README.md                    # Este archivo
│   ├── calculator.py                # Utilidades Python
│   └── ahp_weights.py               # Entrenamiento AHP
│
├── database/migrations/
│   └── V16__security_indicator.sql  # Tablas/funciones
│
└── orchestrator/
    └── post_scraping.py             # Refresh automático
```

---

## 🔍 Consultas Útiles

```sql
-- Ver seguridad por sector
SELECT nombre, 
       homicidios, 
       delitos_sexuales,
       ahp_crimen,
       score_seguridad
FROM iug.sectores_policia
ORDER BY score_seguridad DESC;

-- Inmuebles con mejor seguridad
SELECT id_inmueble, tipo_inmueble, iseg_normalizado
FROM iug.indicador_seguridad_final
ORDER BY iseg_normalizado DESC
LIMIT 10;

-- CAI más cercano a un inmueble
SELECT i.id_inmueble,
       c.nombre as cai_cercano,
       ROUND(ST_Distance(i.geom::geography, c.geom::geography)) as distancia_m
FROM iug.inmueble i
CROSS JOIN LATERAL (
    SELECT nombre, geom
    FROM iug.cai
    ORDER BY geom::geography <-> i.geom::geography
    LIMIT 1
) c
WHERE i.id_inmueble = 123;
```
