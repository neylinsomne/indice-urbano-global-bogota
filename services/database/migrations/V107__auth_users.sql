-- =============================================
-- V107: Sistema de autenticación - Usuarios y uso de PDFs
-- =============================================

-- Tabla de usuarios
CREATE TABLE iug.users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'free'
                    CHECK (role IN ('admin', 'premium', 'free')),
    daily_pdf_limit INT NOT NULL DEFAULT 2,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Conteo diario de uso de PDFs por usuario
CREATE TABLE iug.pdf_usage (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES iug.users(id) ON DELETE CASCADE,
    usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    count       INT NOT NULL DEFAULT 0,
    UNIQUE(user_id, usage_date)
);

CREATE INDEX idx_pdf_usage_user_date ON iug.pdf_usage(user_id, usage_date);

-- NOTA DE SEGURIDAD (importante):
--
-- Esta migración originalmente sembraba un admin con password 'admin123'.
-- Eso es un riesgo de seguridad serio porque el hash bcrypt queda en el
-- repositorio público y permite a un atacante crackearlo offline.
--
-- En su lugar, el admin se siembra mediante el script
--   services/database/bootstrap_admin.sh
-- que toma el password del env var INITIAL_ADMIN_PASSWORD y lo hashea
-- antes de hacer INSERT. La migración aquí no inserta nada por defecto.
--
-- Si necesitas crear el admin tras un deploy nuevo:
--   1. Edita .env y define INITIAL_ADMIN_PASSWORD=<password fuerte>
--   2. Ejecuta: docker compose run --rm postgres bash /docker-entrypoint-initdb.d/bootstrap_admin.sh
--   o via psql manualmente (ver SECURITY.md).
