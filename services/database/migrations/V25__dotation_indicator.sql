-- =====================================================
-- V25: Indicador de Dotaciones (I_DOT) con Gravity Model
-- =====================================================
-- Similar a I_ACC (transporte): suma ponderada inverso distancia
-- Normalización 0-5 por percentil (partition by tipo_inmueble)

-- =====================================================
-- 1. TABLAS DE DOTACIONES
-- =====================================================

-- 1.1 Salud (IPS, Clínicas, Farmacias)
CREATE TABLE IF NOT EXISTS iug.dotacion_salud (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255),
    tipo VARCHAR(50) DEFAULT 'ips', -- 'ips', 'hospital', 'clinica', 'farmacia'
    direccion VARCHAR(255),
    localidad VARCHAR(100),
    geom GEOMETRY(Point, 4326),
    fecha_carga TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dotacion_salud_geom ON iug.dotacion_salud USING GIST(geom);

-- 1.2 Educación (Colegios, Universidades)
CREATE TABLE IF NOT EXISTS iug.dotacion_educacion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255),
    tipo VARCHAR(50) DEFAULT 'colegio', -- 'colegio', 'universidad', 'jardin'
    sector VARCHAR(50), -- 'oficial', 'privado'
    geom GEOMETRY(Point, 4326),
    fecha_carga TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dotacion_educacion_geom ON iug.dotacion_educacion USING GIST(geom);

-- 1.3 Abastecimiento (Supermercados, Centros Comerciales, Plazas, Tiendas)
CREATE TABLE IF NOT EXISTS iug.dotacion_abastecimiento (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255),
    tipo VARCHAR(50) DEFAULT 'supermercado', -- 'supermercado', 'centro_comercial', 'plaza_mercado', 'tienda'
    marca VARCHAR(100), -- 'exito', 'd1', 'ara', etc
    geom GEOMETRY(Point, 4326),
    fecha_carga TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dotacion_abastecimiento_geom ON iug.dotacion_abastecimiento USING GIST(geom);

-- 1.4 Cultura (Bibliotecas, Teatros, Museos)
CREATE TABLE IF NOT EXISTS iug.dotacion_cultura (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255),
    tipo VARCHAR(50) DEFAULT 'biblioteca', -- 'biblioteca', 'teatro', 'museo'
    geom GEOMETRY(Point, 4326),
    fecha_carga TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dotacion_cultura_geom ON iug.dotacion_cultura USING GIST(geom);

-- 1.5 Recreación (Parques, Canchas) - Complementa osm_parks existente
CREATE TABLE IF NOT EXISTS iug.dotacion_recreacion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255),
    tipo VARCHAR(50) DEFAULT 'parque', -- 'parque', 'cancha', 'escenario_deportivo'
    area_m2 NUMERIC,
    geom GEOMETRY(Geometry, 4326), -- Puede ser Point o Polygon
    fecha_carga TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dotacion_recreacion_geom ON iug.dotacion_recreacion USING GIST(geom);

-- =====================================================
-- 2. TABLA DE PESOS (Para suma ponderada y futuro AHP)
-- =====================================================

CREATE TABLE IF NOT EXISTS iug.pesos_dotacion (
    id SERIAL PRIMARY KEY,
    categoria VARCHAR(50) UNIQUE NOT NULL, -- 'salud', 'educacion', etc.
    peso NUMERIC(4,3) DEFAULT 0.200, -- Suma debe = 1.0
    radio_metros INTEGER DEFAULT 1000,
    descripcion TEXT,
    activo BOOLEAN DEFAULT true
);

-- Pesos iniciales (suma ponderada simple)
INSERT INTO iug.pesos_dotacion (categoria, peso, radio_metros, descripcion) VALUES
    ('salud', 0.20, 1000, 'IPS, Clínicas, Farmacias'),
    ('educacion', 0.20, 1500, 'Colegios, Universidades'),
    ('abastecimiento', 0.25, 800, 'Supermercados, Centros Comerciales, Plazas'),
    ('cultura', 0.15, 2000, 'Bibliotecas, Teatros'),
    ('recreacion', 0.20, 1500, 'Parques, Canchas')
ON CONFLICT (categoria) DO NOTHING;

-- Tabla vacía para futuro AHP (si se necesita)
CREATE TABLE IF NOT EXISTS iug.pesos_dotacion_ahp (
    id SERIAL PRIMARY KEY,
    categoria_1 VARCHAR(50),
    categoria_2 VARCHAR(50),
    comparacion NUMERIC(4,2), -- Escala Saaty 1-9
    fecha_calculo TIMESTAMP,
    UNIQUE(categoria_1, categoria_2)
);
COMMENT ON TABLE iug.pesos_dotacion_ahp IS 'Tabla vacía para futura calibración AHP de pesos de dotación';

