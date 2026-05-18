"""
Tests unitarios para el modulo analytics.

Cada test valida que la metodologia produce resultados con la
estructura correcta. NO requieren conexion a la BD; usan datos
sinteticos.

Ejecutar: pytest services/api/tests/test_analytics.py -v
"""
import sys
import math
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pytest

from analytics import (
    gravity_gaussian,
    regression_diagnostics,
    iurb_weights,
    ahp_pca_hybrid,
    dbscan_adaptive,
    sensitivity_sobol,
    normalization_unified,
    regression_1se,
    uncertainty,
)


# ============================================================
# 1. Gravedad gaussiana
# ============================================================

class TestGravityGaussian:

    def test_calibrar_sigma_para_radio_800(self):
        """Para radio=800, sigma debe ser ~327m (5% utilidad en r)."""
        sigma = gravity_gaussian.calibrar_sigma(800.0)
        assert 320 < sigma < 335
        # Verificar f(800) ~ 0.05
        assert abs(gravity_gaussian.gauss_decay(800, sigma) - 0.05) < 0.001

    def test_gauss_decay_en_zero(self):
        """f(0) debe ser 1."""
        assert gravity_gaussian.gauss_decay(0, 100) == 1.0

    def test_gauss_decay_decrece(self):
        """f es monotonicamente decreciente."""
        sigma = 327
        valores = [gravity_gaussian.gauss_decay(d, sigma) for d in [0, 100, 500, 1000]]
        for i in range(len(valores) - 1):
            assert valores[i] > valores[i + 1]

    def test_manhattan_decay_acotado(self):
        """Manhattan en r=0."""
        assert gravity_gaussian.manhattan_decay(0, 800) == 1.0
        assert gravity_gaussian.manhattan_decay(800, 800) == 0.0
        assert gravity_gaussian.manhattan_decay(1000, 800) == 0.0

    def test_inverso_decay_piso(self):
        """1/d con piso."""
        # En d=50 (piso), valor = 1/50 = 0.02
        assert abs(gravity_gaussian.inverso_decay(50, piso_m=50) - 0.02) < 1e-6
        # En d<50, deberia respetar el piso
        assert abs(gravity_gaussian.inverso_decay(10, piso_m=50) - 0.02) < 1e-6

    def test_tabla_calibracion_completa(self):
        """Tabla incluye las 9 capas."""
        tabla = gravity_gaussian.tabla_calibracion_sigma()
        assert len(tabla) == 9
        nombres = [t['capa'] for t in tabla]
        assert 'sitp' in nombres
        assert 'transmilenio' in nombres
        assert 'metro' in nombres


# ============================================================
# 4. Diagnosticos regresion
# ============================================================

class TestRegressionDiagnostics:

    def setup_method(self):
        np.random.seed(42)
        n = 200
        # X correlated: x2 = 2*x1 + noise
        self.x1 = np.random.normal(0, 1, n)
        self.x2 = 2 * self.x1 + np.random.normal(0, 0.5, n)
        self.x3 = np.random.normal(0, 1, n)
        self.X = np.column_stack([self.x1, self.x2, self.x3])
        self.y = self.x1 + self.x3 + np.random.normal(0, 0.5, n)
        self.coords = np.random.uniform(0, 1, (n, 2))

    def test_vif_detecta_multicolinealidad(self):
        """x1 y x2 estan correlacionadas (r~0.97), VIF debe ser >5."""
        vif = regression_diagnostics.compute_vif(
            self.X, ['x1', 'x2', 'x3'],
        )
        assert vif['x1']['vif'] > 5
        assert vif['x2']['vif'] > 5
        assert vif['x3']['vif'] < 2

    def test_moran_residuos_aleatorios(self):
        """Residuos sin estructura espacial -> I cerca de 0."""
        residuos = np.random.normal(0, 1, len(self.coords))
        result = regression_diagnostics.moran_i_residuos(
            residuos, self.coords, k_vecinos=5,
        )
        # Bajo H0, |I| < 0.1 con alta probabilidad
        assert abs(result['I_moran']) < 0.3

    def test_shapiro_normal(self):
        """Datos normales -> p > 0.05."""
        np.random.seed(1)
        residuos = np.random.normal(0, 1, 100)
        result = regression_diagnostics.shapiro_wilk_residuos(residuos)
        assert result['normal'] is True

    def test_shapiro_no_normal(self):
        """Datos uniformes -> p < 0.05."""
        np.random.seed(2)
        residuos = np.random.uniform(-1, 1, 100)
        result = regression_diagnostics.shapiro_wilk_residuos(residuos)
        assert result['normal'] is False


# ============================================================
# 7. AHP-PCA hibrido
# ============================================================

