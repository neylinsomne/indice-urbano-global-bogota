# Arquitectura · Índice Urbano Global de Bogotá

Documento técnico de arquitectura. Para la justificación metodológica del IUG
consulta [`Doc_final.tex`](Doc_final.tex) y la carpeta [`docs/`](docs/).

---

## 1. Vista de alto nivel

```mermaid
flowchart LR
  subgraph Ingesta["📥 Ingesta · scrapers on-demand"]
    SF[Finca Raíz]
    SH[Habi]
    SP[Properati]
    SC[Ciencuadras]
    SS[SAE Bancolombia]
  end

  subgraph Datos["💾 Persistencia"]
    MG[(MongoDB · raw)]
    PG[(PostgreSQL 16 + PostGIS)]
    RD[(Redis 7)]
  end

  subgraph Procesamiento["⚙️ ETL · cálculo del IUG"]
    GEO[Georreferenciación]
    IND[Indicadores I_ACC / I_SEG /<br/>I_HED / I_DOT / I_PNU]
    PCA[PCA → IUG]
    HED[Validación hedónica]
  end

  subgraph API["🔌 API · FastAPI"]
    REST[Endpoints REST<br/>/docs · Swagger UI]
    RAG[Asistente RAG<br/>intent parser + Gemini]
    AUTH[Auth · JWT + bcrypt]
    AHP[AHP · pesos personalizados]
  end

  subgraph Clientes["👥 Consumidores"]
    Web[Cliente web<br/>fuera de este repo]
    NB[Notebooks Jupyter /<br/>Kaggle]
    Tools[curl / Postman /<br/>Swagger UI]
  end

  SF --> MG
  SH --> MG
  SP --> MG
  SC --> MG
  SS --> MG

  MG --> GEO
  GEO --> PG
  PG --> IND
  IND --> PCA
  PCA --> PG
  PG --> HED

  PG <--> REST
  RD <--> REST
  REST --> RAG
  REST --> AUTH
  REST --> AHP

  REST -.HTTPS.- Web
  REST -.HTTP.- NB
  REST -.HTTP.- Tools
```

---

## 2. Stack

| Capa | Tecnología | Por qué |
|---|---|---|
| **API** | FastAPI 0.115 · uvicorn · asyncpg · redis-asyncio | Asíncrono nativo, OpenAPI auto-generado, ecosistema Python rico para datos geoespaciales |
| **DB** | PostgreSQL 16 + PostGIS 3.4 + pgvector | Único motor que combina queries espaciales, vector similarity y SQL transaccional |
| **Cache** | Redis 7 | Memoria conversacional del RAG (TTL 24h) + cache de búsquedas frecuentes |
| **Migraciones** | Flyway 10 | Migraciones SQL versionadas, idempotentes, con rollback automático |
| **Scraping** | Scrapy 2.11 · Selenium Grid · Playwright | Coexisten 3 enfoques porque cada portal tiene un anti-bot distinto |
| **LLM** | Gemini Flash 1.5 (vía REST oficial) · LangChain | Latencia <800ms, tier free generoso, RAG con SQL grounding |
| **Reverse proxy** | Nginx + Cloudflare Tunnel | Despliegue público sin abrir puertos en el router |
| **Monitoring** | Prometheus 2.51 + Grafana 10 + postgres_exporter / redis_exporter | Estándar de la industria, dashboards JSON versionados |

---

## 3. Pipeline del IUG (de scrape a indicador)

