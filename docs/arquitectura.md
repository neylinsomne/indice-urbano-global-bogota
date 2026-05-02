# Arquitectura técnica

> Para volumetría completa y configuración Docker, consultar el Anexo A de la tesis.

## Volumetría del sistema

| Entidad | Naturaleza | Registros |
|---|---|---|
| Inmuebles | POINT | 6,418 |
| Características de inmueble | EAV | 87,117 |
| Historial de scrapeos | JSONB | 47,258 |
| Indicadores de transporte | gravity | 3,867 |
| Indicadores de seguridad | gravity | 4,665 |
| Indicadores de dotación | gravity | 5,289 |
| Localidades | MULTIPOLYGON | 20 |
| Barrios legalizados | MULTIPOLYGON | 1,721 |
| Tratamientos POT 555 | POLYGON | 5,703 |
| Edificabilidad | POLYGON | 2,748 |
| Áreas de actividad | POLYGON | 1,135 |
| Dotaciones POI | POINT | 8,434 |
| Estaciones Transmilenio | POINT | 149 |
| Paraderos SITP (OSM) | POINT | 7,693 |
| CAI de policía | POINT | 599 |
| Sectores priorizados | POLYGON | 44 |

**Total:** ~180,000 entidades georreferenciadas distribuidas en 30 tablas.

## Esquema de base de datos

Esquema principal: `iug` (PostgreSQL).

Tablas core:
- `iug.inmueble` — datos transaccionales + 6 subíndices calculados
- `iug.inmueble_caracteristica` — modelo EAV para atributos heterogéneos
- `iug.inmueble_scrapeo` — historial mensual con JSONB
- `iug.inmueble_historial` — auditoría de cambios
- `iug.localidad`, `iug.barrio`, `iug.upl` — capas administrativas
- `iug.tratamiento_pot`, `iug.edificabilidad`, `iug.area_actividad` — capas POT
- `iug.poi_dotacion`, `iug.estacion_tm`, `iug.paradero_sitp` — capas de transporte y servicios
- `iug.cai`, `iug.sector_priorizado`, `iug.criminalidad_localidad` — capas de seguridad

## Migraciones

Gestionadas con **Flyway**, versión actual: V118.

Cada migración es idempotente y reversible. Las funciones críticas:

- `f_asignar_barrio_localidad(id_inmueble)` — asignación espacial via ST_Within
- `f_recalcular_indicadores(id_inmueble)` — recálculo de los 6 subíndices
- `f_upsert_inmueble(...)` — inserción / actualización con auditoría
- `f_score_tratamiento(...)`, `f_score_edificabilidad(...)`, `f_score_area_actividad(...)` — scoring del POT

## Servicios Docker Compose

| Servicio | Imagen | Propósito |
|---|---|---|
| `postgres` | postgis/postgis:16 + pgvector | BD principal |
| `flyway` | flyway/flyway | Migraciones |
| `redis` | redis:7 | Cache + cola |
| `api` | python:3.12 + FastAPI | Backend REST |
| `frontend-dev` | node:20 + Vite | Desarrollo (HMR) |
| `frontend-prod` | nginx + build | Producción |
| `scraper-finca` | python:3.12 + Scrapy | Scraping Finca Raíz |
| `scraper-habi` | python:3.12 + Scrapy | Scraping Habi |
| `cloudflared` | cloudflare/cloudflared | Túnel público |
| `prometheus` | prom/prometheus | Métricas |
| `grafana` | grafana/grafana | Dashboards |

## Profiles

- `production` — api, frontend-prod, postgres, cloudflared
- `tunnel` — cloudflared aislado
- `finca`, `habi` — scrapers bajo demanda
- `monitoring` — prometheus, grafana, exporters

## Despliegue público

Cloudflare Tunnel desde un runner self-hosted (Windows) expone la aplicación sin abrir puertos en el firewall doméstico. La URL pública `https://inmu.vara-alta.lat` apunta al servicio `frontend-prod:80` vía un túnel autenticado por token.

## Secrets

Gestionados con GitHub Actions Secrets e inyectados como variables de entorno en `.env` (jamás versionadas):

- `MONGO_URI`, `PIPELINE_SECRET`, `JWT_SECRET`
- `GOOGLE_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`
- `REDIS_PASSWORD`, `GRAFANA_PASSWORD`

Ver `.env.example` para la plantilla.
