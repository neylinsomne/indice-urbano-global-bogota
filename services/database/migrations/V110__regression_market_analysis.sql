-- ============================================================
-- V110: Regression Market Analysis
-- Modelos de regresion (OLS, Ridge, Lasso, Quantile) por tipo,
-- predicciones por inmueble, y resumen de mercado agregado.
-- ============================================================

-- Modelos entrenados por (tipo_inmueble, model_type)
CREATE TABLE IF NOT EXISTS iug.regression_model (
    id              SERIAL PRIMARY KEY,
    tipo_inmueble   VARCHAR(50) NOT NULL,
    model_type      VARCHAR(20) NOT NULL
                    CHECK (model_type IN ('ols','ridge','lasso','quantile_25','quantile_50','quantile_75')),
    coefficients    JSONB NOT NULL,
    metrics         JSONB NOT NULL,
    n_samples       INTEGER NOT NULL,
    feature_names   JSONB NOT NULL,
    trained_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tipo_inmueble, model_type)
);

-- Prediccion por inmueble
CREATE TABLE IF NOT EXISTS iug.regression_prediction (
    id_inmueble         BIGINT PRIMARY KEY REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble       VARCHAR(50) NOT NULL,
    predicted_precio_m2 NUMERIC(14,2),
    actual_precio_m2    NUMERIC(14,2),
    market_ratio        NUMERIC(8,4),
    quantile_25_pm2     NUMERIC(14,2),
    quantile_75_pm2     NUMERIC(14,2),
    quantile_position   VARCHAR(20)
                        CHECK (quantile_position IN ('below_q25','within_iqr','above_q75')),
    lasso_top_features  JSONB,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Resumen agregado por tipo (para homepage)
CREATE TABLE IF NOT EXISTS iug.regression_market_summary (
    tipo_inmueble       VARCHAR(50) PRIMARY KEY,
    r2_ols              NUMERIC(5,4),
    r2_ridge            NUMERIC(5,4),
    r2_lasso            NUMERIC(5,4),
    cv_mean_ols         NUMERIC(5,4),
    best_model          VARCHAR(20),
    n_properties        INTEGER NOT NULL,
    n_overpriced        INTEGER DEFAULT 0,
    n_fair              INTEGER DEFAULT 0,
    n_underpriced       INTEGER DEFAULT 0,
    avg_market_ratio    NUMERIC(8,4),
    median_market_ratio NUMERIC(8,4),
    avg_q25_pm2         NUMERIC(14,2),
    avg_q75_pm2         NUMERIC(14,2),
    avg_predicted_pm2   NUMERIC(14,2),
    top_features        JSONB,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regpred_tipo ON iug.regression_prediction(tipo_inmueble);
CREATE INDEX IF NOT EXISTS idx_regpred_ratio ON iug.regression_prediction(market_ratio);
CREATE INDEX IF NOT EXISTS idx_regression_model_tipo ON iug.regression_model(tipo_inmueble);