```mermaid
sequenceDiagram
  autonumber
  participant S as Scraper
  participant M as MongoDB (raw)
  participant E as ETL
  participant P as PostgreSQL (PostGIS)
  participant I as Indicadores
  participant A as PCA
  participant H as Hedónico

  S->>M: dump JSON crudo por listado
  S->>M: ~15-30k listados/scrape, dedupe por id_origen
  Note over M: corpus crudo no normalizado

  E->>M: lee batch
  E->>E: geocoding (Nominatim · OSM)
  E->>E: parseo precio / área / habitaciones
  E->>E: dedupe geoespacial (DBSCAN)
  E->>P: INSERT iug.inmueble (geom = Point)

  I->>P: SELECT inmueble
  I->>P: SELECT pois cercanos (ST_DWithin 1km)
  I->>I: calcula I_ACC (transporte)<br/>I_SEG (criminalidad EPV)<br/>I_HED (precios K=20 KNN)<br/>I_DOT (dotación pública)<br/>I_PNU (POT)
  I->>P: UPDATE iug.inmueble (i_acc, i_seg, i_hed, i_dot, i_pnu)

  A->>P: SELECT 5 dimensiones por inmueble
  A->>A: PCA → IUG (componente principal)
  A->>P: UPDATE inmueble.iurb

  H->>P: SELECT IUG + precio
  H->>H: regresión hedónica<br/>(precio ~ log(area) + IUG + estrato + ...)
  H->>P: INSERT regression_run_history
  Note over H: valida ortogonalidad IUG ⊥ precio<br/>ΔR² · ρ_Spearman · ΔAIC
```

---

## 4. Modelo de datos (schema `iug`)

```mermaid
erDiagram
  inmueble {
    int  id_inmueble PK
    text tipo_inmueble
    bigint precio
    numeric area_construida
    smallint habitaciones
    smallint banos
    geom_point geom
    numeric i_acc "I_ACC accesibilidad"
    numeric i_seg "I_SEG seguridad"
    numeric i_hed "I_HED hedónico"
    numeric i_dot "I_DOT dotación"
    numeric i_pnu "I_PNU normativo POT"
    numeric iurb "IUG agregado (PCA)"
    int  id_localidad FK
    int  id_barrio FK
  }

  localidad {
    int id_localidad PK
    text nombre
    geom_multipolygon geom
  }

  barrio {
    int id_barrio PK
    text nombre
    geom_multipolygon geom
    int id_localidad FK
  }

  user_favoritos {
    bigint id PK
    int user_id FK
    int id_inmueble FK
    text nota
    text carpeta
    numeric snapshot_iug
    bigint snapshot_precio
  }

  users {
    int id PK
    text email
    text password_hash
    text role
    timestamptz created_at
  }

  centro_salud {
    int id PK
    text nombre
    geom_point geom
    text localidad
  }

  colegio {
    int id PK
    text nombre
    geom_point geom
    text localidad
  }

  inmueble }o--|| localidad : pertenece
  inmueble }o--|| barrio    : pertenece
  inmueble ||--o{ user_favoritos : tiene
  users    ||--o{ user_favoritos : guarda
  barrio   }o--|| localidad : pertenece
```

Migraciones Flyway en [`services/database/migrations/`](services/database/migrations/) — más de 120 archivos versionados (`V1` → `V121`), cada uno idempotente.

---

## 5. API · endpoints principales

| Prefijo | Función | Auth |
|---|---|---|
| `/inmueble/*` | CRUD inmuebles, estadísticas, búsqueda paginada | No (lectura) / sí (escritura) |
| `/geo/*` | GeoJSON de localidades, barrios, puntos | No |
| `/iurb/*` | Detalle del IUG por inmueble, oportunidades, recálculo | No |
| `/llm/*` | Chat conversacional + búsqueda en lenguaje natural | JWT opcional |
| `/auth/*` | Login, registro, verificación OTP | — |
| `/favoritos/*` | Inmuebles guardados por usuario | JWT |
| `/acm/*` | Análisis Comparativo de Mercado, PDF | JWT |
| `/regression/*` | Modelos hedónicos guardados, Lasso/Elastic Net | JWT (admin) |
| `/admin/*` | Panel de administración, recomputaciones | JWT (admin) |
| `/pipeline/*` | Ingesta autenticada desde scrapers | `PIPELINE_SECRET` |
| `/analytics/*` | KPIs de uso y conversiones | JWT (admin) |
| `/metrics` | Métricas Prometheus | No |
| `/health` | Healthcheck (keepalive Cloudflare) | No |
| `/docs` | **Swagger UI interactivo** (auto-generado por FastAPI) | No (dev) |

---

## 6. Asistente RAG · cómo funciona

