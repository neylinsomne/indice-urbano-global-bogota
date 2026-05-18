-- =============================================
-- V108: Cache de reportes ACM generados
-- =============================================
-- Guarda el JSON completo del ACM para no regenerar ni descontar
-- del límite diario si el usuario pide el mismo reporte.
-- Expiración: free = 1 día, premium/admin = 30 días.

CREATE TABLE iug.acm_reports (
    id            SERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES iug.users(id) ON DELETE CASCADE,
    inmueble_id   INT NOT NULL,
    metodo        VARCHAR(20) NOT NULL CHECK (metodo IN ('clasico', 'dbscan')),
    data          JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, inmueble_id, metodo)
);

CREATE INDEX idx_acm_reports_lookup
    ON iug.acm_reports(user_id, inmueble_id, metodo);

CREATE INDEX idx_acm_reports_expiry
    ON iug.acm_reports(expires_at);
