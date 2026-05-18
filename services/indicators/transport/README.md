# Indicador de Transporte (I_ACC)

## Descripción
Mide la **accesibilidad** a transporte público usando un **gravity model** que pondera la proximidad a paradas SITP y estaciones TransMilenio.

---

## 📊 Tablas en Base de Datos

| Tabla | Descripción | Registros |
|-------|-------------|-----------|
| `iug.osm_transport` | Paradas SITP (bus_stop) | ~2,000 |
| `iug.estacion_transmilenio` | Estaciones TransMilenio | ~140 |
| `iug.indicador_transporte_raw` | Scores gravity raw por inmueble | N inmuebles |
| `iug.indicador_transporte_final` | Vista materializada con normalización 0-5 | N inmuebles |

---

## 🧮 Fórmula

### Gravity Model
```
I_ACC_raw = Σ (1 / distancia_metros)

Donde:
- Se suman todas las paradas/estaciones dentro del radio
- Distancia mínima = 50m (evita división por cero)
```

### Normalización
```sql
I_ACC_normalizado = 5.0 × PERCENT_RANK() OVER (
    PARTITION BY tipo_inmueble 
    ORDER BY I_ACC_raw
)
```
**Resultado**: Escala 0-5, donde 5 = mejor accesibilidad **dentro de su tipo** (Apartamento vs Apartamento, Casa vs Casa).

---

## 📏 Distancias y Radios

| Tipo Transporte | Radio Influencia | Peso |
|-----------------|------------------|------|
| **SITP** (bus_stop) | 800 metros | 1.0 |
| **TransMilenio** | 1,500 metros | 2.0 (mayor peso) |

---

## 🔧 Scripts y Funciones

### Carga de Datos (Una sola vez)
```powershell
# services/database/extract_osm_complete.ps1
# Extrae paradas SITP y estaciones TM desde Bogota.osm.pbf
```

### Funciones SQL
```sql
-- Calcula score gravity para un punto
iug.calcular_score_gravity(geom, radio_sitp, radio_tm)

-- Trigger automático en INSERT/UPDATE
CREATE TRIGGER trg_inmueble_indicadores_raw
AFTER INSERT OR UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.trg_calcular_indicadores();
```

### Recálculo Masivo
```sql
-- Recalcular todos los inmuebles
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_transporte_final;
```

---

## 🔄 Actualización

### Automática (Triggers)
- ✅ **INSERT/UPDATE individual**: Trigger calcula I_ACC automáticamente
- ✅ **Batch scraping**: Orquestador refresca vista materializada

### Manual (Si se actualizan paradas SITP/TM)
```sql
-- 1. Re-extraer OSM (si hay nuevas paradas)
-- Ejecutar: extract_osm_complete.ps1

-- 2. Recalcular scores
SELECT iug.recalcular_transporte_masivo();

-- 3. Refresh vista
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_transporte_final;
```

---

## 📈 Interpretación

| I_ACC | Interpretación |
|-------|----------------|
| **0.0 - 1.0** | Accesibilidad muy baja |
| **1.0 - 2.5** | Accesibilidad baja |
| **2.5 - 3.5** | Accesibilidad media |
| **3.5 - 4.5** | Accesibilidad alta |
| **4.5 - 5.0** | Accesibilidad excelente |

**Nota**: Comparación **dentro del mismo tipo** de inmueble.

---

## 🗂️ Archivos Relacionados

```
services/
├── indicators/transport/
│   ├── README.md                    # Este archivo
│   ├── calculator.py                # Utilidades Python
│   └── config.py                    # RADIOS, PESOS_TRANSPORTE
│
├── database/
│   ├── migrations/
│   │   └── V15__transport_indicator.sql  # Creación tablas/funciones
│   └── extract_osm_complete.ps1     # Carga datos OSM
│
└── orchestrator/
    └── post_scraping.py             # Refresh automático post-batch
```

---

## 🔍 Consultas Útiles

```sql
-- Ver distribución por tipo
SELECT tipo_inmueble, 
       COUNT(*) n,
       ROUND(AVG(iacc_normalizado), 2) avg,
       ROUND(MIN(iacc_normalizado), 2) min,
       ROUND(MAX(iacc_normalizado), 2) max
FROM iug.indicador_transporte_final
GROUP BY tipo_inmueble;

-- Top 10 mejor accesibilidad
SELECT id_inmueble, tipo_inmueble, iacc_normalizado
FROM iug.indicador_transporte_final
ORDER BY iacc_normalizado DESC
LIMIT 10;

-- Inmuebles con transporte cercano
SELECT i.id_inmueble,
       COUNT(DISTINCT t.id) n_sitp,
       COUNT(DISTINCT tm.id) n_transmilenio
FROM iug.inmueble i
LEFT JOIN iug.osm_transport t ON ST_DWithin(i.geom::geography, t.geom::geography, 800)
LEFT JOIN iug.estacion_transmilenio tm ON ST_DWithin(i.geom::geography, tm.geom::geography, 1500)
WHERE i.id_inmueble = 123
GROUP BY i.id_inmueble;
```
