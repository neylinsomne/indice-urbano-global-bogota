-- =====================================================
-- V106: Fix función y trigger de seguridad
-- =====================================================
-- Los archivos fix_seguridad_function.sql y fix_trigger_seguridad.sql
-- contenían correcciones al V21 pero no seguían la convención Flyway
-- (V{N}__nombre.sql), por lo que nunca fueron aplicadas.
-- Esta migración aplica ambas correcciones.

-- ============================================
-- 1. Fix calcular_seguridad_raw: aliases + rename masa_crimen_val
-- ============================================
CREATE OR REPLACE FUNCTION iug.calcular_seguridad_raw(p_geom geometry)
RETURNS TABLE(
    score_cai NUMERIC,
    score_crimen NUMERIC,
    score_sector NUMERIC,
    localidad TEXT,
    masa_crimen_val NUMERIC,
    en_sector BOOLEAN,
    num_cais INTEGER
) AS $$
DECLARE
    v_cai NUMERIC := 0;
    v_crimen NUMERIC := 0;
    v_sector NUMERIC := 0;
    v_localidad TEXT;
    v_masa NUMERIC;
    v_en_sector BOOLEAN := FALSE;
    v_num_cais INTEGER := 0;
BEGIN
    -- 1. CAI (Gravity-based, radio 800m)
    SELECT
        COALESCE(SUM(GREATEST(0, 1 - ST_Distance(
            ST_Transform(p_geom, 3116),
            ST_Transform(cai.geom, 3116)
        ) / 800)), 0),
        COUNT(*)
    INTO v_cai, v_num_cais
    FROM iug.cai_policia cai
    WHERE ST_DWithin(ST_Transform(p_geom, 3116), ST_Transform(cai.geom, 3116), 800);

    -- 2. Crimen (masa de la localidad) - alias 'c' para evitar ambigüedad
    SELECT c.masa_crimen, c.nombre_localidad
    INTO v_masa, v_localidad
    FROM iug.criminalidad_localidad c
    WHERE ST_Within(p_geom, c.geom)
    LIMIT 1;

    v_crimen := COALESCE(v_masa, 0);

    -- 3. Sector priorizado (proximity 0-200m)
    WITH nearest_sector AS (
        SELECT
            ST_Distance(
                ST_Transform(p_geom, 3116),
                ST_Transform(s.geom, 3116)
            ) as dist
        FROM iug.sector_priorizado s
        WHERE ST_DWithin(ST_Transform(p_geom, 3116), ST_Transform(s.geom, 3116), 200)
        ORDER BY dist
        LIMIT 1
    )
    SELECT
        CASE
            WHEN dist = 0 THEN 1.0
            ELSE GREATEST(0, 1 - dist/200)
        END,
        (dist = 0)
    INTO v_sector, v_en_sector
    FROM nearest_sector;

    v_sector := COALESCE(v_sector, 0);

    RETURN QUERY SELECT v_cai, v_crimen, v_sector, v_localidad, v_masa, v_en_sector, v_num_cais;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 2. Fix trigger: desempaquetado explícito de campos
-- ============================================
DROP TRIGGER IF EXISTS trg_inmueble_seguridad ON iug.inmueble;

CREATE OR REPLACE FUNCTION iug.trigger_calcular_seguridad()
RETURNS TRIGGER AS $$
DECLARE
    v_cai NUMERIC;
    v_crimen NUMERIC;
    v_sector NUMERIC;
    v_localidad TEXT;
    v_masa NUMERIC;
    v_en_sector BOOLEAN;
    v_num_cais INTEGER;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN

        -- Desempaquetado explícito (evita problemas con RECORD)
        SELECT
            score_cai, score_crimen, score_sector,
            localidad, masa_crimen_val, en_sector, num_cais
        INTO
            v_cai, v_crimen, v_sector,
            v_localidad, v_masa, v_en_sector, v_num_cais
        FROM iug.calcular_seguridad_raw(NEW.geom);

        INSERT INTO iug.indicador_seguridad_raw (
            id_inmueble, tipo_inmueble,
            score_cai_raw, score_crimen_raw, score_sector_raw,
            localidad_nombre, masa_crimen_localidad,
            en_sector_priorizado, cais_cercanos
        ) VALUES (
            NEW.id_inmueble, NEW.tipo_inmueble,
            v_cai, v_crimen, v_sector,
            v_localidad, v_masa, v_en_sector, v_num_cais
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_cai_raw = EXCLUDED.score_cai_raw,
            score_crimen_raw = EXCLUDED.score_crimen_raw,
            score_sector_raw = EXCLUDED.score_sector_raw,
            localidad_nombre = EXCLUDED.localidad_nombre,
            masa_crimen_localidad = EXCLUDED.masa_crimen_localidad,
            en_sector_priorizado = EXCLUDED.en_sector_priorizado,
            cais_cercanos = EXCLUDED.cais_cercanos,
            fecha_calculo = now();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inmueble_seguridad
AFTER INSERT OR UPDATE OF geom, tipo_inmueble ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trigger_calcular_seguridad();
