-- ============================================================
-- V112: Historial de corridas de regresion
-- Cada entrenamiento genera un registro inmutable aqui.
-- Permite analisis de estabilidad de coeficientes en el tiempo
-- (coefficient CV), Lasso path, cross-model consensus, y auditoria
-- de triggers (por que se re-entreno).
-- ============================================================

CREATE TABLE IF NOT EXISTS iug.regression_run_history (
    id                      BIGSERIAL PRIMARY KEY,
    run_uuid                UUID NOT NULL DEFAULT gen_random_uuid(),
    tipo_inmueble           VARCHAR(50) NOT NULL,
    model_type              VARCHAR(30) NOT NULL,  -- ols | ridge | lasso | elastic_net
    trained_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Contexto del entrenamiento
    n_samples               INTEGER NOT NULL,
    n_new_since_last        INTEGER,          -- nuevos registros desde la corrida anterior
    trigger_reason          VARCHAR(50) DEFAULT 'manual',
                            -- 'manual' | 'psi_drift' | 'iaao_drift' | 'scheduled' | 'auto_post_scrape'
    admin_id                INTEGER REFERENCES iug.users(id) ON DELETE SET NULL,

    -- Metricas de rendimiento (CV-RMSE es la metrica primaria SOTA)
    r2                      NUMERIC(6,4),
    cv_rmse_mean            NUMERIC(10,6),
    cv_rmse_std             NUMERIC(10,6),
    cv_r2_mean              NUMERIC(6,4),
    cv_r2_std               NUMERIC(6,4),
    rmse                    NUMERIC(10,4),
    mae                     NUMERIC(10,4),
    alpha                   NUMERIC(14,8),    -- NULL para OLS
    l1_ratio                NUMERIC(6,4),     -- solo ElasticNet

    -- Coeficientes estandarizados (clave para analisis de estabilidad)
    -- Cada key = nombre del feature, value = beta estandarizado
    coefficients            JSONB NOT NULL,

    -- Metricas IAAO (solo para el best_model de cada corrida)
    iaao_cod                NUMERIC(6,2),
    iaao_prd                NUMERIC(6,4),
    iaao_prb                NUMERIC(6,4),
    iaao_median_ratio       NUMERIC(6,4),
    iaao_cod_ok             BOOLEAN,
    iaao_prd_ok             BOOLEAN,
    iaao_level_ok           BOOLEAN,

    -- Features activas segun Lasso (las que NO fueron zeroed a CV alpha)
    -- Lista de nombres de features con coeficiente != 0
    lasso_active_features   JSONB,

    -- Cross-model consensus para esta corrida (calculado en Python)
    -- Objeto: {feature: {all_active, sign_agreement, consensus, n_models_active}}
    consensus               JSONB,

    -- Senales de drift en el momento del trigger (para auditoria)
    psi_estrato             NUMERIC(6,4),
    psi_area                NUMERIC(6,4),
    psi_precio_m2           NUMERIC(6,4),

    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_hist_tipo_model
    ON iug.regression_run_history(tipo_inmueble, model_type);
CREATE INDEX IF NOT EXISTS idx_run_hist_trained_at
    ON iug.regression_run_history(trained_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_hist_tipo_at
    ON iug.regression_run_history(tipo_inmueble, trained_at DESC);
