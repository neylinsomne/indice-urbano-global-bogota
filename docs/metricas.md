# Catálogo completo de métricas

El sistema reporta cerca de 40 métricas distintas agrupadas en 5 categorías.

## 1. Subíndices urbanos (componentes del IUG)

| Símbolo | Nombre | Cálculo |
|---|---|---|
| `I_ACC` | Accesibilidad | Modelo gravitacional sobre Transmilenio + SITP |
| `I_SEG` | Seguridad | Tridimensional: proximidad CAI + ICSU + EPV 2024 |
| `I_HED` | Calidad construida | PCA sobre área, baños, garajes |
| `I_DOT` | Dotación urbana | Proximidad acumulada en radios 400 / 800 m |
| `I_PNU` | Potencial normativo | Scoring sobre POT 555 |
| `IUG` | Índice agregado | Σ wₖ Iₖ con Σwₖ = 1 |

## 2. Métricas econométricas (regresión hedónica)

- **R²** — Coeficiente de determinación
- **R² ajustado**
- **RMSE** — Error cuadrático medio raíz
- **MAE** — Error absoluto medio
- **CV-RMSE** mean / std (5-fold)
- **CV-R²** mean / std
- **α (alpha)** — hiperparámetro de regularización (Ridge / Lasso / Elastic Net)
- **L1-ratio** — Elastic Net
- **VIF** — Variance Inflation Factor (multicolinealidad)
- **PSI** — Population Stability Index (drift detection)

## 3. Métricas IAAO (estándar internacional de tasación masiva)

| Métrica | Aceptable IAAO | Significado |
|---|---|---|
| **COD** | 5–15% | Coefficient of Dispersion |
| **PRD** | 0.98–1.03 | Price-Related Differential |
| **PRB** | ±0.05 | Price-Related Bias |
| **Median ratio** | 0.90–1.10 | Nivel de tasación |

## 4. Pruebas de validez de uso (Capítulo 5 — 11 tests)

| # | Prueba | Métrica reportada |
|---|---|---|
| 1 | Modelos anidados | ΔR², ΔAIC, F-test, Likelihood Ratio |
| 2 | Análisis de comunalidad | Varianza única / común por subíndice |
| 3 | Estabilidad de ranking | ρ Spearman, % zonas que se mueven > 5 posiciones |
| 4 | Validación cruzada espacial | ΔR² CV espacial, leakage % |
| 5 | Bootstrap (1,000 reps) | IC 95 % de ΔR² y ΔAIC |
| 6 | Ramsey RESET | F-stat, p-value |
| 7 | Comparación de especificaciones | R² de M1–M5 |
| 8 | Subgrupos | CV del R² por localidad |
| 9 | Validez convergente | ρ(IUG, estrato), ρ(IUG, precio/m²), ANOVA F, η² |
| 10 | AUC clasificador estrato | ROC AUC |
| 11 | Matriz 2×2 de mispricing | Mann-Whitney p, KS p, % cuadrantes |

## 5. Análisis complementarios

- **DBSCAN** — outlier detection (n_outliers, % suprimidos)
- **AHP-PCA** — pesos empíricos, sensibilidad
- **Sobol** — índices de sensibilidad global (S₁, Sₜ) con muestreo Saltelli
- **Gravity model calibration** — β óptimo por modo de transporte
- **Normalization compare** — min-max vs. z-score vs. robust
- **1-SE rule regression** — α óptimo parsimonioso
- **Uncertainty quantification** — IC predicción por inmueble y por localidad

## Métodos de simulación / muestreo

| Método | Uso | n |
|---|---|---|
| **Monte Carlo** (perturbación de pesos) | Estabilidad de ranking | 500–1,000 sims |
| **Saltelli sampling** (cuasi-aleatorio) | Índices Sobol | n × (p+2) |
| **Bootstrap** (no paramétrico) | IC de ΔR², ΔAIC | 1,000 réplicas |

## Endpoints expuestos

| Endpoint | Métrica |
|---|---|
| `GET /analytics/regression/diagnostics/{tipo}` | R², RMSE, MAE, CV, IAAO, VIF |
| `GET /analytics/validation/nested` | Comparación modelos anidados |
| `GET /analytics/validation/commonality` | Descomposición de varianza |
| `GET /analytics/validation/ranking-stability` | Monte Carlo ranking |
| `GET /analytics/validation/cv-comparison` | CV aleatorio vs. espacial |
| `GET /analytics/validation/bootstrap` | IC bootstrap |
| `GET /analytics/validation/ramsey` | Ramsey RESET |
| `GET /analytics/validation/specification` | M1–M5 |
| `GET /analytics/validation/mispricing` | Matriz 2×2 |
| `GET /analytics/validation/decision-matrix` | Cuadrantes accionables |
| `GET /analytics/sobol/iurb` | Índices Sobol |
| `GET /analytics/uncertainty/{id}` | IC por inmueble |
| `GET /analytics/uncertainty/locality/{nombre}` | IC por localidad |
| `GET /analytics/dbscan/compare/{tipo}` | Outliers |
| `GET /analytics/ahp-pca/hybrid` | Pesos AHP-PCA |
| `GET /analytics/normalization/compare` | Comparación de normalizaciones |
| `GET /analytics/gravity/calibration` | β del gravity model |
