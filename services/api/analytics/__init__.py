"""
Modulo analytics: Implementacion de las 11 mejoras estadisticas
propuestas en docs/tesis_definitivos/mejoras_estadisticas.tex.

Cada submodulo es independiente y NO modifica el pipeline en
produccion. Expone resultados via endpoints REST en
services/api/routers/analytics.py para evaluacion comparativa.

Mejoras implementadas:
1. gravity_gaussian      - Funcion gaussiana unificada (vs Manhattan/inverso)
2. regression_diagnostics - VIF + Moran I + residuos
3. iurb_weights          - Pesos empiricos via correlacion con precio
4. ahp_pca_hybrid        - Combinacion AHP (juicio) + PCA (datos)
5. dbscan_adaptive       - Auto-tune eps via k-distance graph
6. sensitivity_sobol     - Indices Sobol para descomposicion de varianza
7. normalization_unified - Min-max global vs PERCENT_RANK por tipo
8. regression_1se        - Regla 1-SE para parsimonia en seleccion
9. uncertainty           - Bandas de confianza para indicadores
"""
__version__ = "1.0.0"
