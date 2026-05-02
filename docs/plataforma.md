# Plataforma web y asistente RAG

> Para detalle completo y capturas, consultar el Anexo B de la tesis.

## Frontend

**Stack:** React + Vite + Leaflet (cartografía).

### Tres niveles de resolución espacial

1. **Localidades** — 20 polígonos coloreados por IUG promedio.
2. **Barrios** — 1,721 polígonos legalizados con heterogeneidad interna visible.
3. **Inmuebles individuales** — puntos con popup que muestran:
   - Desglose de los 5 subíndices
   - Banda de confianza al 90%
   - Residual hedónico (precio observado vs. precio predicho)
   - Cuadrante de decisión asignado

### Filtros

- Tipo de inmueble (apartamento / casa)
- Rango de precio
- Umbrales por subíndice
- Localidad / barrio
- Cuadrante de la matriz de decisión

## Asistente conversacional (RAG)

Arquitectura **Retrieval-Augmented Generation** que conecta el LLM Gemini con una base de datos vectorial PgVector.

### Flujo

1. La descripción textual + atributos + subíndices de cada inmueble se transforman en **embeddings densos**.
2. La consulta del usuario en lenguaje natural se vectoriza.
3. Búsqueda por similitud coseno en PgVector → top-K inmuebles semánticamente relevantes.
4. El LLM compone la respuesta con los inmuebles recuperados como contexto.

### Ejemplos de consultas que el sistema resuelve

- *"apartamentos cerca al Transmilenio"*
- *"oportunidades en Chapinero con alto IUG y precio bajo"*
- *"casas seguras cerca a un hospital, vivo con mi abuela"* — el asistente solicita precisión sobre el hospital, pregunta proactivamente por accesibilidad, y luego busca

### Por qué supera al filtro SQL convencional

- Comprende **contexto semántico** (e.g., "para mi abuela" implica accesibilidad / seguridad).
- Combina criterios heterogéneos en una sola consulta.
- Solicita precisión cuando el requerimiento es ambiguo.

## Generación de cotizaciones (ACM)

El módulo de Análisis Comparativo de Mercado materializa la transición **indicador → documento operativo**.

### Flujo

1. Usuario selecciona un inmueble objetivo.
2. Sistema busca comparables por similitud espacial + estructural.
3. Se calcula intervalo de confianza al 90% con distribución *t*-Student (n − 1 grados de libertad). Para n = 3, t₂,₀.₉₅ = 2.920 produce intervalos 77% más anchos que con z = 1.645, reflejando la incertidumbre real con muestras pequeñas.
4. Se genera PDF con desglose IUG, residual hedónico, cuadrante de decisión y valoración estimada con su banda.

📎 **Sample real:** [`../samples/cotizacion_ejemplo.pdf`](../samples/cotizacion_ejemplo.pdf)

## Acceso

- **Plataforma en vivo:** <https://inmu.vara-alta.lat>
- **Despliegue local:** ver [`replicabilidad.md`](replicabilidad.md)

## Stack completo

| Componente | Tecnología |
|---|---|
| Frontend | React 18 + Vite |
| Mapa | Leaflet + react-leaflet |
| Backend API | FastAPI (Python 3.12) |
| BD analítica | PostgreSQL 16 + PostGIS |
| BD vectorial | pgvector |
| Cache + cola | Redis |
| LLM | Gemini |
| Túnel público | Cloudflare Tunnel |
| Orquestación | Docker Compose |
| CI / CD | GitHub Actions (runner self-hosted) |