class TestAHPPCAHybrid:

    def test_alpha_0_es_solo_pca(self):
        """alpha=0: pesos = PCA puro."""
        result = ahp_pca_hybrid.calcular_pesos_hibridos(0.0)
        # Verificar que los pesos respetan el ranking PCA
        pesos = result['pesos_hibridos']
        # Lesiones personales (PCA: 17.7%) deberia tener peso > 0
        assert pesos['lesiones_personales'] > 0.10

    def test_alpha_1_es_solo_ahp(self):
        """alpha=1: pesos = AHP puro."""
        result = ahp_pca_hybrid.calcular_pesos_hibridos(1.0)
        # Homicidios deberia ser dominante
        assert result['pesos_hibridos']['homicidios'] > 0.5

    def test_alpha_05_balance(self):
        """alpha=0.5: combinacion balanceada."""
        result = ahp_pca_hybrid.calcular_pesos_hibridos(0.5)
        pesos = result['pesos_hibridos']
        # Suma debe ser 1
        assert abs(sum(pesos.values()) - 1.0) < 0.001
        # Homicidios debe estar entre 0.13 (PCA) y 0.57 (AHP)
        assert 0.13 < pesos['homicidios'] < 0.57

    def test_alpha_invalido(self):
        with pytest.raises(ValueError):
            ahp_pca_hybrid.calcular_pesos_hibridos(1.5)
        with pytest.raises(ValueError):
            ahp_pca_hybrid.calcular_pesos_hibridos(-0.1)

    def test_sensibilidad_alpha(self):
        result = ahp_pca_hybrid.sensibilidad_alpha([0, 0.5, 1])
        assert 'series_por_delito' in result
        assert 'homicidios' in result['series_por_delito']


# ============================================================
# 12. DBSCAN adaptativo
# ============================================================

class TestDBSCANAdaptive:

    def test_k_distance_cluster_compacto(self):
        """Un cluster denso -> eps recomendado bajo."""
        np.random.seed(3)
        X = np.random.normal(0, 0.1, (100, 3))  # cluster muy compacto
        result = dbscan_adaptive.k_distance_graph(X, k=4)
        assert result['eps_recomendado'] < 1.0

    def test_k_distance_dispersos(self):
        """Datos dispersos -> eps mayor."""
        np.random.seed(4)
        X = np.random.uniform(0, 10, (100, 3))
        result = dbscan_adaptive.k_distance_graph(X, k=4)
        assert result['eps_recomendado'] > 0.5

    def test_isolation_forest_detecta_outliers(self):
        """Inyectar outliers obvios."""
        np.random.seed(5)
        X = np.vstack([
            np.random.normal(0, 1, (100, 3)),
            np.random.uniform(50, 100, (5, 3)),  # 5 outliers
        ])
        result = dbscan_adaptive.isolation_forest_outliers(X, contamination=0.05)
        # Debe detectar al menos los 5 outliers
        assert result['n_outliers_detectados'] >= 5


# ============================================================
# 15. Sobol
# ============================================================

class TestSobol:

    def test_saltelli_sample_dimensiones(self):
        A, B, AB = sensitivity_sobol.saltelli_sample(64, 5)
        assert A.shape == (64, 5)
        assert B.shape == (64, 5)
        assert len(AB) == 5
        assert all(ab.shape == (64, 5) for ab in AB)

    def test_normalizar_pesos(self):
        """Pesos normalizados deben sumar 1 y respetar minimo."""
        np.random.seed(6)
        raw = np.random.uniform(0, 1, (10, 5))
        norm = sensitivity_sobol.normalizar_pesos(raw)
        # Cada fila suma 1
        assert np.allclose(norm.sum(axis=1), 1.0)
        # Minimo respetado
        assert (norm >= 0.05 / 6).all()  # 0.05/(0.05*5) = 0.01666...

    def test_calcular_iurb_pesos_uniformes(self):
        """Con pesos uniformes 0.2, IURB = mean(X)."""
        np.random.seed(7)
        X = np.random.uniform(0, 5, (100, 5))
        pesos = np.ones((1, 5)) * 0.2
        iurb = sensitivity_sobol.calcular_iurb_con_pesos(X, pesos)
        assert iurb.shape == (1,)
        assert abs(iurb[0] - X.mean()) < 0.01


# ============================================================
# 9. Normalizacion unificada
# ============================================================

