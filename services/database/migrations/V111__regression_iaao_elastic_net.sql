-- ============================================================
-- V111: Upgrade regression con Elastic Net + metricas IAAO
-- Agrega elastic_net al CHECK de model_type,
-- columnas IAAO en market_summary, y best_model_predictions.
-- ============================================================

-- 1. Ampliar CHECK de model_type para incluir elastic_net
ALTER TABLE iug.regression_model DROP CONSTRAINT IF EXISTS regression_model_model_type_check;
ALTER TABLE iug.regression_model ADD CONSTRAINT regression_model_model_type_check
    CHECK (model_type IN ('ols','ridge','lasso','elastic_net','quantile_25','quantile_50','quantile_75'));

-- 2. Agregar columna que indica cual modelo genero la prediccion
ALTER TABLE iug.regression_prediction
    ADD COLUMN IF NOT EXISTS best_model VARCHAR(20) DEFAULT 'ols';

-- 3. Agregar metricas IAAO al resumen de mercado
ALTER TABLE iug.regression_market_summary
    ADD COLUMN IF NOT EXISTS r2_elastic_net  NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS iaao_cod        NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS iaao_prd        NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS iaao_prb        NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS iaao_median_ratio NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS iaao_cod_ok     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS iaao_prd_ok     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS iaao_level_ok   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS active_model    VARCHAR(20) DEFAULT 'ols';
