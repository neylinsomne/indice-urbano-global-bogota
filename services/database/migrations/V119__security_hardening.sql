-- =============================================
-- V119: Hardening de seguridad
-- =============================================
-- Objetivo: reducir el blast radius si la API es comprometida.
--
-- 1. Crear `app_user` con permisos limitados al schema `iug`
--    (la API deja de correr como superuser).
-- 2. REVOKE de funciones peligrosas que permiten escape al host.
-- 3. Garantizar que las extensiones de bajo nivel solo se carguen
--    desde el rol postgres (admin operacional).
--
-- Aplica idempotentemente (usa DO blocks con checks).
-- =============================================

-- ─── 1. Crear app_user (no superuser, no createdb, no createrole) ───
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION
            NOBYPASSRLS
            CONNECTION LIMIT 50
            PASSWORD 'TEMP_PLACEHOLDER_REPLACE_BY_INIT_SCRIPT';
        COMMENT ON ROLE app_user IS
            'Rol limitado usado por la API FastAPI. Solo puede operar dentro del schema iug.';
    END IF;
END$$;

-- ─── 2. Permisos en schema iug ───
GRANT USAGE ON SCHEMA iug TO app_user;

-- SELECT en todas las tablas existentes y futuras (catálogos, vistas, etc.)
GRANT SELECT ON ALL TABLES IN SCHEMA iug TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA iug GRANT SELECT ON TABLES TO app_user;

-- INSERT/UPDATE/DELETE solo en tablas operativas (whitelist explícito).
-- Aplicamos uno por uno con DO block: si una tabla no existe en este
-- entorno (puede pasar entre dev/prod), saltamos sin tirar el GRANT
-- atómico completo.
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'users',
            'pdf_usage',
            'acm_reports',
            'acm_reports_cache',
            'email_otp',
            'password_reset',
            'refresh_tokens',
            'audit_log'
        ])
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'iug' AND tablename = tbl
        ) THEN
            EXECUTE format('GRANT INSERT, UPDATE, DELETE ON iug.%I TO app_user', tbl);
        END IF;
    END LOOP;
END$$;

-- Permisos sobre secuencias (necesarios para INSERT con SERIAL)
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA iug TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA iug GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_user;

-- EXECUTE en funciones del proyecto (todas en schema iug)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA iug TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA iug GRANT EXECUTE ON FUNCTIONS TO app_user;

-- ─── 3. Permisos para extensiones espaciales (PostGIS, pgvector) ───
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO app_user';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_user';
        EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user';
    END IF;
END$$;

-- ─── 4. REVOKE de capacidades peligrosas ───
-- Estas funciones permiten leer archivos del filesystem, ejecutar
-- comandos del SO, escribir archivos arbitrarios, etc. Revocamos
-- para PUBLIC y específicamente para app_user.

-- Lectura de archivos del servidor (filesystem del container)
REVOKE EXECUTE ON FUNCTION pg_read_file(text)                      FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_read_file(text, bigint, bigint)      FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_read_binary_file(text)               FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_read_binary_file(text, bigint, bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_ls_dir(text)                         FROM PUBLIC;

-- Escritura de archivos (large objects)
REVOKE EXECUTE ON FUNCTION lo_export(oid, text)                    FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION lo_import(text)                         FROM PUBLIC;

-- Aseguramos que app_user no los tenga heredados
DO $$
DECLARE
    fn_signature text;
BEGIN
    FOR fn_signature IN
        SELECT 'pg_read_file(text)'
        UNION ALL SELECT 'pg_read_file(text, bigint, bigint)'
        UNION ALL SELECT 'pg_read_binary_file(text)'
        UNION ALL SELECT 'pg_read_binary_file(text, bigint, bigint)'
        UNION ALL SELECT 'pg_ls_dir(text)'
        UNION ALL SELECT 'lo_export(oid, text)'
        UNION ALL SELECT 'lo_import(text)'
    LOOP
        BEGIN
            EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM app_user', fn_signature);
        EXCEPTION WHEN undefined_function OR insufficient_privilege THEN
            -- Si la función no existe en esta versión de Postgres, ignoramos
            NULL;
        END;
    END LOOP;
END$$;

-- ─── 5. Deny por defecto de roles de sistema peligrosos ───
-- app_user NO debe tener ninguno de estos roles
REVOKE pg_read_server_files       FROM app_user;
REVOKE pg_write_server_files      FROM app_user;
REVOKE pg_execute_server_program  FROM app_user;
REVOKE pg_read_all_data           FROM app_user;
REVOKE pg_write_all_data          FROM app_user;

-- ─── 6. Audit log (tabla auxiliar para registrar eventos críticos) ───
CREATE TABLE IF NOT EXISTS iug.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id    INT REFERENCES iug.users(id) ON DELETE SET NULL,
    actor_email VARCHAR(255),
    action      VARCHAR(64) NOT NULL,
    resource    VARCHAR(128),
    resource_id VARCHAR(128),
    ip_address  INET,
    user_agent  TEXT,
    metadata    JSONB,
    success     BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_audit_log_actor      ON iug.audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_occurred   ON iug.audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action     ON iug.audit_log(action);

GRANT INSERT, SELECT ON iug.audit_log         TO app_user;
GRANT USAGE, SELECT ON SEQUENCE iug.audit_log_id_seq TO app_user;

-- ─── 7. Verificación final (comentarios para auditoría) ───
COMMENT ON SCHEMA iug IS
    'Schema principal de la aplicación. La API se conecta como app_user '
    '(no superuser). Solo postgres puede modificar estructura.';
