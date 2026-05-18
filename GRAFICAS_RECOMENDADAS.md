# Gráficas recomendadas para sustentación

Lista priorizada de gráficas que tienen **alto impacto académico** y que
encajan con los slots ya dejados en `Presentacion_grado.tex` (los
`\figslot{…}{figs/…}`).

Cada entrada indica:
- **Qué**: descripción y datos a usar
- **Por qué**: el argumento que cierra
- **Cómo**: librería sugerida (matplotlib/seaborn/Plotly)
- **Slot Beamer**: nombre del archivo que el .tex espera

---

## Prioridad 1 — Imprescindibles

### 1.1 Histograma + densidad de los 5 subíndices

- **Qué**: 5 mini-histogramas en grid 2×3 (uno por subíndice + el IUG
  global), cada uno con curva KDE encima y línea vertical en la media.
- **Por qué**: demuestra visualmente lo que el test de normalidad
  reportó. El bimodalismo de I_ACC y I_DOT salta a la vista —
  argumenta por qué se usa rank min-max y no z-score.
- **Cómo**:
  ```python
  import seaborn as sns, matplotlib.pyplot as plt
  fig, axs = plt.subplots(2, 3, figsize=(10, 6))
  for ax, col in zip(axs.flat, ["iurb","iacc","iseg","ihed","idot","ipnu"]):
      sns.histplot(df[col].dropna(), kde=True, ax=ax, color="#15803D")
      ax.axvline(df[col].mean(), color="#0A2540", ls="--")
      ax.set_title(col.upper())
  ```
- **Slot**: `figs/hist_subindices.pdf`

### 1.2 QQ-plot de residuos hedónicos

- **Qué**: scatter con cuantiles teóricos vs empíricos, línea
  diagonal en gris, puntos en verde, anotación con kurtosis exceso.
- **Por qué**: muestra honestamente las colas pesadas. Justifica usar
  bootstrap y errores estándar robustos.
- **Cómo**:
  ```python
  from scipy import stats
  stats.probplot(residuos, dist="norm", plot=plt)
  plt.title(f"QQ-plot residuos · kurt_exc = {stats.kurtosis(residuos):+.2f}")
  ```
- **Slot**: `figs/qq_residuos.pdf`

### 1.3 Mapa coroplético del IUG v2.0

- **Qué**: silueta de Bogotá con las 20 localidades, color por IUG
  promedio. Leyenda de gradiente gris → verde.
- **Por qué**: el "wow" visual para la sustentación. Demuestra
  cobertura espacial completa.
- **Cómo**: si tienes los polígonos en GeoJSON usa `folium` para
  exportar a PNG, o `geopandas.GeoDataFrame.plot()` + `cmap='Greens'`.
- **Slot**: `figs/mapa_iug_v2.pdf`

### 1.4 Bar chart de POIs por categoría

- **Qué**: barras horizontales con el conteo de cada categoría
  (farmacia 8129, colegio 2237, universidad 583, …). Anotar el
  total 11.610.
- **Por qué**: complementa la tabla de volumetría y muestra el
  desbalance natural del corpus.
- **Cómo**:
  ```python
  cats = df.dotaciones_poi.value_counts()
  cats.plot.barh(color="#15803D")
  ```
- **Slot**: `figs/poi_categorias.pdf`

### 1.5 Cuadrante de decisión 2×2 (mispricing)

- **Qué**: scatter en plano (precio_residual × IUG), 4 cuadrantes:
  Comprar / Conservar / Vender / Evitar, con porcentajes en cada uno
  (30.7%, 24.7%, …). Puntos coloreados por cuadrante.
- **Por qué**: la "moneda comunicacional" más fuerte de la tesis —
  el evaluador la va a recordar.
- **Cómo**:
  ```python
  import seaborn as sns
  sns.scatterplot(x=df.residual, y=df.iurb, hue=cuadrante,
                  palette={"COMPRAR":"#15803D", "VENDER":"#DC2626",
                           "CONSERVAR":"#94A3B8", "EVITAR":"#0A2540"},
                  s=8, alpha=0.4)
  plt.axhline(df.iurb.median(), color="k", ls="--")
  plt.axvline(0, color="k", ls="--")
  ```
- **Slot**: `figs/cuadrante_decisiones.pdf`

---

## Prioridad 2 — Apoyo metodológico

### 2.1 Scree plot del PCA (I_HED)

- **Qué**: eigenvalues vs número de componente, regla de Kaiser
  (eigenvalue > 1), porcentaje acumulado de varianza explicada.
