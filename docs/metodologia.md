# Metodología general

> Para el detalle formal y matemático, consultar el Capítulo 3 de la tesis ([`Doc_final.tex`](../Doc_final.tex)).

## Marco conceptual

El IUG **no es un predictor de precio**. Es una herramienta-perspectiva que condensa cinco metodologías heterogéneas en una única escala interpretable, calculada de forma **ortogonal al precio**. La virtud del indicador no reside en su correlación con el precio, sino en su capacidad de revelar la *brecha* entre lo que el mercado paga y la calidad urbana objetiva del entorno.

## Pregunta de investigación

> ¿Es posible construir, a partir de fuentes abiertas y replicables, un indicador sintético de calidad urbana que sea estadísticamente válido, robusto y operativamente útil para identificar discrepancias entre el precio observado y los fundamentales urbanos del territorio?

## Enfoque CRISP-DM

El proyecto sigue la metodología CRISP-DM (Cross-Industry Standard Process for Data Mining):

1. **Business Understanding** — Definición del objetivo: contraste IUG vs. precio, KPI Ratio de Oportunidad, alcance Bogotá.
2. **Data Understanding** — Exploración de portales inmobiliarios, calidad IGAC/SIEDCO, cobertura espacial.
3. **Data Preparation** — ETL distribuido, geocodificación, snapping espacial.
4. **Modeling** — Hedónico + cuantílica + clustering DBSCAN + cálculo IUG.
5. **Evaluation** — Validación cruzada, robustez espacial, análisis de sensibilidad.
6. **Deployment** — Containerización, asistente IA, mapas interactivos.

## Big Data urbano (las 3 Vs)

- **Volumen:** cartografía catastral masiva (millones de vértices), bases históricas de seguridad.
- **Variedad:** SHP, GeoJSON, CSV, JSONB, HTML.
- **Veracidad:** validación cruzada contra fuentes oficiales (IDECA, SDP).

## Hipótesis

**Central:** existe información estructural sobre la calidad urbana que el precio no captura íntegramente.

**Operativa:** la ortogonalidad entre IUG y precio (correlación débil esperada, |ρ| < 0.30) no es un defecto sino la **condición necesaria** para que el indicador aporte información incremental sobre el benchmark hedónico.

## Lo que esta tesis NO intenta

- ❌ No es un AVM (Modelo de Valoración Automática).
- ❌ No estima precio puntual ni intervalo de precio para un inmueble.
- ❌ No incorpora costos de obra ni estructura financiera.
- ❌ No constituye instrumento tributario ni base catastral.
- ❌ No persigue eficiencia predictiva sobre el precio.

## Validación

El indicador se valida a través de un **protocolo de 11 pruebas estadísticas** (Capítulo 5 de la tesis):

- Bondad de ajuste y descomposición de varianza (4 pruebas)
- Robustez estadística (3 pruebas)
- Validez convergente y discriminante (1 prueba con 5 métricas)
- Validez de uso y matriz de mispricing (3 pruebas)

Ver detalle en [`metricas.md`](metricas.md).
