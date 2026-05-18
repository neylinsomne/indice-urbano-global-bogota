# Data Loaders - Carga Automática de Datos Estáticos

## Descripción

Sistema de carga automática de datos estáticos que se ejecuta en **startup del orquestador**.

Verifica si las tablas están vacías y carga los datos correspondientes **una sola vez**, evitando scripts manuales hardcodeados.

---

## 📦 Loaders Implementados

### 1. `dotaciones_loader.py` - POIs de Dotaciones
**Tablas**: `iug.dotaciones_poi`

**Datos cargados**:
- Salud: `salud.geojson`, `farmacias.geojson`
- Educación: `colegios12_2024.geojson`
- Cultura: `biblored.geojson`
- Abastecimiento: `centros_comerciales_bogota.csv`
- Recreación: `osm_parks` (centroide)

**Total**: ~10,881 POIs

---

### 2. `osm_loader.py` - Datos OSM
**Tablas**: `iug.osm_transport`, `iug.osm_parks`, `iug.osm_main_roads`

**Datos cargados** (desde `Bogota.osm.pbf`):
- **SITP**: Paradas de bus (`amenity='bus_stop'`)
- **Parques**: Polígonos de parques (`leisure='park'`)
- **Vías**: Vías principales (motorway, trunk, primary, secondary, tertiary)

**Método**: `ogr2ogr` en subprocess

---

### 3. `security_loader.py` - Datos de Seguridad
**Tablas**: `iug.sectores_policia`, `iug.cai`

**Estado**: Verifica si están vacías y registra warnings

**Nota**: Estos datos normalmente vienen de fuentes oficiales (Policía Nacional) y deben cargarse manualmente o desde archivos específicos.

---

## 🔄 Flujo de Ejecución

### Startup del Orquestador

```python
# services/orchestrator/__init__.py

async def start_orchestrator():
    # 1. Dotaciones (POIs)
    await load_dotaciones_if_empty()
    
    # 2. OSM (Transporte, parques, vías)
    await load_all_osm_data()
    
    # 3. Seguridad (Sectores, CAI)
    await load_all_security_data()
    
    # 4. Setup event handlers
    await setup_post_scraping()
    await setup_individual_insert()
```

### Cuándo se Ejecuta

- ✅ **Primera vez** que levanta el API (tablas vacías)
- ✅ Después de `docker compose restart`
- ✅ Después de aplicar migraciones que crean tablas nuevas
- ❌ **NO se ejecuta** si las tablas ya tienen datos

---

## 🛠️ Agregar Nuevo Loader

### Paso 1: Crear archivo loader

```python
# services/orchestrator/data_loaders/mi_loader.py

import psycopg2
import logging

logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'postgres'),
    'port': os.getenv('PG_PORT', '5432'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

def check_table_empty(conn, table_name):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0] == 0

async def load_mi_data_if_empty():
    conn = psycopg2.connect(**DB_CONFIG)
    
    if check_table_empty(conn, 'iug.mi_tabla'):
        logger.info("Cargando mi_tabla...")
        # Lógica de carga aquí
        with conn.cursor() as cur:
            cur.execute("INSERT INTO iug.mi_tabla ...")
            conn.commit()
    
    conn.close()
```

### Paso 2: Exportar en `__init__.py`

```python
# services/orchestrator/data_loaders/__init__.py

from .mi_loader import load_mi_data_if_empty

__all__ = [
    'load_dotaciones_if_empty',
    'load_all_osm_data',
    'load_all_security_data',
    'load_mi_data_if_empty'  # ← Agregar
]
```

### Paso 3: Llamar en orquestador

```python
# services/orchestrator/__init__.py

async def start_orchestrator():
    try:
        from .data_loaders import (
            load_dotaciones_if_empty,
            load_all_osm_data,
            load_all_security_data,
            load_mi_data_if_empty  # ← Agregar
        )
        
        await load_dotaciones_if_empty()
        await load_all_osm_data()
        await load_all_security_data()
        await load_mi_data_if_empty()  # ← Llamar
```

---

## 📋 Checklist de Datos Estáticos

| Dato | Loader | Tabla | Estado |
|------|--------|-------|--------|
| **Dotaciones** | ✅ dotaciones_loader.py | dotaciones_poi | ✅ Implementado |
| **SITP** | ✅ osm_loader.py | osm_transport | ✅ Implementado |
| **Parques OSM** | ✅ osm_loader.py | osm_parks | ✅ Implementado |
| **Vías OSM** | ✅ osm_loader.py | osm_main_roads | ✅ Implementado |
| **TransMilenio** | ⚠️ osm_loader.py | estacion_transmilenio | ⚠️ Requiere archivo |
| **Sectores Policía** | ⚠️ security_loader.py | sectores_policia | ⚠️ Requiere archivo |
| **CAI** | ⚠️ security_loader.py | cai | ⚠️ Requiere archivo |
| **POT** | ❌ - | pot_* | ❌ Pendiente |
| **Cuadrantes** | ❌ - | cuadrante_policia | ❌ Pendiente |

---

## 🔍 Debugging

### Ver logs de carga

```bash
# Logs del orquestador en startup
docker logs api-inmobiliario | grep "CARGANDO"
```

### Verificar si tabla está vacía

```sql
SELECT COUNT(*) FROM iug.dotaciones_poi;
SELECT COUNT(*) FROM iug.osm_transport;
SELECT COUNT(*) FROM iug.osm_parks;
```

### Forzar recarga

```sql
-- Vaciar tabla para forzar recarga en próximo restart
TRUNCATE iug.dotaciones_poi;
-- Luego: docker compose restart
```

---

## ⚠️ Consideraciones

1. **Orden de carga**: Los loaders se ejecutan secuencialmente en el orden definido en `start_orchestrator()`

2. **Timeout**: Loaders con `ogr2ogr` pueden tardar varios minutos en archivos grandes

3. **Errores no bloquean startup**: Si un loader falla, el orquestador continúa (try/except)

4. **Idempotencia**: Cada loader verifica si la tabla está vacía antes de cargar

5. **Paths Docker**: Los paths deben ser relativos al contenedor (`/app/...`)

---

## 🚀 Próximos Loaders Sugeridos

1. **POT Loader** (`pot_loader.py`):
   - `pot_tratamiento`
   - `pot_edificabilidad`
   - `pot_area_actividades`

2. **Cuadrantes Loader** (`cuadrantes_loader.py`):
   - `cuadrante_policia`

3. **TransMilenio Loader** (extender `osm_loader.py`):
   - Cargar desde GeoJSON específico si existe

---

## 📁 Estructura de Archivos

```
services/orchestrator/data_loaders/
├── __init__.py                 # Exports
├── dotaciones_loader.py        # POIs (10,881 registros)
├── osm_loader.py               # SITP, parques, vías
├── security_loader.py          # Sectores, CAI (warnings)
└── README.md                   # Este archivo
```

---

## 🎯 Ventajas del Sistema

✅ **Sin hardcoding**: No más scripts manuales  
✅ **Automático**: Se ejecuta en startup  
✅ **Idempotente**: Solo carga si tabla vacía  
✅ **Modular**: Fácil agregar nuevos loaders  
✅ **Resiliente**: Errores no bloquean startup  
✅ **Documentado**: README + logs claros
