# Cálculo de indicadores

> Para definiciones formales, fórmulas y discusión metodológica, consultar el Capítulo 2 de la tesis.

## Fórmula del IUG

$$
\text{IUG}_i = w_1 I_{HED} + w_2 I_{ACC} + w_3 I_{SEG} + w_4 I_{DOT} + w_5 I_{PNU}
$$

Donde Σwₖ = 1. Por defecto los pesos son equiponderados (wₖ = 0.20).

## Los cinco subíndices

### `I_HED` — Calidad construida (Hedónico)

Score derivado de **PCA** sobre variables estructurales (área, baños, garajes). Captura el confort privado del inmueble.

**Validación previa al PCA:** test KMO ≥ 0.50, esfericidad de Bartlett (p < 0.05), Kaiser (λ > 1), bootstrap de estabilidad (200 réplicas). Si falla, fallback a pesos proporcionales a la varianza, luego a promedio simple.

### `I_ACC` — Accesibilidad

**Modelo gravitacional:**

$$
I_{ACC,i} = \sum_j \frac{O_j}{d_{ij}^{\beta}}
$$

Suma de oportunidades ponderadas por el inverso de la distancia a estaciones de Transmilenio y SITP. β calibrado empíricamente.

### `I_SEG` — Seguridad

**Indicador tridimensional** — combinación lineal:

$$
I'_{SEG} = 0.40 \cdot S_{micro} + 0.30 \cdot D_{obj} + 0.30 \cdot D_{subj}
$$

Donde:
- `S_micro` — proximidad local a CAI y sectores priorizados
- `D_obj` — Indicador Compuesto de Seguridad Urbana (ICSU), 7 tipos de delito normalizados por km²
- `D_subj` — percepción derivada de la EPV 2024 (n = 19,354)

**Por qué tridimensional:** la correlación entre criminalidad objetiva y percepción es débil (r = 0.3174); el 44% de las localidades exhibe la "paradoja de inseguridad" (baja criminalidad pero alta percepción de riesgo).

### `I_DOT` — Dotación urbana

Proximidad acumulada a equipamientos (salud, educación, cultura, comercio, parques) en **radios de caminabilidad**:

- 400 m → 5 minutos a pie
- 800 m → 10 minutos a pie

Estos radios corresponden a estándares urbanísticos internacionales y determinan la cobertura efectiva de servicios para un residente sin vehículo.

### `I_PNU` — Potencial normativo

Scoring sobre el **POT 555** (Plan de Ordenamiento Territorial vigente):

- Tratamiento urbanístico (consolidación, renovación, mejoramiento, etc.)
- Edificabilidad (altura permitida)
- Área de actividad (residencial, mixta, comercial)

## Normalización

Todos los subíndices se normalizan a una escala común [0, 5] mediante **rank-min-max**:

$$
S(X_i) = 5 \times \frac{\text{rank}(X_i) - 1}{N - 1}
$$

A diferencia del Z-score (que produce valores negativos), esta escala permite lectura intuitiva donde 5 representa la máxima dotación observada en la muestra.

## Ratio de Oportunidad

$$
\text{Ratio}_i = \frac{\text{IUG}_i}{\tilde{P}_i}
$$

Donde Ratio > 1 sugiere subvaloración relativa: alta calidad urbana con precio contenido.

## Tratamiento de outliers (DBSCAN)

- Outliers (cluster -1): se **excluyen del modelo hedónico** (evita sesgo en β).
- Outliers: se **incluyen en el cálculo del IUG** pero con simbología diferenciada en el mapa.

Resultado en la muestra: 239 outliers (3.7%), más frecuentes en casas (4.9%) que en apartamentos (2.9%).

## Cobertura por subíndice

| Subíndice | Cobertura |
|---|---|
| I_SEG | 99.9% (opera a escala de localidad) |
| I_ACC | 53.7% (depende de proximidad a transporte masivo) |
| I_HED | 33.7% (datos completos de estructura) |
| I_DOT | 32.9% (intersección con POIs) |
| I_PNU | 33.3% (intersección con POT) |
| **IUG** | **100%** (calculado con los disponibles) |
