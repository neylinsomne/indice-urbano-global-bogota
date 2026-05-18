-- =============================================
-- V109: Detección de outliers post-scraping (DBSCAN)
-- =============================================

-- Flag en tabla principal
ALTER TABLE iug.inmueble
    ADD COLUMN is_outlier BOOLEAN NOT NULL DEFAULT FALSE;

-- Log de ejecuciones de clasificación
CREATE TABLE iug.outlier_run (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    total_analyzed  INTEGER DEFAULT 0,
    total_outliers  INTEGER DEFAULT 0,
    params          JSONB,
    triggered_by    INTEGER REFERENCES iug.users(id)
);

-- Detalle por inmueble: por qué fue clasificado como outlier
CREATE TABLE iug.inmueble_outlier (
    id_inmueble     BIGINT PRIMARY KEY REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES iug.outlier_run(id) ON DELETE SET NULL,
    outlier_labels  JSONB NOT NULL,
    review_status   VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (review_status IN ('pending', 'confirmed', 'reinstated')),
    reviewed_by     INTEGER REFERENCES iug.users(id),
    reviewed_at     TIMESTAMPTZ,
    classified_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_inmueble_is_outlier ON iug.inmueble(is_outlier) WHERE is_outlier = TRUE;
CREATE INDEX idx_outlier_review_status ON iug.inmueble_outlier(review_status);
CREATE INDEX idx_outlier_run_id ON iug.inmueble_outlier(run_id);
