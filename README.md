# Índice Urbano Global de Bogotá (IUG)

[![Licencia: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm--Noncommercial--1.0.0-blueviolet)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL 16 + PostGIS](https://img.shields.io/badge/PostgreSQL_16-+_PostGIS-336791?logo=postgresql&logoColor=white)](https://postgis.net)
[![Docker](https://img.shields.io/badge/docker--compose-ready-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tesis · PUJ 2026](https://img.shields.io/badge/Tesis-PUJ_2026-D32F2F)](Doc_final.tex)

> **Trabajo de Grado** · Pontificia Universidad Javeriana · Facultad de Ciencias · Ciencia de Datos · 2026
> **Autor:** Neyl Peñuela Bernate · **Director:** Vladimir Moreno G.

Backend, metodología y notebooks de un sistema de inteligencia urbana que sintetiza la calidad del entorno de cualquier punto de Bogotá en un único índice (IUG, 0-5), validado como **ortogonal al precio inmobiliario** sobre ~16.500 listados reales. **El frontend no está incluido** en este repo (es un compañero comercial bajo licencia distinta). Lo que se publica acá es el corazón académico y reproducible.

---

## ⚡ Quickstart (60 segundos)

```bash
git clone https://github.com/neylinsomne/indice-urbano-global-bogota.git
cd indice-urbano-global-bogota
cp .env.example .env                                 # editar PG_PASSWORD, JWT_SECRET, GOOGLE_API_KEY
docker compose -f docker-compose.public.yml --profile api up -d
```

API → http://localhost:8000 · **Swagger interactivo** → http://localhost:8000/docs

```bash
# Sanity check
curl http://localhost:8000/health
# → {"status":"ok"}

# Búsqueda en lenguaje natural (requiere GOOGLE_API_KEY)
curl -X POST http://localhost:8000/api/llm/search-natural \
  -H 'Content-Type: application/json' \
  -d '{"query":"apto en chapinero cerca a hospital, menos de 600M","limit":3}'
```

---

## 🧠 ¿Qué es el IUG?

El **Índice Urbano Global** es una métrica sintética 0-5 que mide la *calidad del entorno urbano* de un punto de Bogotá, **independientemente del precio del inmueble** que ahí se encuentre. Se construye con PCA sobre cinco dimensiones independientes:

| Dim | Nombre | Insumo principal | Fuente |
|---|---|---|---|
| **I_ACC** | Accesibilidad | Gravedad sobre TransMilenio + SITP | TransMilenio S.A., SITP |
| **I_SEG** | Seguridad | EPV 2024 + ICSU + densidad CAI | Cámara de Comercio · SDSCJ |
| **I_HED** | Hedónico | precio_m² vs vecinos K-NN espaciales | Corpus propio (~16.5k listados) |
| **I_DOT** | Dotación | Densidad de hospitales/colegios/parques en 1 km | IDECA, IDRD, SED |
| **I_PNU** | Normativo | Clasificación Decreto POT 555/2021 | SDP |

**Validación** (corpus completo, ver `Doc_final.tex` Cap. 5):

| Métrica | Solo hedónico | + IUG | Δ |
|---|---|---|---|
| R² ajustado | 0.741 | **0.793** | +0.052 |
| AIC | -3217 | **-4803** | -1586 |
| ρ_Spearman precio_pred vs real | 0.945 | **0.998** | +0.053 |

Bootstrap (n=10.000) confirma ΔR² > 0 con p < 0.001 → el IUG **no es una proxy** del precio.

---

## 📚 Documentación

| Archivo | Contenido |
|---|---|
| [`Doc_final.tex`](Doc_final.tex) | Tesis completa · 130 K caracteres LaTeX |
| [`Presentacion_grado.tex`](Presentacion_grado.tex) | Slides de defensa Beamer |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Diagramas Mermaid: stack, pipeline ETL, esquema BD, asistente RAG |
| [`docs/metodologia.md`](docs/metodologia.md) | Justificación de PCA + AHP + ortogonalidad |
| [`docs/pipeline.md`](docs/pipeline.md) | Flujo end-to-end ingesta → indicadores |
| [`docs/indicadores.md`](docs/indicadores.md) | Cómo se computa cada dimensión |
| [`docs/modelo_hedonico.md`](docs/modelo_hedonico.md) | Lasso · Elastic Net · spatial CV · bootstrap |
| [`docs/replicabilidad.md`](docs/replicabilidad.md) | Cómo reproducir con tus datos |
| [`docs/metricas.md`](docs/metricas.md) | Catálogo de las 40 métricas reportadas |
| [`docs/plataforma.md`](docs/plataforma.md) | Asistente RAG + deploy |
| [`CHANGELOG_CORPUS.md`](CHANGELOG_CORPUS.md) | Versionado del corpus (v1.0 tesis · v2.0 vigente) |

---

## 🧪 Notebooks reproducibles

3 notebooks con datos sintéticos calibrados al corpus real (200 inmuebles), listos para Kaggle:

| Notebook | Contenido | Corre standalone |
|---|---|---|
| [`notebooks/01_iug_construccion.ipynb`](notebooks/01_iug_construccion.ipynb) | Cálculo de las 5 dimensiones + PCA → IUG + validación ortogonalidad | ✅ |
| [`notebooks/02_validacion_hedonica.ipynb`](notebooks/02_validacion_hedonica.ipynb) | Lasso/ElasticNet hedónico + bootstrap ΔR² | 🟡 corpus completo vía API |
| [`notebooks/03_busqueda_natural.ipynb`](notebooks/03_busqueda_natural.ipynb) | Asistente RAG con memoria conversacional | 🟡 requiere API levantada |

Detalles e instrucciones Kaggle: [`notebooks/README.md`](notebooks/README.md).

---

## 🏗 Arquitectura

```
┌──────────────┐  ┌───────────┐  ┌────────────────┐  ┌────────────┐
│  Scrapers    │─▶│  MongoDB  │─▶│  PostgreSQL    │◀▶│  FastAPI   │
│  (5 portales)│  │   (raw)   │  │  PostGIS+vec   │  │  /docs UI  │
└──────────────┘  └───────────┘  └────────┬───────┘  └─────┬──────┘
                                          │                │
                                  ┌───────▼──────┐  ┌──────▼──────┐
                                  │  Indicators  │  │   Redis     │
                                  │  ETL · IUG   │  │  RAG memory │
                                  └──────────────┘  └─────────────┘
```

Stack: **Python 3.11** · **FastAPI** · **asyncpg** · **PostgreSQL 16 + PostGIS 3.4 + pgvector** · **Redis 7** · **Flyway** · **Scrapy + Playwright + Selenium** · **Gemini Flash** (RAG) · **Prometheus + Grafana** · **Cloudflare Tunnel** (deploy).

Diagramas Mermaid completos en [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 🌐 Despliegue público (Cloudflare Tunnel)

El sistema se expone a internet sin abrir puertos en el router doméstico:

1. Crear túnel en https://one.dash.cloudflare.com → Networks → Tunnels
2. Copiar el `TUNNEL_TOKEN` y ponerlo en `.env` como `CLOUDFLARE_TUNNEL_TOKEN`
3. Mapear el subdominio (ej. `api.tu-dominio.com → http://api:8000`) en el panel Cloudflare
4. Levantar: `docker compose -f docker-compose.public.yml --profile api up -d`
5. Añadir el contenedor `cloudflared` al compose (ver línea comentada o el compose privado del autor para referencia)

**Beneficios:** TLS gratuito en el edge · WAF y DDoS protection incluidos · cero puertos abiertos hacia el ISP · multi-subdominio sin DNS extra.

---

## 📂 Estructura del repo

```
indice-urbano-global-bogota/
├── Doc_final.tex                 # Tesis principal (LaTeX)
├── Presentacion_grado.tex        # Slides defensa (Beamer)
├── ARCHITECTURE.md               # Diagramas Mermaid
├── CITATION.cff                  # Citation File Format
├── CLAUDE.md                     # Instrucciones para agentes IA
├── LICENSE                       # PolyForm Noncommercial 1.0.0
├── docker-compose.public.yml     # Stack mínimo reproducible
├── .env.example                  # Plantilla de variables
│
├── services/
│   ├── api/                      # FastAPI · routers · servicios · RAG
│   ├── database/                 # Migraciones Flyway · loaders · GeoJSON públicos
│   ├── scraping/                 # 5 spiders (Finca Raíz, Habi, Properati, …)
│   ├── indicators/               # Cálculo de las 5 dimensiones del IUG
│   ├── etl/                      # Pipeline transform Mongo → Postgres
│   ├── orchestrator/             # Coordinación de jobs
│   ├── monitoring/               # Prometheus + Grafana provisioning
│   └── utils/                    # Utilidades compartidas
│
├── notebooks/                    # Kaggle-ready notebooks
│   ├── 01_iug_construccion.ipynb
│   ├── 02_validacion_hedonica.ipynb
│   ├── 03_busqueda_natural.ipynb
│   └── data_sample/              # 200 inmuebles + POIs + localidades reales
│
├── docs/                         # Documentación metodológica
├── samples/                      # PDF de cotización ejemplo
├── scripts/                      # Scripts utilitarios
├── figs/                         # Figuras de la tesis
└── capturas/                     # Screenshots del sistema (referencia)
```

---

## 🔐 Seguridad y datos

- **Sin credenciales reales** en el repo. `.env.example` con placeholders, `.gitignore` cubre todos los formatos.
- **Sin direcciones ni teléfonos** de los listados scrapeados. Los notebooks usan datos sintéticos calibrados.
- Migraciones SQL `V107`+ implementan **defense in depth**: usuario `app_user` con permisos limitados al schema `iug`, hashing bcrypt cost 12, JWT con secreto largo, rate limiting de auth, audit log.
- Habeas Data (Ley 1581/2012): tablas de consentimiento y políticas documentadas en `V120__habeas_data.sql`.
- Auditado con `gitleaks` antes del push inicial; reporte limpio.

---

## 🤝 Cómo contribuir

Este es un trabajo de tesis individual, pero issues con preguntas/correcciones son bienvenidos. **No se aceptan PRs** que cambien la metodología documentada en `Doc_final.tex` sin discusión previa.

---

## 📌 Cita

```bibtex
@mastersthesis{penuela2026iug,
  author    = {Pe{\~n}uela Bernate, Neyl},
  title     = {{\'I}ndice Urbano Global de Bogot{\'a}: construcci{\'o}n metodol{\'o}gica y validaci{\'o}n emp{\'i}rica},
  school    = {Pontificia Universidad Javeriana},
  year      = {2026},
  type      = {Trabajo de grado · Pregrado en Ciencia de Datos},
  address   = {Bogot{\'a}, Colombia},
  url       = {https://github.com/neylinsomne/indice-urbano-global-bogota}
}
```

Formato Citation File Format (CFF) disponible en [`CITATION.cff`](CITATION.cff).

---

## 📜 Licencia

**[PolyForm Noncommercial 1.0.0](LICENSE)**. Permite uso académico, investigación, portafolio, evaluación, forks personales. **Prohíbe** uso comercial directo o reventa del software. Para licencia comercial: contactar al autor.

Datos de fuentes oficiales (DANE, IDECA, SDP, IDRD, IGAC, Cámara de Comercio de Bogotá) bajo sus respectivas licencias open data. Listados de mercado recolectados por web scraping con fines exclusivamente académicos bajo principios de fair use — sin información personal de anunciantes.

---

## 📬 Contacto

Issues técnicos: usar el sistema de issues de GitHub.
Consultas académicas: neylbernate@gmail.com.