```mermaid
flowchart TD
  Q[Consulta usuario<br/>texto libre] --> Router{detect_handler}

  Router -->|smalltalk| Quick[Respuesta canned · 0ms]
  Router -->|explain quick| Canned[Doc canned · 0ms]
  Router -->|explain fallback| Chat[SQL Agent · Gemini]
  Router -->|search| Mem[load conversation_memory · Redis]

  Mem --> Merge[merge previous intent<br/>filters into query]
  Merge --> Parse[intent_parser<br/>rule-based + Gemini fallback]
  Parse --> Geocode{¿menciona zona?}
  Geocode -->|sí| Nom[Nominatim geocoding]
  Geocode -->|no| Skip[continúa]
  Nom --> Spatial[spatial_search.py]
  Skip --> Spatial
  Spatial --> Cache{Redis hit?}
  Cache -->|sí| Return[devuelve cache]
  Cache -->|no| Query[PostgreSQL · ST_DWithin + scoring]
  Query --> Suggest[suggestions A/B/C/D<br/>refinamiento 1-click]
  Suggest --> Save[append_turn · Redis 24h]
  Save --> Return
```

El router clasifica la consulta en 6 categorías antes de tocar el LLM:

1. **smalltalk** ("hola", "gracias") → respuesta inmediata, 0 tokens
2. **explain (quick)** ("qué es IUG", "cómo se calcula I_ACC") → doc pre-renderizado
3. **explain (fallback)** → SQL Agent con grounding sobre el schema
4. **stats** (agregados por localidad) → query SQL directo
5. **compare** (inmueble A vs B) → dos lookups + diff
6. **search** → flujo completo de spatial search

Memoria conversacional en Redis (clave `chat:{session_id}`, TTL 24h, hasta 10 turnos) preserva el intent previo para que "ahora en chapinero" extienda la búsqueda anterior sin perder filtros.

---

## 7. Despliegue de referencia (Cloudflare Tunnel)

```mermaid
flowchart LR
  Browser[🌐 navegador] -->|HTTPS| CF[Cloudflare edge]
  CF -->|outbound TLS<br/>tunnel persistente| Tunnel[cloudflared<br/>container]
  Tunnel -->|HTTP interno<br/>red Docker| Nginx[reverse proxy<br/>opcional]
  Nginx --> API
  API[FastAPI] --> PG[(PostgreSQL)]
  API --> RD[(Redis)]
```

Beneficios:

- **Cero puertos abiertos** en el router doméstico — Cloudflare establece la conexión saliente
- TLS terminado en el edge de Cloudflare, con HTTPS gratuito
- Subdominios múltiples sin DNS adicional: `api.dominio.com`, `dashboard.dominio.com`, etc.
- DDoS / WAF de Cloudflare incluido en tier free

Config en el panel Cloudflare → no hay archivos secretos en el repo. El único valor sensible es el `CLOUDFLARE_TUNNEL_TOKEN` (en `.env`, nunca en el repo).

---

## 8. Decisiones de diseño relevantes

| Decisión | Por qué |
|---|---|
| FastAPI vs Flask/Django | Async nativo + OpenAPI gratis + tipado Pydantic |
| asyncpg vs SQLAlchemy ORM | Latencia crítica en queries espaciales; ORM agrega 30-50ms |
| Flyway vs Alembic | Migraciones SQL puras, audit-friendly para tesis |
| MongoDB para raw | Schema-less; cada scraper devuelve JSON con campos distintos |
| PostgreSQL para procesado | PostGIS + pgvector + transaccional en un solo motor |
| Redis para memoria conversacional | TTL nativo, sub-ms p99, sin schema rigid |
| PCA para agregar el IUG | Componente principal único maximiza varianza explicada; alternativa AHP por usuario también soportada |
| Gemini Flash vs GPT-4 | Tier free generoso · latencia 600-800ms · suficiente para intent parsing |
| `app_user` con permisos limitados | Defensa en profundidad: si la API es comprometida, el atacante no puede DROP TABLE |
| Tests de regresión hedónica en CI | Detecta regresiones de calidad del IUG cuando se reentrenan los pesos |
