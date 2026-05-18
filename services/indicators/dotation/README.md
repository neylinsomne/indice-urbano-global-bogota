# Indicador de Dotaciones (I_DOT)

## Descripción
Mide la **accesibilidad a equipamientos urbanos** usando un **gravity model** que pondera la proximidad a:
- Salud (IPS, hospitales, farmacias)
- Educación (colegios, universidades)
- Abastecimiento (supermercados, centros comerciales, plazas)
- Cultura (bibliotecas, teatros)
- Recreación (parques, canchas)

---

## 📊 Tablas en Base de Datos

| Tabla | Descripción | Registros |
|-------|-------------|-----------|
| **`iug.dotaciones_poi`** | **Tabla unificada de POIs** | **10,881** |
| `iug.pesos_dotacion` | Pesos por categoría (suma ponderada) | 5 categorías |
| `iug.pesos_dotacion_ahp` | Vacía (para futuro AHP) | 0 |
| `iug.indicador_dotacion_raw` | Scores gravity raw | N inmuebles |
| `iug.indicador_dotacion_final` | Vista materializada 0-5 | N inmuebles |

### Detalle de POIs en `dotaciones_poi`
| Categoría | Registros | Fuente |
|-----------|-----------|--------|
| **farmacia** | 8,129 | farmacias.geojson |
| **colegio** | 2,237 | colegios12_2024.geojson |
| **ips** | 240 | salud.geojson |
| **parque** | 210 | osm_parks |
| **centro_comercial** | 42 | centros_comerciales_bogota.csv |
| **biblioteca** | 23 | biblored.geojson |

---

## 🧮 Fórmula

### Gravity Model por Categoría
```
Score_Categoria = Σ (1 / distancia_metros)

Donde:
- Se suman todos los POIs de la categoría dentro del radio
- Distancia mínima = 50m
```

### Score Total Ponderado
```
I_DOT_raw = Σ (w_cat × Score_Categoria)

Pesos (w_cat):
- Salud: 0.20
- Educación: 0.20
- Abastecimiento: 0.25
- Cultura: 0.15
- Recreación: 0.20
Total: 1.00
```

### Normalización
```sql
I_DOT_normalizado = 5.0 × PERCENT_RANK() OVER (
    PARTITION BY tipo_inmueble 
    ORDER BY I_DOT_raw
)
```

---

## 📏 Distancias y Radios

| Categoría | Radio Influencia | Peso | Justificación |
|-----------|------------------|------|---------------|
| **Salud** | 1,000 m | 0.20 | Acceso a IPS/farmacias básico |
| **Educación** | 1,500 m | 0.20 | Colegios/universidades |
| **Abastecimiento** | 800 m | 0.25 | Supermercados, CCs (más peso) |
| **Cultura** | 2,000 m | 0.15 | Bibliotecas, teatros (menos frecuente) |
| **Recreación** | 1,500 m | 0.20 | Parques, canchas |

---

## 🔧 Scripts y Funciones

### Carga Inicial de Datos (Automática en startup)
```python
# services/orchestrator/data_loaders/dotaciones_loader.py
# Se ejecuta automáticamente si dotaciones_poi está vacía
```

**Archivos fuente**:
```
services/database/archivos/archivos/dotaciones/
├── salud.geojson
├── farmacias.geojson
├── colegios12_2024.geojson
├── biblored.geojson
├── centros_comerciales_bogota.csv
└── osm_parks (tabla existente)
```

### Funciones SQL
```sql
-- Calcula I_DOT para un punto
iug.calcular_idot_poi(geom)

-- Trigger automático
CREATE TRIGGER trg_calcular_dotacion
AFTER INSERT OR UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.trg_calcular_dotacion();

-- Recálculo masivo
SELECT iug.recalcular_dotacion_poi(NULL);
```

---

## 🔄 Actualización

### Automática
- ✅ **Primera vez**: Orquestador carga datos si `dotaciones_poi` vacía
- ✅ **INSERT/UPDATE individual**: Trigger calcula I_DOT
- ✅ **Batch scraping**: Orquestador refresca vista materializada

### Manual (Agregar nuevos POIs)
```sql
-- Insertar nuevo POI
INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
VALUES ('Nuevo Hospital', 'hospital', 'manual', ST_SetSRID(ST_MakePoint(-74.08, 4.65), 4326));

-- Recalcular inmuebles afectados (radio 1000m)
UPDATE iug.inmueble SET geom = geom
WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(-74.08, 4.65), 4326)::geography, 1000);

-- Refresh vista
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_dotacion_final;
```

---

## 📈 Interpretación

| I_DOT | Interpretación |
|-------|----------------|
| **0.0 - 1.0** | Dotación muy baja (zona periférica) |
| **1.0 - 2.5** | Dotación baja |
| **2.5 - 3.5** | Dotación media |
| **3.5 - 4.5** | Dotación alta |
| **4.5 - 5.0** | Dotación excelente (zona central) |

---

## 🗂️ Archivos Relacionados

```
services/
├── indicators/dotation/
│   └── README.md                    # Este archivo
│
├── database/
│   ├── migrations/
│   │   └── V25__dotation_indicator.sql  # Tablas/funciones
│   └── archivos/archivos/dotaciones/    # GeoJSON/CSV fuente
│
└── orchestrator/
    ├── data_loaders/
    │   └── dotaciones_loader.py     # Carga automática
    └── post_scraping.py             # Refresh automático
```

---

## 🔍 Consultas Útiles

```sql
-- Ver distribución de POIs por categoría
SELECT categoria, COUNT(*) n
FROM iug.dotaciones_poi
GROUP BY categoria
ORDER BY n DESC;

-- POIs cercanos a un inmueble
SELECT p.nombre, p.categoria,
       ROUND(ST_Distance(i.geom::geography, p.geom::geography)) dist_m
FROM iug.inmueble i
CROSS JOIN LATERAL (
    SELECT nombre, categoria, geom
    FROM iug.dotaciones_poi
    WHERE ST_DWithin(i.geom::geography, geom::geography, 1000)
    ORDER BY geom::geography <-> i.geom::geography
    LIMIT 10
) p
WHERE i.id_inmueble = 123;

-- Top 10 mejor dotación
SELECT id_inmueble, tipo_inmueble, idot_normalizado
FROM iug.indicador_dotacion_final
ORDER BY idot_normalizado DESC
LIMIT 10;

-- Pesos actuales
SELECT categoria, peso, radio_metros
FROM iug.pesos_dotacion
WHERE activo = true
ORDER BY peso DESC;
```

---

## 🔄 Agregar Nuevas Categorías

```sql
-- 1. Agregar peso
INSERT INTO iug.pesos_dotacion (categoria, peso, radio_metros, descripcion)
VALUES ('gimnasio', 0.10, 1000, 'Gimnasios y centros deportivos');

-- 2. Ajustar pesos existentes (suma debe = 1.0)
UPDATE iug.pesos_dotacion SET peso = 0.18 WHERE categoria = 'salud';
UPDATE iug.pesos_dotacion SET peso = 0.18 WHERE categoria = 'educacion';
-- ... etc

-- 3. Cargar POIs de la nueva categoría
INSERT INTO iug.dotaciones_poi (nombre, categoria, geom)
SELECT nombre, 'gimnasio', geom FROM fuente_gimnasios;

-- 4. Actualizar función calcular_idot_poi() para incluir nueva categoría
-- (Editar services/database/fix_idot_function.sql)
```
