-- V118: Persistir metricas de validacion estadistica
-- Cierra el gap donde metricas se calculan pero no llegan al cliente

-- ============================================
-- 1. Spatial CV en regression_market_summary
-- ============================================
ALTER TABLE iug.regression_market_summary
    ADD COLUMN IF NOT EXISTS spatial_cv_rmse NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS spatial_cv_r2 NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS spatial_leakage_ratio NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS spatial_leakage_flag BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS spatial_n_groups INTEGER;

COMMENT ON COLUMN iug.regression_market_summary.spatial_cv_rmse IS
'RMSE de cross-validation espacial (GroupKFold por localidad)';
COMMENT ON COLUMN iug.regression_market_summary.spatial_leakage_flag IS
'TRUE si el modelo memoriza barrios en vez de aprender patrones (leakage > 15%)';

-- ============================================
-- 2. Spatial CV en run_history (auditoria)
-- ============================================
ALTER TABLE iug.regression_run_history
    ADD COLUMN IF NOT EXISTS spatial_cv_rmse NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS spatial_leakage_ratio NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS spatial_leakage_flag BOOLEAN;

-- ============================================
-- 3. Validacion PCA en pca_pesos_tipo
-- ============================================
ALTER TABLE iug.pca_pesos_tipo
    ADD COLUMN IF NOT EXISTS kmo NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS bartlett_p NUMERIC(10, 8),
    ADD COLUMN IF NOT EXISTS metodo_usado VARCHAR(20) DEFAULT 'pca',
    ADD COLUMN IF NOT EXISTS advertencias JSONB;

COMMENT ON COLUMN iug.pca_pesos_tipo.kmo IS
'Indice Kaiser-Meyer-Olkin (>0.60 aceptable, >0.80 bueno)';
COMMENT ON COLUMN iug.pca_pesos_tipo.metodo_usado IS
'pca, pca_robusto, varianza, o promedio (fallback si PCA no valido)';

-- ============================================
-- 4. Validacion PCA en pca_loadings_dimension
-- ============================================
ALTER TABLE iug.pca_loadings_dimension
    ADD COLUMN IF NOT EXISTS kmo NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS bartlett_p NUMERIC(10, 8),
    ADD COLUMN IF NOT EXISTS metodo_usado VARCHAR(20) DEFAULT 'pca',
    ADD COLUMN IF NOT EXISTS advertencias JSONB;
