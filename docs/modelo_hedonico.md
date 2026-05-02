# Modelo hedónico y validación

> Para resultados completos, consultar Capítulo 4 (modelo hedónico) y Capítulo 5 (validez de uso) de la tesis.

## Especificación

Variable dependiente: ln(Precio/m²)

Predictores:
- Estructurales: área, habitaciones, baños, área construida, ratio baños/habitaciones.
- Vecindario: estrato.
- Localización: dummies de localidad / barrio.

## Cuatro estimadores

| Modelo | Regularización | Uso |
|---|---|---|
| OLS | Ninguna | Baseline interpretable |
| Ridge | L2 (α por CV) | Estabilidad ante multicolinealidad |
| Lasso | L1 (α por CV) | Selección de variables |
| Elastic Net | L1 + L2 (α y l1_ratio por CV) | Compromiso entre los dos |

## Validación cruzada espacial

`GroupKFold` por localidad (no aleatorio) para evitar **leakage espacial**: inmuebles de la misma localidad nunca caen en folds distintos.

**Leakage ratio:**

$$
\text{Leakage} = \frac{\text{RMSE}_{espacial} - \text{RMSE}_{aleatorio}}{\text{RMSE}_{aleatorio}}
$$

Si > 15% → advertencia de que el modelo puede estar memorizando efectos de barrio.

## Resultados publicados

| Tipo | Mejor modelo | n | R² | Top feature |
|---|---|---|---|---|
| Apartamento | Ridge | 1,669 | 0.4242 | Estrato (26.8%) |
| Casa | Lasso | 1,679 | 0.4926 | Estrato (44.9%) |

R² bajo es **honesto**: refleja la dispersión real del mercado. COD entre 21-28% (IAAO acepta 5-15%) confirma que dos inmuebles estructuralmente idénticos pueden diferir 30%+ por factores no observables. **Esa varianza residual es donde el IUG aporta lectura complementaria.**

## Métricas IAAO

| Métrica | Apartamento | Casa | Aceptable IAAO |
|---|---|---|---|
| COD (%) | 21.25 | 27.57 | 5–15 |
| PRD | 1.078 | 1.354 | 0.98–1.03 |
| PRB | -0.588 | -0.526 | ±0.05 |
| Median ratio | 1.004 | 1.028 | 0.90–1.10 |

Los ratios medianos ≈ 1.00 confirman ausencia de sesgo. Los COD elevados confirman dispersión estructural.

## Protocolo de 11 pruebas estadísticas (Capítulo 5)

### Bondad de ajuste y descomposición

1. **Modelos anidados** — ΔR² = +0.053 a favor de los subíndices vs. IUG agregado
2. **Análisis de comunalidad** — varianza común = 0.0% → ortogonalidad confirmada
3. **Estabilidad de ranking** (Monte Carlo, ±20% pesos, 1,000 sims) — ρ = 0.995, 0% zonas se mueven > 5 posiciones
4. **CV espacial** — leakage controlado (<15%)

### Robustez

5. **Bootstrap** (1,000 réplicas) — IC 95% de ΔR² = [0.039, 0.064], excluye cero
6. **Ramsey RESET** — forma funcional lineal insuficiente (p < 10⁻²⁰⁰)
7. **Comparación de especificaciones** — M5 con log(área) eleva R² de 0.55 a 0.73

### Validez convergente y de uso

8. **Subgrupos** — CV del R² por localidad = 0.13 (modelo homogéneo)
9. **AUC clasificador estrato** — 0.480 (azar, esperado por hipótesis de ortogonalidad)
10. **Mann-Whitney Q4 vs Q1** — discriminación de mispricing (p = 0.0007)
11. **KS comprar vs conservar** — distribuciones distintas (p < 10⁻³⁷)

## Matriz 2×2 de decisión

|  | Subvalorado | Sobrevalorado |
|---|---|---|
| **IUG alto** | 🟢 COMPRAR (30.7%) | 🟡 CONSERVAR (19.3%) |
| **IUG bajo** | 🔴 EVITAR (25.3%) | 🟠 VENDER (24.7%) |

El cuadrante COMPRAR concentra el 30.7% del mercado con precio/m² 37% inferior al cuadrante CONSERVAR. **El 55.4% del mercado se distribuye en cuadrantes accionables.**