class TestNormalizationUnified:

    def test_minmax_global_rango_correcto(self):
        np.random.seed(8)
        X = np.random.uniform(0, 5, (100, 3))
        X_norm = normalization_unified.normalizar_minmax_global(X)
        assert X_norm.min() >= 0
        assert X_norm.max() <= 5
        # Cada columna debe alcanzar 0 y 5
        for j in range(3):
            assert abs(X_norm[:, j].min()) < 0.01
            assert abs(X_norm[:, j].max() - 5.0) < 0.01

    def test_ecdf_gaussiano_simetrico(self):
        np.random.seed(9)
        X = np.random.exponential(1, (200, 2))  # asimetrico
        X_norm = normalization_unified.normalizar_ecdf_gaussiano(X)
        # Despues de ECDF->normal, sesgo cercano a 0
        from scipy import stats as sp_stats
        for j in range(2):
            assert abs(sp_stats.skew(X_norm[:, j])) < 0.5

    def test_percent_rank_uniforme(self):
        np.random.seed(10)
        X = np.random.exponential(1, (100, 1))
        X_norm = normalization_unified.normalizar_percent_rank_global(X)
        # Debe ser ~uniforme [0, 5]
        assert abs(X_norm.mean() - 2.5) < 0.2


# ============================================================
# 11. Regla 1-SE
# ============================================================

class TestRegla1SE:

    def test_seleccion_simple_modelo(self):
        modelos = {
            'a': {'cv_rmse_mean': 0.50, 'cv_rmse_std': 0.05, 'n_features': 13},
            'b': {'cv_rmse_mean': 0.51, 'cv_rmse_std': 0.05, 'n_features': 5},
            'c': {'cv_rmse_mean': 0.55, 'cv_rmse_std': 0.05, 'n_features': 3},
        }
        result = regression_1se.regla_1se(modelos)
        # Mejor por CV-RMSE: 'a' (0.50)
        assert result['mejor_por_cv_rmse'] == 'a'
        # Umbral 1-SE: 0.50 + 0.05 = 0.55
        # 'b' (0.51) y 'c' (0.55) entran. Mas simple: 'c' (3 features)
        assert result['mejor_por_1se'] == 'c'

    def test_score_multi_criterio(self):
        modelos = {
            'simple': {'cv_rmse_mean': 0.55, 'cv_rmse_std': 0.02, 'n_features': 3},
            'complejo': {'cv_rmse_mean': 0.50, 'cv_rmse_std': 0.10, 'n_features': 13},
        }
        # Con lambda alto a parsimonia y estabilidad, simple gana
        result = regression_1se.score_multi_criterio(
            modelos, lambda_parsimonia=0.5, lambda_estabilidad=2.0,
        )
        assert result['mejor_modelo'] == 'simple'


# ============================================================
# 14. Incertidumbre
# ============================================================

class TestUncertainty:

    def test_propagacion_lineal_independiente(self):
        sigmas = {'iacc': 0.3, 'iseg': 0.2, 'ihed': 0.1, 'idot': 0.15, 'ipnu': 0.05}
        result = uncertainty.propagacion_lineal_iurb(sigmas)
        # sigma_iurb = sqrt(sum (0.2 * sigma_k)^2)
        expected = math.sqrt(sum((0.20 * s) ** 2 for s in sigmas.values()))
        assert abs(result['sigma_iurb'] - expected) < 0.001

    def test_banda_gravedad_sin_pois(self):
        result = uncertainty.banda_confianza_gravedad(0, 0, 800)
        assert result['sigma_score'] == 0
        assert result['ic_95_lower'] == 0
        assert result['ic_95_upper'] == 0

    def test_banda_gravedad_con_pois(self):
        result = uncertainty.banda_confianza_gravedad(2.5, 10, 800, sigma_gps_m=10)
        # sigma_score > 0
        assert result['sigma_score'] > 0
        # IC es simetrico alrededor del score
        assert abs((result['ic_95_upper'] + result['ic_95_lower']) / 2 - 2.5) < 0.01


# ============================================================
# 10. IUG weights empiricos
# ============================================================

class TestIURBWeights:

    def setup_method(self):
        np.random.seed(11)
        self.X = np.random.uniform(0, 5, (200, 5))
        # y correlacionado con I_HED y I_PNU principalmente
        self.y = (0.3 * self.X[:, 2] + 0.5 * self.X[:, 4] +
                  np.random.normal(0, 0.5, 200))

    def test_correlation_weights_suma_1(self):
        result = iurb_weights.correlation_weights(self.X, self.y)
        assert abs(sum(result['pesos'].values()) - 1.0) < 0.01

    def test_regression_weights_suma_1(self):
        result = iurb_weights.regression_weights(self.X, self.y)
        assert abs(sum(result['pesos'].values()) - 1.0) < 0.01

    def test_pca_weights_suma_1(self):
        result = iurb_weights.pca_weights(self.X, self.y)
        assert abs(sum(result['pesos'].values()) - 1.0) < 0.01

    def test_correlation_identifica_relevantes(self):
        """ihed e ipnu deben tener pesos altos."""
        result = iurb_weights.correlation_weights(self.X, self.y)
        # ihed (idx 2) e ipnu (idx 4) deben superar 0.20
        pesos = result['pesos']
        assert pesos['ihed'] + pesos['ipnu'] > 0.5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
