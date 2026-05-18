-- ============================================
-- V12: Crear tablas para datos POT 555 y catastrales
-- ============================================

-- Sectores catastrales
CREATE TABLE IF NOT EXISTS iug.sector_catastral (
    id_sector SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(300),
    localidad VARCHAR(100),
    geom geometry(Geometry, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sector_catastral_geom ON iug.sector_catastral USING GIST(geom);

-- Barrios legalizados
CREATE TABLE IF NOT EXISTS iug.barrio (
    id_barrio SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(300),
    localidad VARCHAR(100),
    tipo VARCHAR(100),
    geom geometry(Geometry, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_barrio_geom ON iug.barrio USING GIST(geom);

-- Áreas de actividad POT
CREATE TABLE IF NOT EXISTS iug.area_actividad (
    id_area SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(300),
    tipo_actividad VARCHAR(200),
    geom geometry(Geometry, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_area_actividad_geom ON iug.area_actividad USING GIST(geom);

-- Tratamientos urbanísticos POT
CREATE TABLE IF NOT EXISTS iug.tratamiento_urbanistico (
    id_tratamiento SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(300),
    tipo VARCHAR(200),
    geom geometry(Geometry, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tratamiento_urbanistico_geom ON iug.tratamiento_urbanistico USING GIST(geom);

-- Rangos de edificabilidad POT
CREATE TABLE IF NOT EXISTS iug.edificabilidad (
    id_edificabilidad SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    rango_min FLOAT,
    rango_max FLOAT,
    descripcion VARCHAR(500),
    geom geometry(Geometry, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_edificabilidad_geom ON iug.edificabilidad USING GIST(geom);

-- Comentarios
COMMENT ON TABLE iug.sector_catastral IS 'Sectores catastrales de Bogotá';
COMMENT ON TABLE iug.barrio IS 'Barrios legalizados de Bogotá';
COMMENT ON TABLE iug.area_actividad IS 'Áreas de actividad según POT 555';
COMMENT ON TABLE iug.tratamiento_urbanistico IS 'Tratamientos urbanísticos según POT 555';
COMMENT ON TABLE iug.edificabilidad IS 'Rangos de edificabilidad según POT 555';
