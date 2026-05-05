# Changelog del corpus — INMU / IUG Bogotá

Documento de trazabilidad del corpus de datos sobre el cual se calcula
el Índice Urbano Global (IUG). Las entradas se ordenan de la más reciente
a la más antigua. Cada entrada describe el delta respecto a la versión
inmediatamente anterior y las pruebas estadísticas re-ejecutadas.

---

## v2.0 — 2026-05-05 · Carga completa de POIs y aislamiento multi-ciudad

### Resumen

Tras la entrega documental de la tesis, se completó la carga de las
categorías de dotación que la metodología describe pero que no se habían
ingerido al momento del corte. Adicionalmente se aisló del cálculo el
sub-corpus correspondiente a inmuebles fuera del alcance espacial del
estudio (Medellín, Cali, Barranquilla).

### Cambios en POIs (`iug.dotaciones_poi`)

| Categoría | v1.0 (tesis) | v2.0 (vigente) | Delta | Fuente |
|---|---:|---:|---:|---|
| Farmacias | 8.129 | 8.129 | = | Datos Abiertos Bogotá |
| IPS · Salud | 240 | 240 | = | salud.geojson |
| Bibliotecas | 23 | 23 | = | BibloRed |
| Centros comerciales | 42 | 70 | +28 | centro-comercial.csv |
| **Colegios SED** | 0 | **2.237** | **+2.237** | colegios12_2024.geojson |
| **Universidades** | 0 | **583** | **+583** | ecosistema_educacion_superior.geojson |
| **Teatros** | 0 | **134** | **+134** | teatroauditorio.json |
| **Parques IDRD** | 0 | **184** | **+184** | directorio-parques-2023.csv |
| **Escenarios deportivos** | 0 | **10** | **+10** | parques IDRD subset |
| Plazas de mercado | 0 | 0 | pendiente | CRS no estándar — investigación abierta |
| **TOTAL** | **8.434** | **11.610** | **+3.176** | |

### Cambios en inmuebles

| Métrica | v1.0 (tesis) | v2.0 (vigente) | Nota |
|---|---:|---:|---|
| Inmuebles totales (todas las ciudades) | 6.418 | 45.438 | Crecimiento por scrapeo continuo |
| Inmuebles bogotanos (alcance estudio) | 6.418 | **23.761** | Filtrados por bbox |
| Inmuebles fuera de Bogotá | 0 | 21.671 | iurb seteado a `NULL`, no contaminan promedios |

### Implicación metodológica

El indicador de Dotación se construye por **proximidad acumulada** a
equipamientos. Al añadir POIs a categorías existentes, el efecto sobre
I_DOT,i es **monotónico no-decreciente**:

> ∀ i ∈ Inmuebles, I_DOT,i (v2.0) ≥ I_DOT,i (v1.0)

En consecuencia los resultados v1.0 son una **cota inferior conservadora**
de las cifras v2.0. Las conclusiones cualitativas se mantienen y se
refuerzan.

### Re-ejecución de pruebas estadísticas

Pruebas ejecutadas con `validar_iurb_completo()` sobre `iug.inmueble`
restringido al alcance bogotano (n = 13.462 inmuebles válidos con todos
los indicadores no-nulos, 19 localidades con masa crítica ≥ 50).

| Prueba | v1.0 (tesis) | v2.0 (vigente) | Veredicto |
|---|---:|---:|---|
| ΔR² (modelo completo − reducido) | +0.053 | **+0.0517** | Casi idéntico — ortogonalidad confirmada |
| ΔAIC | −658 | **−1586** | Mayor magnitud por mayor N |
| Varianza común (commonality) | 0.0% | 3.0% | Sigue dentro del rango ortogonal |
| ρ Spearman ranking (MC, mediana) | 0.995 | **0.998** | Mejora |
| IC 90% bootstrap ρ Spearman | n/d | [0.991, 1.000] | Excluye 0.90 |
| % zonas que cambian rank > umbral | n/d | 0.0% | Estabilidad total |

### IUG promedio Bogotá

