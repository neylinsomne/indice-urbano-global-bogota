-- V21: Indicador de Seguridad con Normalización 0-5
-- Componentes: CAI (positivo), Crimen (negativo), Sectores Priorizados (negativo)
-- Cada componente normalizado 0-5 usando min/max del dataset

-- ============================================
-- 1. TABLA: Pesos AHP para tipos de crimen
-- ============================================
CREATE TABLE IF NOT EXISTS iug.ahp_pesos_crimen (
    id SERIAL PRIMARY KEY,
    tipo_delito VARCHAR(50) UNIQUE,
    peso_ahp NUMERIC(5, 4),  -- Suma = 1.0
    descripcion TEXT,
    version INTEGER DEFAULT 1,
    fecha_actualizacion TIMESTAMP DEFAULT now()
);

-- Inicializar con pesos calculados por AHP
INSERT INTO iug.ahp_pesos_crimen (tipo_delito, peso_ahp, descripcion) VALUES
('homicidios', 0.5660, 'Máxima gravedad - impacto letal'),
('delitos_sexuales', 0.2670, 'Alta gravedad - violencia de género'),
('hurto_personas', 0.1200, 'Media gravedad - criminalidad común'),
('otros_delitos', 0.0470, 'Baja gravedad - delitos menores')
ON CONFLICT (tipo_delito) DO NOTHING;