- **Slot**: `figs/scree_ihed.pdf`

### 2.2 Scatter D_obj vs D_subj (I_SEG)

- **Qué**: por cada localidad, criminalidad objetiva (ICSU) vs
  percepción (EPV 2024). Marcar las "paradojas" (alta crim, baja perc).
- **Por qué**: visualiza la "paradoja de la inseguridad" mencionada.
- **Slot**: `figs/scatter_seg.pdf`

### 2.3 Histograma de I_ACC con anotación gravity-decay

- **Qué**: distribución de I_ACC con anotación del parámetro β=1.5
  y el valor de threshold para "buena accesibilidad".
- **Slot**: `figs/hist_iacc.pdf`

### 2.4 Heatmap de correlación entre subíndices

- **Qué**: matriz 5×5 con correlaciones de Pearson + Spearman. Notar
  que las correlaciones son moderadas (no >0.7 entre ningún par).
- **Por qué**: refuerza el argumento de ortogonalidad/no-colinealidad
  entre dimensiones.
- **Slot**: `figs/heatmap_corr.pdf`

---

## Prioridad 3 — Detalles para apoyar Q&A

### 3.1 Distribución espacial de POIs nuevos vs viejos

- **Qué**: dos mapas lado a lado, v1.0 (solo farmacia, IPS, CC,
  biblioteca) vs v2.0 (todas las categorías). Muestra el "antes/después"
  del cargue de datos.

### 3.2 Curva de ΔAIC vs N

- **Qué**: línea mostrando cómo crece la magnitud del ΔAIC a medida
  que aumenta el tamaño de la muestra (6.418 → 23.761). Justifica que
  el corpus ampliado refuerza, no contradice.

### 3.3 Bootstrap distribution del ΔR²

- **Qué**: histograma de 1000 ΔR² bootstrappeados con IC 95%
  marcado en rojo. Visualiza que el IC excluye cero.

### 3.4 Tiempo de respuesta del RAG

- **Qué**: scatter latencia vs complejidad de la query (n° de
  proximities + geocoding sí/no). Justifica que el sistema es
  usable en producción.

---

## Generación masiva — script sugerido

Si quieres generar las gráficas v1 todas de una sola vez, este
snippet engancha con la base ya viva:

```python
# guardar como notebooks/figuras_sustentacion.ipynb
import os, psycopg2, pandas as pd, matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

conn = psycopg2.connect(host="localhost", port=5434, user="postgres",
                        password=os.environ["PG_PASSWORD"], dbname="postgres")

df = pd.read_sql("""
    SELECT i.iurb, i.iacc, i.iseg, i.ihed, i.idot, i.ipnu,
           i.precio, i.area_construida AS area, i.habitaciones, i.banos,
           l.nombre AS localidad
    FROM iug.inmueble i
    LEFT JOIN iug.localidad l ON i.id_localidad = l.id_localidad
    WHERE i.iurb IS NOT NULL
      AND i.precio BETWEEN 50000000 AND 5000000000
      AND i.area_construida BETWEEN 20 AND 1500
""", conn)

# 1.1 Histograma 5 subíndices
fig, axs = plt.subplots(2, 3, figsize=(11, 6))
for ax, col in zip(axs.flat, ["iurb","iacc","iseg","ihed","idot","ipnu"]):
    sns.histplot(df[col], kde=True, ax=ax, color="#15803D", bins=40)
    ax.axvline(df[col].mean(), color="#0A2540", ls="--", lw=1)
    ax.set_title(col.upper(), fontsize=10)
plt.tight_layout()
plt.savefig("figs/hist_subindices.pdf")

# ... etc para las demás (ver descripciones arriba)
```

---

## Estilo visual recomendado

Para que todas las gráficas hablen el mismo idioma del documento:

| Elemento     | Color hex     | Uso                                    |
|---|---|---|
| Verde principal  | `#15803D`  | Datos / barras / línea principal       |
| Verde claro      | `#22C55E`  | Highlights / hover / segundario        |
| Azul oscuro INMU | `#0A2540`  | Líneas de referencia / texto principal |
| Gris medio       | `#64748B`  | Texto secundario / leyendas            |
| Rojo crítico     | `#DC2626`  | Outliers / cuadrante "VENDER"          |

Tipografía: **Inter** o **Helvetica Neue** (matplotlib `font.sans-serif`),
tamaños mínimos 9pt para axis labels, 10pt títulos.
