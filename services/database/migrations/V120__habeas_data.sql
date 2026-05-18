-- =============================================
-- V120 — Hábeas Data (Ley 1581 de 2012, Decreto 1377 de 2013)
-- =============================================
--
-- Añade los campos PII que pide el formulario de registro y crea una
-- tabla inmutable de consentimientos. La idea es poder demostrar ante
-- la SIC, en cualquier momento, qué autorizó cada usuario, cuándo, con
-- qué versión de política, y desde qué IP.
--
-- Nota de cifrado: contraseñas siguen con bcrypt (en password_hash).
-- Los campos PII (nombre, apellido, teléfono, cédula) se guardan en
-- claro a nivel de columna pero protegidos por:
--   1. TLS 1.3 en tránsito (Cloudflare → nginx → app)
--   2. Encriptación en disco del volumen Docker (postgres-data)
--   3. REVOKE en pg_read_server_files / lo_export de V119
--   4. app_user role no-superuser sin permisos de filesystem
--
-- Si en el futuro quieres cifrado a nivel de columna (AES-256 con pgcrypto),
-- la migración siguiente puede convertir cada columna a bytea y wrappers
-- view + INSTEAD OF triggers. Por ahora el threat model no lo justifica.

-- ── 1. Campos PII en users ────────────────────────────────
ALTER TABLE iug.users
    ADD COLUMN IF NOT EXISTS nombre        VARCHAR(80),
    ADD COLUMN IF NOT EXISTS apellido      VARCHAR(80),
    ADD COLUMN IF NOT EXISTS telefono      VARCHAR(20),
    ADD COLUMN IF NOT EXISTS cedula        VARCHAR(20),
    ADD COLUMN IF NOT EXISTS pais          VARCHAR(40)  DEFAULT 'Colombia',
    ADD COLUMN IF NOT EXISTS ciudad        VARCHAR(60)  DEFAULT 'Bogotá';

COMMENT ON COLUMN iug.users.cedula
    IS 'Documento de identidad. Opcional. Usado para cotizaciones ACM con valor probatorio.';
COMMENT ON COLUMN iug.users.telefono
    IS 'Formato libre. Sólo se usa con consentimiento explícito (col_marketing).';

-- ── 2. Tabla de log inmutable de consentimientos ───────────
-- Una fila por evento de consentimiento (registro, cambio de preferencia,
-- revocación). Nunca se actualiza una fila existente: cada cambio inserta
-- una nueva. Así queda trazabilidad histórica completa.
CREATE TABLE IF NOT EXISTS iug.consent_log (
    id                  BIGSERIAL   PRIMARY KEY,
    user_id             INT         REFERENCES iug.users(id) ON DELETE SET NULL,
    email               VARCHAR(255) NOT NULL,
    evento              VARCHAR(40)  NOT NULL
                        CHECK (evento IN ('registro', 'actualizacion', 'revocacion')),
    politica_version    VARCHAR(20)  NOT NULL,
    autoriza_tratamiento  BOOLEAN  NOT NULL,
    autoriza_marketing    BOOLEAN  NOT NULL DEFAULT FALSE,
    autoriza_terceros     BOOLEAN  NOT NULL DEFAULT FALSE,
    ip_origen           INET,
    user_agent          TEXT,
    locale              VARCHAR(20),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consent_log_user        ON iug.consent_log(user_id);
CREATE INDEX IF NOT EXISTS idx_consent_log_email       ON iug.consent_log(email);
CREATE INDEX IF NOT EXISTS idx_consent_log_created     ON iug.consent_log(created_at DESC);

COMMENT ON TABLE iug.consent_log IS
    'Registro inmutable de consentimientos hábeas data (Ley 1581/2012). '
    'Una fila por evento. Nunca se actualiza ni borra.';

-- Constraint: nadie debería poder UPDATE o DELETE filas históricas.
-- Lo dejamos como REVOKE para app_user (admin postgres sí puede).
REVOKE UPDATE, DELETE ON iug.consent_log FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        EXECUTE 'GRANT INSERT, SELECT ON iug.consent_log TO app_user';
        EXECUTE 'GRANT USAGE ON SEQUENCE iug.consent_log_id_seq TO app_user';
    END IF;
END $$;

-- ── 3. Vista de utilidad para auditoría rápida ──────────────
CREATE OR REPLACE VIEW iug.v_consent_actual AS
SELECT DISTINCT ON (cl.email)
    cl.email,
    cl.user_id,
    cl.politica_version,
    cl.autoriza_tratamiento,
    cl.autoriza_marketing,
    cl.autoriza_terceros,
    cl.evento  AS ultimo_evento,
    cl.created_at AS ultimo_evento_at
FROM iug.consent_log cl
ORDER BY cl.email, cl.created_at DESC;

COMMENT ON VIEW iug.v_consent_actual IS
    'Estado actual del consentimiento de cada usuario (última fila por email).';
