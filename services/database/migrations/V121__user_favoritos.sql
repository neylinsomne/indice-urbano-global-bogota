-- =============================================
-- V121 — Favoritos de usuario
-- =============================================
-- El usuario puede marcar inmuebles que le interesan desde el chatbot
-- y desde el dashboard. La tabla guarda un PIN ligero (sin payload
-- completo del inmueble — esos datos se rehidratan al hacer SELECT
-- con JOIN). Permite añadir una nota libre por inmueble y agrupar
-- por "carpetas" lógicas para clientes (p.ej. "inversión 2026",
-- "vivienda familiar").

CREATE TABLE IF NOT EXISTS iug.user_favoritos (
    id              BIGSERIAL    PRIMARY KEY,
    user_id         INT          NOT NULL
                                  REFERENCES iug.users(id) ON DELETE CASCADE,
    id_inmueble     INT          NOT NULL
                                  REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    nota            TEXT,
    carpeta         VARCHAR(60)  DEFAULT 'default',
    snapshot_iug    NUMERIC(4,2),     -- IUG en el momento del guardado
    snapshot_precio BIGINT,           -- precio en el momento del guardado
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, id_inmueble)
);

CREATE INDEX IF NOT EXISTS idx_favoritos_user      ON iug.user_favoritos(user_id, carpeta, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_favoritos_inmueble  ON iug.user_favoritos(id_inmueble);

COMMENT ON TABLE iug.user_favoritos IS
    'Inmuebles guardados por el usuario desde el chatbot o el dashboard.';
COMMENT ON COLUMN iug.user_favoritos.snapshot_iug IS
    'IUG en el instante del guardado — útil para detectar cambios después.';
COMMENT ON COLUMN iug.user_favoritos.carpeta IS
    'Etiqueta libre para que el usuario agrupe sus favoritos.';

-- Grants para app_user
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        EXECUTE 'GRANT INSERT, SELECT, UPDATE, DELETE ON iug.user_favoritos TO app_user';
        EXECUTE 'GRANT USAGE ON SEQUENCE iug.user_favoritos_id_seq TO app_user';
    END IF;
END $$;