| Métrica | v1.0 | v2.0 |
|---|---:|---:|
| IUG promedio (Bogotá) | 2.45 | **2.96** |
| Cobertura I_DOT > 0 | 36% | **70%** |
| Cobertura I_ACC > 0 | 33% | 62% |
| Cobertura I_SEG, I_HED, I_PNU | 100% | 100% |

### Nuevo top-10 ranking de localidades por IUG promedio

```
 1.  BARRIOS UNIDOS       3.95
 2.  PUENTE ARANDA        3.88
 3.  SUMAPAZ              3.86
 4.  ANTONIO NARIÑO       3.81
 5.  TUNJUELITO           3.76
 6.  BOSA                 3.58
 7.  SANTA FE             3.56
 8.  RAFAEL URIBE URIBE   3.51
 9.  …
10.  …
```

### Reproducibilidad

```bash
# 1. Carga incremental de POIs
docker compose --profile data run --rm --entrypoint sh data-loader \
    -c "python /app/loaders/load_dotaciones_faltantes.py"
docker compose --profile data run --rm --entrypoint sh data-loader \
    -c "python /app/loaders/load_universidades.py"

# 2. Copia universidades a dotaciones_poi para que entren al cálculo
docker compose exec postgres psql -U postgres -d postgres -c "
INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
SELECT COALESCE(nombre,'Universidad'), 'universidad',
       'ecosistema_educacion_superior.geojson', geom
FROM iug.universidad WHERE geom IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM iug.dotaciones_poi WHERE categoria='universidad');"

# 3. Recalcular todos los indicadores
docker compose exec postgres psql -U postgres -d postgres -c \
    "SELECT * FROM iug.f_recalcular_indicadores();"

# 4. Aislar inmuebles fuera del bbox de Bogotá (si los hubiera)
docker compose exec postgres psql -U postgres -d postgres -c "
UPDATE iug.inmueble SET
  iacc=NULL, iseg=NULL, ihed=NULL, idot=NULL, ipnu=NULL, iurb=NULL, iug=NULL
WHERE geom IS NOT NULL
  AND NOT (-75 < ST_X(geom) AND ST_X(geom) < -73
           AND 3 < ST_Y(geom) AND ST_Y(geom) < 6);"

# 5. Invalidar cache geo
curl -s -X POST 'https://inmu.vara-alta.lat/api/geo/cache/invalidar'

# 6. Re-ejecutar validación
docker compose exec api python /app/analytics/run_validation_post_corpus.py
```

### Issue abierto

- **Plazas de mercado**: el archivo `plaza_mercado.geojson` viene en un
  CRS no estándar (no es 3857, 4326, 3116 ni 21897). Las 42 plazas
  quedan pendientes hasta identificar el datum correcto. Su impacto en
  I_DOT es marginal por el bajo conteo y por estar correlacionadas
  espacialmente con otros equipamientos.

---

## v1.0 — 2026-04 · Estado documentado en la tesis

Estado del corpus en el corte de redacción del Trabajo de Grado.

- **6.418 inmuebles bogotanos** scrapeados de FincaRaíz y Habi
- **8.434 POIs** unificados en `iug.dotaciones_poi`, repartidos en 4 de las
  categorías metodológicas (farmacias, IPS, CC, bibliotecas)
- **149 estaciones TransMilenio**, **599 CAI Policía**, **44 sectores
  priorizados**, **5.703 polígonos POT tratamientos**, **2.748 polígonos
  edificabilidad**, **1.135 polígonos áreas de actividad**

Pruebas estadísticas reportadas en el Capítulo de Resultados:

- ΔR² (completo − reducido) = +0.053
- ΔAIC = −658
- Varianza común = 0.0%
- ρ Spearman ranking = 0.995
- IC 95% bootstrap ΔR² = [0.039; 0.064]
- M5 mejor especificación (log área): R² = 0.73 (+18 pp vs base)
- Mann-Whitney Q4 vs Q1 residual: p = 0.0007
- KS distribuciones COMPRAR vs CONSERVAR: p < 10⁻³⁷

Veredicto académico: **IUG válido como métrica compuesta ortogonal al
precio, capaz de discriminar mispricing entre calidad urbana objetiva
y valor de mercado.**