-- =====================================================
-- 3. TABLA RAW DE INDICADOR
-- =====================================================

CREATE TABLE IF NOT EXISTS iug.indicador_dotacion_raw (
    id SERIAL PRIMARY KEY,
    id_inmueble INTEGER REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    
    -- Scores por categoría (gravity: sum 1/d)
    score_salud NUMERIC(10,4),
    score_educacion NUMERIC(10,4),
    score_abastecimiento NUMERIC(10,4),
    score_cultura NUMERIC(10,4),
    score_recreacion NUMERIC(10,4),
    
    -- Conteos (para debug/análisis)
    n_salud INTEGER DEFAULT 0,
    n_educacion INTEGER DEFAULT 0,
    n_abastecimiento INTEGER DEFAULT 0,
    n_cultura INTEGER DEFAULT 0,
    n_recreacion INTEGER DEFAULT 0,
    
    -- Score total ponderado
    idot_raw NUMERIC(10,4),
    
    fecha_calculo TIMESTAMP DEFAULT now(),
    UNIQUE(id_inmueble)
);
CREATE INDEX IF NOT EXISTS idx_indicador_dotacion_inmueble ON iug.indicador_dotacion_raw(id_inmueble);

-- =====================================================
-- 4. FUNCIÓN: Calcular Score Gravity por Categoría
-- =====================================================

CREATE OR REPLACE FUNCTION iug.calcular_score_dotacion_categoria(
    p_geom GEOMETRY,
    p_tabla TEXT,
    p_radio_m INTEGER
) RETURNS TABLE(score NUMERIC, conteo INTEGER) AS $$
DECLARE
    v_score NUMERIC := 0;
    v_count INTEGER := 0;
