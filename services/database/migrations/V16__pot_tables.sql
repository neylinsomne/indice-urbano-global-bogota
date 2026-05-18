-- V16: Tablas POT (Plan de Ordenamiento Territorial) para permisos de construcción
-- Estas tablas contienen información sobre zonificación, alturas permitidas, y tratamiento urbano

-- ============================================
-- 1. Área de Actividad (Zonificación)
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pot_area_actividad (
    id_area SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    descripcion TEXT,
    normativa TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pot_area_geom ON iug.pot_area_actividad USING GIST(geom);

COMMENT ON TABLE iug.pot_area_actividad IS 'Áreas de actividad del POT - Define usos permitidos por zona';

-- ============================================
-- 2. Tratamiento Urbanístico
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pot_tratamiento (
    id_tratamiento SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    tipo VARCHAR(100),  -- Consolidación, Desarrollo, Conservación, Mejoramiento, Renovación
    descripcion TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pot_tratamiento_geom ON iug.pot_tratamiento USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_pot_tratamiento_tipo ON iug.pot_tratamiento(tipo);

COMMENT ON TABLE iug.pot_tratamiento IS 'Tratamiento urbanístico - Define intervenciones permitidas';

-- ============================================
-- 3. Edificabilidad (Altura/Pisos Máximos)
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pot_edificabilidad (
    id_edificabilidad SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    rango VARCHAR(100),  -- Ej: "1-3 pisos", "4-6 pisos", etc.
    pisos_min INTEGER,
    pisos_max INTEGER,
    altura_max_m NUMERIC(6,2),
    descripcion TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pot_edificabilidad_geom ON iug.pot_edificabilidad USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_pot_edificabilidad_pisos ON iug.pot_edificabilidad(pisos_max);

COMMENT ON TABLE iug.pot_edificabilidad IS 'Edificabilidad - Altura y pisos máximos permitidos';

-- ============================================
-- 4. Unidad de Planeamiento Local (UPL)
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pot_upl (
    id_upl SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    localidad VARCHAR(100),
    estado VARCHAR(50),  -- Adoptada, En formulación, etc.
    descripcion TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pot_upl_geom ON iug.pot_upl USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_pot_upl_localidad ON iug.pot_upl(localidad);

COMMENT ON TABLE iug.pot_upl IS 'Unidades de Planeamiento Local - Normativa específica por UPL';

-- ============================================
-- 5. Vista combinada para análisis
-- ============================================
CREATE OR REPLACE VIEW iug.v_pot_completo AS
SELECT 
    i.id_inmueble,
    i.direccion,
    i.tipo_inmueble,
    i.geom,
    
    -- Edificabilidad
    e.pisos_max,
    e.altura_max_m,
    e.rango as rango_edificabilidad,
    
    -- Tratamiento
    t.tipo as tipo_tratamiento,
    t.nombre as tratamiento,
    
    -- Área actividad
    a.nombre as area_actividad,
    a.normativa,
    
    -- UPL
    u.nombre as upl,
    u.estado as estado_upl
    
FROM iug.inmueble i
LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
LEFT JOIN iug.pot_upl u ON ST_Within(i.geom, u.geom);

COMMENT ON VIEW iug.v_pot_completo IS 'Vista consolidada de información POT por inmueble';