-- ============================================
-- 2. TABLA: Criminalidad por Localidad
-- ============================================
CREATE TABLE IF NOT EXISTS iug.criminalidad_localidad (
    id_crim SERIAL PRIMARY KEY,
    codigo_localidad VARCHAR(10),
    nombre_localidad VARCHAR(200),
    
    -- Delitos 2024 (campos del archivo DAILoc.geojson)
    homicidios_2024 INTEGER DEFAULT 0,
    delitos_sexuales_2024 INTEGER DEFAULT 0,
    hurto_personas_2024 INTEGER DEFAULT 0,
    otros_delitos_2024 INTEGER DEFAULT 0,
    
    -- Masa de crimen calculada con pesos AHP
    masa_crimen NUMERIC(12, 4),
    
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_crim_local_geom ON iug.criminalidad_localidad USING GIST(geom);
CREATE INDEX idx_crim_local_codigo ON iug.criminalidad_localidad(codigo_localidad);

COMMENT ON TABLE iug.criminalidad_localidad IS 'Estadísticas de criminalidad por localidad con masa ponderada por AHP';

-- ============================================
-- 3. TABLA: Sectores Priorizados (zonas deterioradas)
-- ============================================
CREATE TABLE IF NOT EXISTS iug.sector_priorizado (
    id_sector SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    descripcion TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_sector_prior_geom ON iug.sector_priorizado USING GIST(geom);

COMMENT ON TABLE iug.sector_priorizado IS 'Sectores priorizados para recuperación del espacio público (Hábitat)';

-- ============================================
-- 4. TABLA: CAI - Comandos de Atención Inmediata
-- ============================================
CREATE TABLE IF NOT EXISTS iug.cai_policia (
    id_cai SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    cuadrante VARCHAR(100),
    direccion TEXT,
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_cai_geom ON iug.cai_policia USING GIST(geom);

COMMENT ON TABLE iug.cai_policia IS 'Comandos de Atención Inmediata - protección policial';

-- ============================================
-- 5. TABLA: Scores RAW de seguridad (antes de normalizar)
-- ============================================
CREATE TABLE IF NOT EXISTS iug.indicador_seguridad_raw (
    id_indicador SERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble VARCHAR(50),
    
    -- Scores raw (sin normalizar)
    score_cai_raw NUMERIC(10, 4),          -- Σ gravity de CAI cercanos
    score_crimen_raw NUMERIC(12, 4),       -- Masa de crimen de la localidad
    score_sector_raw NUMERIC(5, 4),        -- Proximity a sector priorizado (0-1)
    
    -- Metadata
    localidad_nombre VARCHAR(200),
    masa_crimen_localidad NUMERIC(12, 4),
    en_sector_priorizado BOOLEAN DEFAULT FALSE,
    cais_cercanos INTEGER DEFAULT 0,
    
    fecha_calculo TIMESTAMP DEFAULT now(),
    UNIQUE(id_inmueble)
);

CREATE INDEX idx_seg_raw_inmueble ON iug.indicador_seguridad_raw(id_inmueble);
CREATE INDEX idx_seg_raw_tipo ON iug.indicador_seguridad_raw(tipo_inmueble);

COMMENT ON TABLE iug.indicador_seguridad_raw IS 'Scores crudos de seguridad antes de normalización 0-5';

-- ============================================
-- 6. TABLA: Parámetros de normalización por tipo de inmueble
-- ============================================
CREATE TABLE IF NOT EXISTS iug.normalizacion_seguridad (
    tipo_inmueble VARCHAR(50) PRIMARY KEY,
    
    -- Min/Max para normalización 0-5 (calculados del dataset)
    cai_min NUMERIC(10, 4) DEFAULT 0,
    cai_max NUMERIC(10, 4) DEFAULT 2.0,     -- Saturación en 2 CAI
    crimen_min NUMERIC(12, 4),
    crimen_max NUMERIC(12, 4),
    sector_min NUMERIC(5, 4) DEFAULT 0,
    sector_max NUMERIC(5, 4) DEFAULT 1.0,
    
    -- Pesos finales para combinación (suman ~1, pero pueden ajustarse)
    peso_cai NUMERIC(5, 4) DEFAULT 0.35,        -- Protección policial
    peso_crimen NUMERIC(5, 4) DEFAULT 0.45,     -- Mayor peso al crimen
    peso_sector NUMERIC(5, 4) DEFAULT 0.20,     -- Sectores deteriorados
    
    -- Metadata
    total_muestras INTEGER DEFAULT 0,
    fecha_actualizacion TIMESTAMP DEFAULT now(),
    version INTEGER DEFAULT 1
);

-- Inicializar para tipos comunes
INSERT INTO iug.normalizacion_seguridad (tipo_inmueble) 
VALUES ('Apartamento'), ('Casa'), ('Lote'), ('Local'), ('Oficina'), ('Bodega')
ON CONFLICT (tipo_inmueble) DO NOTHING;

COMMENT ON TABLE iug.normalizacion_seguridad IS 'Parámetros min/max y pesos para normalizar scores de seguridad 0-5';

-- ============================================
-- 7. VISTA MATERIALIZADA: Score final normalizado 0-5
-- ============================================
CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_seguridad_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    
    -- Normalizar cada componente 0-5
    5 * LEAST(r.score_cai_raw, n.cai_max) / NULLIF(n.cai_max, 0) as cai_norm,
    
    5 * CASE 
        WHEN NULLIF((n.crimen_max - n.crimen_min), 0) > 0 THEN
            (r.score_crimen_raw - n.crimen_min) / (n.crimen_max - n.crimen_min)
        ELSE 0.5
    END as crimen_norm,
    
    5 * r.score_sector_raw as sector_norm,
    
    -- Score final ponderado
    -- CAI suma, crimen y sector restan (invertidos)
    LEAST(5, GREATEST(0,
        (n.peso_cai * 5 * LEAST(r.score_cai_raw, n.cai_max) / NULLIF(n.cai_max, 0)) +
        (n.peso_crimen * (5 - 5 * CASE 
            WHEN NULLIF((n.crimen_max - n.crimen_min), 0) > 0 THEN
                (r.score_crimen_raw - n.crimen_min) / (n.crimen_max - n.crimen_min)
            ELSE 0.5
        END)) +
        (n.peso_sector * (5 - 5 * r.score_sector_raw))
    )) as score_seguridad_final,
    
    -- Metadata
    r.localidad_nombre,
    r.masa_crimen_localidad,
    r.en_sector_priorizado,
    r.cais_cercanos,
    n.version as normalizacion_version,
    r.fecha_calculo
    
FROM iug.indicador_seguridad_raw r
JOIN iug.normalizacion_seguridad n ON r.tipo_inmueble = n.tipo_inmueble;

CREATE UNIQUE INDEX idx_seg_final_id ON iug.indicador_seguridad_final(id_inmueble);
CREATE INDEX idx_seg_final_score ON iug.indicador_seguridad_final(score_seguridad_final DESC);
CREATE INDEX idx_seg_final_tipo ON iug.indicador_seguridad_final(tipo_inmueble);

COMMENT ON MATERIALIZED VIEW iug.indicador_seguridad_final IS 'Score final de seguridad 0-5: CAI suma, crimen y sectores priorizados restan';

-- ============================================
-- 8. FUNCIÓN: Calcular scores raw de seguridad
-- ============================================
CREATE OR REPLACE FUNCTION iug.calcular_seguridad_raw(p_geom geometry)
RETURNS TABLE(
    score_cai NUMERIC,
    score_crimen NUMERIC,
    score_sector NUMERIC,
    localidad TEXT,
    masa_crimen NUMERIC,
    en_sector BOOLEAN,
    num_cais INTEGER
) AS $$
DECLARE
    v_cai NUMERIC := 0;
    v_crimen NUMERIC := 0;
    v_sector NUMERIC := 0;
    v_localidad TEXT;
    v_masa NUMERIC;
    v_en_sector  BOOLEAN := FALSE;
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
    
    -- 2. Crimen (masa de la localidad)
    SELECT masa_crimen, nombre_localidad
    INTO v_masa, v_localidad
    FROM iug.criminalidad_localidad
    WHERE ST_Within(p_geom, geom)
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
-- 9. TRIGGER: Auto-cálculo de seguridad
-- ============================================
CREATE OR REPLACE FUNCTION iug.trigger_calcular_seguridad()
RETURNS TRIGGER AS $$
DECLARE
    v_result RECORD;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN
        
        SELECT * INTO v_result
        FROM iug.calcular_seguridad_raw(NEW.geom);
        
        INSERT INTO iug.indicador_seguridad_raw (
            id_inmueble,
            tipo_inmueble,
            score_cai_raw,
            score_crimen_raw,
            score_sector_raw,
            localidad_nombre,
            masa_crimen_localidad,
            en_sector_priorizado,
            cais_cercanos
        ) VALUES (
            NEW.id_inmueble,
            NEW.tipo_inmueble,
            v_result.score_cai,
            v_result.score_crimen,
            v_result.score_sector,
            v_result.localidad,
            v_result.masa_crimen,
            v_result.en_sector,
            v_result.num_cais
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

-- ============================================
-- 10. FUNCIÓN: Recalcular normalización desde dataset
-- ============================================
CREATE OR REPLACE FUNCTION iug.recalcular_normalizacion_seguridad(p_tipo_inmueble TEXT DEFAULT NULL)
RETURNS void AS $$
DECLARE
    v_tipo TEXT;
BEGIN
    FOR v_tipo IN 
        SELECT DISTINCT tipo_inmueble 
        FROM iug.indicador_seguridad_raw
        WHERE (p_tipo_inmueble IS NULL OR tipo_inmueble  = p_tipo_inmueble)
    LOOP
        UPDATE iug.normalizacion_seguridad n
        SET 
            cai_min = stats.cai_min,
            cai_max = stats.cai_max,
            crimen_min = stats.crimen_min,
            crimen_max = stats.crimen_max,
            sector_min = 0,
            sector_max = 1,
            total_muestras = stats.total,
            fecha_actualizacion = now()
        FROM (
            SELECT 
                MIN(score_cai_raw) as cai_min,
                LEAST(MAX(score_cai_raw), 2.0) as cai_max,  -- Saturar en 2
                MIN(score_crimen_raw) as crimen_min,
                MAX(score_crimen_raw) as crimen_max,
                COUNT(*) as total
            FROM iug.indicador_seguridad_raw
            WHERE tipo_inmueble = v_tipo
        ) stats
        WHERE n.tipo_inmueble = v_tipo;
        
        RAISE NOTICE 'Actualizada normalización para %', v_tipo;
    END LOOP;
    
    -- Refrescar vista materializada
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_seguridad_final;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.recalcular_normalizacion_seguridad IS 
'Recalcula min/max para normalización desde los datos actuales del dataset';
