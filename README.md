# Índice Urbano Global de Bogotá (IUG)

> Trabajo de Grado · Pontificia Universidad Javeriana · Facultad de Ciencias · Programa de Ciencia de Datos · 2026
> 
> **Autor:** Neyl Peñuela Bernate &nbsp;·&nbsp; **Director:** Vladimir Moreno G.
> 
> **Despliegue público:** [`inmu.vara-alta.lat`](https://inmu.vara-alta.lat) · **Repo permanente:** [`neylinsomne/indice-urbano-global-bogota`](https://github.com/neylinsomne/indice-urbano-global-bogota)

---

## 🌐 Plataforma en vivo

👉 **<https://inmu.vara-alta.lat>**

> *Última actualización del enlace: **2026-05-01**.*
> 
> Si el enlace no responde al momento de consulta, el repositorio incluye el código fuente completo, capturas representativas y las instrucciones de despliegue local mediante `docker compose`. La plataforma se puede levantar en cualquier máquina sin dependencias externas más allá de Docker.

<!-- ![QR](docs/qr_inmu.png) -->

---

## 📄 Documento de tesis

| Recurso | Enlace |
|---|---|
| Tesis (PDF) | [`Doc_final.pdf`](Doc_final.pdf) |
| Fuente LaTeX | [`Doc_final.tex`](Doc_final.tex) |
| Bibliografía | (incluida en el `.tex`) |

---

## 🧠 ¿Qué es el IUG?

El **Índice Urbano Global (IUG)** es un indicador sintético adimensional, en escala 0-5, que mide la **calidad integral del entorno urbano** de un inmueble en Bogotá, **independientemente de su precio de mercado**.

A diferencia de un Modelo de Valoración Automática (AVM), el IUG **no predice el precio**: lo contrasta. Su utilidad reside en revelar la *brecha* entre lo que el mercado paga y la calidad urbana objetiva del territorio, habilitando una matriz de decisión 2×2 (`comprar`, `conservar`, `vender`, `evitar`) sobre el mercado residencial.

El indicador sintetiza cinco dimensiones:

| Símbolo | Dimensión | Metodología |
|---|---|---|
| `I_ACC` | Accesibilidad | Modelo gravitacional sobre Transmilenio + SITP |
| `I_SEG` | Seguridad | Indicador tridimensional (proximidad CAI + ICSU + EPV 2024) |
| `I_HED` | Calidad construida | Score hedónico vía PCA |
| `I_DOT` | Dotación urbana | Proximidad acumulada a equipamientos en radios de caminabilidad |
| `I_PNU` | Potencial normativo | Scoring sobre POT 555 |

📚 **Documentación detallada por subsistema:**

- [Metodología general](docs/metodologia.md)
- [Pipeline de datos](docs/pipeline.md)
- [Cálculo de indicadores](docs/indicadores.md)
- [Modelo hedónico y validación](docs/modelo_hedonico.md)
- [Plataforma web y asistente RAG](docs/plataforma.md)

---

## 🎬 Capturas del sistema

| | |
|---|---|
| **Mapa coroplético del IUG** | **Asistente conversacional (RAG)** |
| ![mapa](capturas/mapa_iug.png) | ![chatbot](capturas/chatbot_rag.jpg) |

---

## 📄 Output: Cotizaciones automatizadas

La plataforma genera reportes profesionales en PDF (Análisis Comparativo de Mercado — ACM) que materializan la transición del indicador al documento operativo.

🔗 **Ejemplo real:** [`samples/cotizacion_ejemplo.pdf`](samples/cotizacion_ejemplo.pdf)

Cada cotización incluye:
- Comparables seleccionados por similitud espacial y estructural
- Desglose del IUG por subíndices
- Residual hedónico (sobre/sub-valoración)
- Intervalo de confianza al 90% con distribución *t*-Student
- Cuadrante de decisión (`comprar` / `conservar` / `vender` / `evitar`)

---

## 🏗 Arquitectura

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Scraping   │───▶│   MongoDB    │───▶│  PostgreSQL  │───▶│   FastAPI    │
│   Selenium   │    │   (raw)      │    │   PostGIS    │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘    └──────┬───────┘
                                                │                    │
                                          ┌─────▼──────┐      ┌─────▼──────┐
                                          │  PgVector  │      │   React    │
                                          │ (embeddings)│      │  + Leaflet │
                                          └─────┬──────┘      └────────────┘
                                                │
                                          ┌─────▼──────┐
                                          │  Asistente │
                                          │   RAG      │
                                          └────────────┘
```

**Stack:** PostgreSQL 16 + PostGIS + pgvector · MongoDB · Redis · FastAPI · React + Vite · Leaflet · Scrapy + Playwright · Docker Compose · Cloudflare Tunnel · GitHub Actions (runner self-hosted)

📐 [Diagrama detallado y volumetría](docs/arquitectura.md)

---

## 🚀 Levantar el sistema localmente

```bash
git clone https://github.com/neylinsomne/indice-urbano-global-bogota.git
cd indice-urbano-global-bogota
cp .env.example .env
# Editar .env con tus credenciales

docker compose up -d postgres flyway redis
docker compose up -d api frontend
```

La plataforma queda disponible en `http://localhost:5173` y la API en `http://localhost:8000`.

📦 [Instrucciones detalladas](docs/replicabilidad.md)

---

## 📊 Métricas reportadas

El sistema reporta cerca de 40 métricas distintas agrupadas en 5 categorías. Resumen:

| Categoría | Cantidad | Ejemplos |
|---|---|---|
| Subíndices urbanos | 6 | I_ACC, I_SEG, I_HED, I_DOT, I_PNU, IUG |
| Métricas econométricas | 10 | R², RMSE, MAE, CV-RMSE, VIF, PSI |
| Métricas IAAO (tasación masiva) | 4 | COD, PRD, PRB, Median ratio |
| Pruebas de validez (Cap. 5) | 11 | Modelos anidados, ranking stability vía Monte Carlo, bootstrap, Ramsey, AUC, matriz 2×2 |
| Análisis complementarios | 7 | DBSCAN, AHP-PCA, Sobol, gravity calibration, uncertainty quantification |

📈 [Catálogo completo de métricas](docs/metricas.md)

---

## 📌 Citación

Si usas este trabajo, por favor cita:

```bibtex
@mastersthesis{penuela2026iug,
  author       = {Pe{\~n}uela Bernate, Neyl},
  title        = {{\'I}ndice de Precios Inmobiliarios por Bienestar y Entorno Urbano},
  school       = {Pontificia Universidad Javeriana},
  year         = {2026},
  type         = {Trabajo de Grado},
  address      = {Bogot{\'a}, Colombia},
  url          = {https://github.com/neylinsomne/indice-urbano-global-bogota}
}
```

---

## 📜 Licencia

Código bajo licencia MIT. Datos de fuentes oficiales bajo sus respectivas licencias (DANE, IDECA, SDP, IDRD, Cámara de Comercio, etc.). Datos de mercado obtenidos por web scraping con fines exclusivamente académicos bajo políticas de uso justo.

---

## 📬 Contacto

Para preguntas académicas o sobre el sistema: abrir un *issue* en este repositorio.
