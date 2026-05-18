-- V18: Sistema de Indicadores de Amenidades
-- Calcula scores gravity-based para: Parques, Hospitales, Colegios, Universidades

-- ============================================
-- 1. TABLA: Scores raw de amenidades
-- ============================================
CREATE TABLE IF NOT EXISTS iug.indicador_amenidades_raw (
    id_indicador SERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble VARCHAR(50),
    
    -- Scores gravity-based individuales
    score_parques_raw NUMERIC(10, 4),
    score_salud_raw NUMERIC(10, 4),
    score_educacion_basica_raw NUMERIC(10, 4),  -- Colegios
    score_educacion_superior_raw NUMERIC(10, 4), -- Universidades
    
    fecha_calculo TIMESTAMP DEFAULT now(),
    UNIQUE(id_inmueble)
);

CREATE INDEX IF NOT EXISTS idx_amenidades_raw_inmueble ON iug.indicador_amenidades_raw(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_amenidades_raw_tipo ON iug.indicador_amenidades_raw(tipo_inmueble);

COMMENT ON TABLE iug.indicador_amenidades_raw IS 
'Scores gravity-based para amenidades: Parques (800m), Salud (1500m), Educación Básica (1000m), Educación Superior (2000m)';

-- ============================================
-- 2. TABLA: Pesos PCA para amenidades
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pca_pesos_amenidades (
    tipo_inmueble VARCHAR(50) PRIMARY KEY,
    
    -- Pesos de componente principal
    peso_parques NUMERIC(10,6) DEFAULT 0.25,
    peso_salud NUMERIC(10,6) DEFAULT 0.25,
    peso_educacion_basica NUMERIC(10,6) DEFAULT 0.25,
    peso_educacion_superior NUMERIC(10,6) DEFAULT 0.25,
    
    -- Normalización
    pc1_min NUMERIC(10,6) DEFAULT 0,
    pc1_max NUMERIC(10,6) DEFAULT 1,
    
    -- Metadata
    pca_version INTEGER DEFAULT 1,
    total_muestras INTEGER DEFAULT 0,
    varianza_explicada NUMERIC(5,4),
    fecha_actualizacion TIMESTAMP DEFAULT now()
);

-- Inicializar pesos por defecto
INSERT INTO iug.pca_pesos_amenidades (tipo_inmueble) 
VALUES ('Apartamento'), ('Casa'), ('Lote'), ('Local'), ('Oficina'), ('Bodega')
ON CONFLICT (tipo_inmueble) DO NOTHING;

-- ============================================
-- 3. FUNCIÓN: Calcular indicadores de amenidades
-- ============================================
CREATE OR REPLACE FUNCTION iug.calcular_indicadores_amenidades(p_geom geometry)
RETURNS TABLE(
    score_parques NUMERIC,
    score_salud NUMERIC,
    score_educacion_basica NUMERIC,
    score_educacion_superior NUMERIC
) AS $$
DECLARE
    -- Radios específicos por amenidad (metros)
    v_radio_parques CONSTANT INTEGER := 800;
    v_radio_salud CONSTANT INTEGER := 1500;
    v_radio_educacion_basica CONSTANT INTEGER := 1000;
    v_radio_educacion_superior CONSTANT INTEGER := 2000;
    
    v_score_parques NUMERIC;
    v_score_salud NUMERIC;
    v_score_educacion_basica NUMERIC;
    v_score_educacion_superior NUMERIC;
BEGIN
    RAISE NOTICE '[AMENIDADES] Calculando scores de amenidades...';
    
    -- Parques
    v_score_parques := iug.calcular_score_transporte_gravity(p_geom, 'parques', v_radio_parques);
    RAISE NOTICE '[AMENIDADES] Parques: % (radio %m)', v_score_parques, v_radio_parques;
    
    -- Centros de salud
    v_score_salud := iug.calcular_score_transporte_gravity(p_geom, 'salud', v_radio_salud);
    RAISE NOTICE '[AMENIDADES] Salud: % (radio %m)', v_score_salud, v_radio_salud;
    
    -- Educación básica (colegios)
    v_score_educacion_basica := iug.calcular_score_transporte_gravity(p_geom, 'educacion_basica', v_radio_educacion_basica);
    RAISE NOTICE '[AMENIDADES] Educación básica: % (radio %m)', v_score_educacion_basica, v_radio_educacion_basica;
    
    -- Educación superior (universidades)
    v_score_educacion_superior := iug.calcular_score_transporte_gravity(p_geom, 'educacion_superior', v_radio_educacion_superior);
    RAISE NOTICE '[AMENIDADES] Educación superior: % (radio %m)', v_score_educacion_superior, v_radio_educacion_superior;
    
    RETURN QUERY SELECT v_score_parques, v_score_salud, v_score_educacion_basica, v_score_educacion_superior;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 4. TRIGGER: Auto-cálculo de amenidades
-- ============================================
CREATE OR REPLACE FUNCTION iug.trigger_calcular_amenidades_raw()
RETURNS TRIGGER AS $$
DECLARE
    v_scores RECORD;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN
        RAISE NOTICE '[TRIGGER AMENIDADES] Calculando para ID=%', NEW.id_inmueble;
        
        SELECT * INTO v_scores 
        FROM iug.calcular_indicadores_amenidades(NEW.geom);
        
        INSERT INTO iug.indicador_amenidades_raw (
            id_inmueble,
            tipo_inmueble,
            score_parques_raw,
            score_salud_raw,
            score_educacion_basica_raw,
            score_educacion_superior_raw
        ) VALUES (
            NEW.id_inmueble,
            NEW.tipo_inmueble,
            v_scores.score_parques,
            v_scores.score_salud,
            v_scores.score_educacion_basica,
            v_scores.score_educacion_superior
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_parques_raw = EXCLUDED.score_parques_raw,
            score_salud_raw = EXCLUDED.score_salud_raw,
            score_educacion_basica_raw = EXCLUDED.score_educacion_basica_raw,
            score_educacion_superior_raw = EXCLUDED.score_educacion_superior_raw,
            fecha_calculo = now();
        
        RAISE NOTICE '[TRIGGER AMENIDADES] ✅ Scores guardados';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inmueble_amenidades_raw
AFTER INSERT OR UPDATE OF geom, tipo_inmueble ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trigger_calcular_amenidades_raw();

-- ============================================
-- 5. VISTA MATERIALIZADA: Score final
-- ============================================
CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_amenidades_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    
    -- PC1 raw
    (r.score_parques_raw * p.peso_parques + 
     r.score_salud_raw * p.peso_salud + 
     r.score_educacion_basica_raw * p.peso_educacion_basica + 
     r.score_educacion_superior_raw * p.peso_educacion_superior) as pc1_value,
    
    -- Score final normalizado (0-5)
    CASE 
        WHEN (p.pc1_max - p.pc1_min) > 0 THEN
            5 * ((r.score_parques_raw * p.peso_parques + 
                  r.score_salud_raw * p.peso_salud + 
                  r.score_educacion_basica_raw * p.peso_educacion_basica + 
                  r.score_educacion_superior_raw * p.peso_educacion_superior) - p.pc1_min) 
                / (p.pc1_max - p.pc1_min)
        ELSE 2.5
    END as score_amenidades_final,
    
    p.pca_version,
    r.fecha_calculo as fecha_calculo_gravity,
    p.fecha_actualizacion as fecha_calculo_pca
    
FROM iug.indicador_amenidades_raw r
JOIN iug.pca_pesos_amenidades p ON r.tipo_inmueble = p.tipo_inmueble;

CREATE UNIQUE INDEX IF NOT EXISTS idx_amenidades_final_id ON iug.indicador_amenidades_final(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_amenidades_final_tipo ON iug.indicador_amenidades_final(tipo_inmueble);

COMMENT ON MATERIALIZED VIEW iug.indicador_amenidades_final IS
'Score final de amenidades (0-5) normalizado con PCA';

-- ============================================
-- 6. ACTUALIZAR calcular_score_transporte_gravity para soportar nuevas capas
-- ============================================
-- La función ya es genérica, solo necesitamos asegurar que las capas estén registradas
-- Agregamos comentario con las capas soportadas
COMMENT ON FUNCTION iug.calcular_score_transporte_gravity(geometry, text, integer) IS
'Calcula score gravity-based genérico. Capas: transmilenio, sitp, vias, parques, salud, educacion_basica, educacion_superior';
