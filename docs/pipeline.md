# Pipeline de datos

> Para detalle técnico completo (volumetría, modelo de datos, entorno computacional), consultar el Anexo A de la tesis.

## Diagrama general

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   INGESTA    │───▶│  PROCESADO   │───▶│ DISTRIBUCIÓN │
│              │    │              │    │              │
│ • Selenium   │    │ • Limpieza   │    │ • PostGIS    │
│ • Datos      │    │ • Geocoding  │    │   (analítica)│
│   abiertos   │    │ • Snapping   │    │ • PgVector   │
│              │    │   espacial   │    │   (chatbot)  │
└──────────────┘    └──────────────┘    └──────────────┘
       │                    │                    │
   MongoDB              MongoDB             PostgreSQL
   (raw JSON)          (procesado)          + pgvector
```

## Tres etapas

### 1. Ingesta

- **Web scraping**: Selenium contra portales inmobiliarios (Finca Raíz, Habi).
- **Datos abiertos**: descarga programada de capas oficiales (IDECA, SDP, IDRD, Sec. Seguridad, DANE).
- Resultado: ~6,418 inmuebles + ~180,000 entidades georreferenciadas.

### 2. Procesamiento

- Limpieza con DBSCAN para detección de outliers (~3.7% del dataset).
- Geocodificación inversa contra capas oficiales.
- Asignación espacial mediante operadores PostGIS:
  - `ST_Within(punto, poligono_barrio)` → barrio
  - `ST_Within(punto, poligono_localidad)` → localidad
  - `ST_Distance(punto, estaciones)` → métricas de accesibilidad

### 3. Distribución

Dos almacenes especializados:

- **PostGIS** — consultas espaciales estructuradas, agregaciones, modelos econométricos.
- **PgVector** — embeddings densos para búsqueda semántica del asistente RAG.

## Automatización mensual

GitHub Actions sobre runner self-hosted ejecuta:

1. Día 15 de cada mes, 03:00 hora Colombia.
2. Scrapers de Finca Raíz y Habi (matriz `tipos × sectores × txs`).
3. ETL completo vía endpoint `POST /pipeline/complete`.
4. Recálculo de indicadores con `f_recalcular_indicadores()` (función PostgreSQL).
5. Notificación por correo del resumen de carga.

Tareas Windows complementarias:

- `WakeForScraping` — despierta la máquina antes de la ejecución.
- `StartDockerForScraping` — garantiza que Docker está corriendo.
- `KeepRunnerAlive` — mantiene el runner conectado.

## Reproducibilidad local

Ver [`replicabilidad.md`](replicabilidad.md) para instrucciones detalladas de levantar la pila completa con `docker compose`.
