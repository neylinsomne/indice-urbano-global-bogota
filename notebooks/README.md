# Notebooks · Índice Urbano Global

Tres notebooks que reproducen los hallazgos centrales de la tesis sobre una
muestra sintética. Para correr contra el corpus real necesitas levantar el
backend (ver `docker-compose.public.yml` en la raíz del repo).

## Contenido

| # | Notebook | Descripción | Datos requeridos |
|---|---|---|---|
| 01 | [`01_iug_construccion.ipynb`](01_iug_construccion.ipynb) | Calcula las 5 dimensiones del IUG (I_ACC, I_SEG, I_HED, I_DOT, I_PNU), las agrega con PCA y valida la ortogonalidad respecto al precio. **Notebook completo y ejecutable** sobre la muestra. | `data_sample/inmuebles_sample.csv` · `data_sample/pois_sample.csv` · `data_sample/localidades.geojson` |
| 02 | [`02_validacion_hedonica.ipynb`](02_validacion_hedonica.ipynb) | Modelo hedónico clásico vs +IUG. Bootstrap, ΔR², ΔAIC. **Resumen + esqueleto**; la implementación completa vive en `services/api/services/regression_service.py`. | corpus completo (vía API) |
| 03 | [`03_busqueda_natural.ipynb`](03_busqueda_natural.ipynb) | Demuestra el asistente RAG con dos turnos conversacionales (memoria Redis). Requiere el backend corriendo localmente. | API en `localhost:8000` |

## Datos de muestra (`data_sample/`)

| Archivo | Tamaño | Contenido |
|---|---|---|
| `inmuebles_sample.csv` | 14 KB | 200 inmuebles sintéticos con distribuciones calibradas al corpus real |
| `pois_sample.csv` | 4 KB | 80 POIs (transmilenio, hospitales, colegios, parques, universidades) |
| `localidades.geojson` | 2.2 MB | 20 polígonos reales de localidades de Bogotá (datos abiertos IDECA) |
| `generate_sample.py` | 6 KB | Script que regenera el CSV con `random.seed(20260517)` para reproducibilidad |

Los inmuebles son **sintéticos** — no se publican listados reales scrapeados. La distribución de precios y áreas está calibrada a las medianas observadas en cada localidad tras la corrección de geometrías documentada en el corpus.

## Correr en Kaggle

1. Crea un nuevo notebook en https://kaggle.com/code
2. *Add data* → *Upload dataset* → sube `data_sample/` como dataset (Kaggle lo monta en `/kaggle/input/...`)
3. Sube el `.ipynb` correspondiente
4. Cambia la línea `DATA = Path('data_sample')` por `DATA = Path('/kaggle/input/inmu-iug/data_sample')` (ajusta el nombre del dataset según lo hayas subido)
5. *Run All*

## Correr localmente

```bash
# Desde la raíz del repo
pip install pandas numpy scikit-learn scipy matplotlib jupyter
cd notebooks
jupyter notebook
```

## Reproducibilidad

- `random.seed(20260517)` en `generate_sample.py` → el CSV es bit-exact reproducible
- Pesos PCA dependen de los datos; con la semilla fija siempre sale el mismo IUG
- Las dimensiones simplificadas del notebook 01 son una aproximación didáctica de las del backend (que usan datos oficiales: EPV 2024, POT Decreto 555/2021, OSM, IDECA)