BEGIN
    -- Gravity model: Σ(1 / distancia_metros)
    -- Distancia mínima = 50m para evitar división por cero
    EXECUTE format('
        SELECT 
            COALESCE(SUM(1.0 / GREATEST(ST_Distance($1::geography, geom::geography), 50)), 0),
            COUNT(*)
        FROM %I
        WHERE ST_DWithin($1::geography, geom::geography, $2)
    ', p_tabla)
    INTO v_score, v_count
    USING p_geom, p_radio_m;
    
    RETURN QUERY SELECT v_score, v_count;
END;
$$ LANGUAGE plpgsql STABLE;

-- =====================================================
-- 5. FUNCIÓN: Calcular I_DOT Completo
-- =====================================================

CREATE OR REPLACE FUNCTION iug.calcular_idot(p_geom GEOMETRY)
RETURNS NUMERIC AS $$
DECLARE
    v_score_salud NUMERIC := 0;
    v_score_educacion NUMERIC := 0;
    v_score_abastecimiento NUMERIC := 0;
    v_score_cultura NUMERIC := 0;
    v_score_recreacion NUMERIC := 0;
    v_peso RECORD;
    v_idot NUMERIC := 0;
    v_temp_score NUMERIC;
    v_temp_count INTEGER;
BEGIN
    -- Obtener pesos
    FOR v_peso IN SELECT categoria, peso, radio_metros FROM iug.pesos_dotacion WHERE activo LOOP
        CASE v_peso.categoria
            WHEN 'salud' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_salud', v_peso.radio_metros);
                v_score_salud := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'educacion' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_educacion', v_peso.radio_metros);
                v_score_educacion := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'abastecimiento' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_abastecimiento', v_peso.radio_metros);
                v_score_abastecimiento := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'cultura' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_cultura', v_peso.radio_metros);
                v_score_cultura := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'recreacion' THEN
                -- Usa osm_parks existente + dotacion_recreacion
                SELECT 
                    COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
                INTO v_temp_score
                FROM (
                    SELECT geom FROM iug.dotacion_recreacion 
                    WHERE ST_DWithin(p_geom::geography, geom::geography, v_peso.radio_metros)
                    UNION ALL
                    SELECT ST_Centroid(geom) as geom FROM iug.osm_parks
                    WHERE ST_DWithin(p_geom::geography, ST_Centroid(geom)::geography, v_peso.radio_metros)
                ) combined;
                v_score_recreacion := COALESCE(v_temp_score, 0);
                v_idot := v_idot + (v_peso.peso * v_score_recreacion);
        END CASE;
    END LOOP;
    
    RETURN v_idot;
END;
$$ LANGUAGE plpgsql STABLE;

-- =====================================================
-- 6. FUNCIÓN TRIGGER: Calcular I_DOT en INSERT/UPDATE
-- =====================================================

CREATE OR REPLACE FUNCTION iug.trg_calcular_dotacion()
RETURNS TRIGGER AS $$
DECLARE
    v_idot NUMERIC;
    v_scores RECORD;
BEGIN
    -- Solo calcular si tiene geometría
    IF NEW.geom IS NULL THEN
        RETURN NEW;
    END IF;
    
    -- Calcular score total
    v_idot := iug.calcular_idot(NEW.geom);
    
    -- Guardar en tabla raw
    INSERT INTO iug.indicador_dotacion_raw (id_inmueble, idot_raw, fecha_calculo)
    VALUES (NEW.id_inmueble, v_idot, now())
    ON CONFLICT (id_inmueble) DO UPDATE SET
        idot_raw = EXCLUDED.idot_raw,
        fecha_calculo = now();
    
    -- Actualizar campo en inmueble (si existe columna)
    -- NEW.idot := v_idot; -- Descomentar si agregas columna
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Crear trigger (desactivado por defecto hasta que haya datos)
DROP TRIGGER IF EXISTS trg_inmueble_dotacion ON iug.inmueble;
CREATE TRIGGER trg_inmueble_dotacion
AFTER INSERT OR UPDATE OF geom ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trg_calcular_dotacion();

-- Desactivar temporalmente hasta cargar datos
ALTER TABLE iug.inmueble DISABLE TRIGGER trg_inmueble_dotacion;

-- =====================================================
-- 7. VISTA MATERIALIZADA: Normalización 0-5
-- =====================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_dotacion_final AS
SELECT 
    r.id_inmueble,
    i.tipo_inmueble,
    r.idot_raw,
    
    -- Normalización 0-5 por percentil (partition by tipo)
    ROUND(
        (5.0 * PERCENT_RANK() OVER (
            PARTITION BY i.tipo_inmueble 
            ORDER BY r.idot_raw
        ))::numeric, 
        4
    ) as idot_normalizado,
    
    -- Stats adicionales
    r.n_salud,
    r.n_educacion,
    r.n_abastecimiento,
    r.n_cultura,
    r.n_recreacion,
    r.fecha_calculo
FROM iug.indicador_dotacion_raw r
JOIN iug.inmueble i ON r.id_inmueble = i.id_inmueble
WHERE r.idot_raw IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_indicador_dotacion_final_pk 
ON iug.indicador_dotacion_final(id_inmueble);

-- =====================================================
-- 8. FUNCIÓN: Recalcular Masivo
-- =====================================================

CREATE OR REPLACE FUNCTION iug.recalcular_dotacion_masivo(p_limit INTEGER DEFAULT NULL)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
    v_inmueble RECORD;
    v_idot NUMERIC;
BEGIN
    FOR v_inmueble IN 
        SELECT id_inmueble, geom 
        FROM iug.inmueble 
        WHERE geom IS NOT NULL
        LIMIT p_limit
    LOOP
        v_idot := iug.calcular_idot(v_inmueble.geom);
        
        INSERT INTO iug.indicador_dotacion_raw (id_inmueble, idot_raw)
        VALUES (v_inmueble.id_inmueble, v_idot)
        ON CONFLICT (id_inmueble) DO UPDATE SET
            idot_raw = EXCLUDED.idot_raw,
            fecha_calculo = now();
        
        v_count := v_count + 1;
        
        IF v_count % 100 = 0 THEN
            RAISE NOTICE 'Procesados: %', v_count;
        END IF;
    END LOOP;
    
    -- Refresh vista
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_dotacion_final;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. AGREGAR COLUMNA IDOT A INMUEBLE (Opcional)
-- =====================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'iug' AND table_name = 'inmueble' AND column_name = 'idot'
    ) THEN
        ALTER TABLE iug.inmueble ADD COLUMN idot NUMERIC(5,4);
        COMMENT ON COLUMN iug.inmueble.idot IS 'Indicador de Dotación normalizado 0-5';
    END IF;
END $$;

-- =====================================================
-- COMENTARIOS
-- =====================================================

COMMENT ON TABLE iug.pesos_dotacion IS 'Pesos para suma ponderada de dotaciones. Suma debe = 1.0';
COMMENT ON FUNCTION iug.calcular_idot IS 'Calcula I_DOT usando gravity model: Σ(peso × Σ(1/distancia))';
COMMENT ON TRIGGER trg_inmueble_dotacion ON iug.inmueble IS 'Calcula I_DOT automáticamente en INSERT/UPDATE. Desactivado hasta cargar datos.';
