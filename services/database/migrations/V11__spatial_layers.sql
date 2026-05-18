-- ============================================
-- V11: Crear tablas para capas geográficas
-- ============================================

-- Localidades de Bogotá
CREATE TABLE IF NOT EXISTS iug.localidad (
    id_localidad SERIAL PRIMARY KEY,
    codigo VARCHAR(10),
    nombre VARCHAR(100) NOT NULL,
    geom geometry(MultiPolygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_localidad_geom ON iug.localidad USING GIST(geom);

-- Sectores catastrales
CREATE TABLE IF NOT EXISTS iug.sector (
    id_sector SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(100),
    localidad VARCHAR(100),
    geom geometry(MultiPolygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sector_geom ON iug.sector USING GIST(geom);

-- UPL (Unidades de Planeamiento Local)
CREATE TABLE IF NOT EXISTS iug.upl (
    id_upl SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(100),
    localidad VARCHAR(100),
    geom geometry(MultiPolygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_upl_geom ON iug.upl USING GIST(geom);

-- Estaciones TransMilenio
CREATE TABLE IF NOT EXISTS iug.estacion_transmilenio (
    id_estacion SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(100) NOT NULL,
    troncal VARCHAR(100),
    tipo VARCHAR(50),
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_estacion_tm_geom ON iug.estacion_transmilenio USING GIST(geom);

-- Colegios
CREATE TABLE IF NOT EXISTS iug.colegio (
    id_colegio SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200) NOT NULL,
    tipo VARCHAR(50),
    localidad VARCHAR(100),
    direccion VARCHAR(200),
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_colegio_geom ON iug.colegio USING GIST(geom);

-- Centros de Salud
CREATE TABLE IF NOT EXISTS iug.centro_salud (
    id_centro SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200) NOT NULL,
    tipo VARCHAR(100),
    localidad VARCHAR(100),
    direccion VARCHAR(200),
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_centro_salud_geom ON iug.centro_salud USING GIST(geom);

-- Cuadrantes de Policía
CREATE TABLE IF NOT EXISTS iug.cuadrante_policia (
    id_cuadrante SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(100),
    localidad VARCHAR(100),
    geom geometry(MultiPolygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cuadrante_geom ON iug.cuadrante_policia USING GIST(geom);

-- Centros Comerciales
CREATE TABLE IF NOT EXISTS iug.centro_comercial (
    id_cc SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    direccion VARCHAR(200),
    localidad VARCHAR(100),
    lat FLOAT,
    lon FLOAT,
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cc_geom ON iug.centro_comercial USING GIST(geom);

-- Universidades / Educación Superior
CREATE TABLE IF NOT EXISTS iug.universidad (
    id_universidad SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200) NOT NULL,
    tipo VARCHAR(100),
    localidad VARCHAR(100),
    direccion VARCHAR(200),
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_universidad_geom ON iug.universidad USING GIST(geom);

-- Rutas SITP
CREATE TABLE IF NOT EXISTS iug.ruta_sitp (
    id_ruta SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(200),
    tipo VARCHAR(50),
    geom geometry(MultiLineString, 4326),
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ruta_sitp_geom ON iug.ruta_sitp USING GIST(geom);

-- Comentario para tracking
COMMENT ON TABLE iug.localidad IS 'Polígonos de localidades de Bogotá';
COMMENT ON TABLE iug.estacion_transmilenio IS 'Estaciones y portales de TransMilenio';
COMMENT ON TABLE iug.colegio IS 'Instituciones educativas de Bogotá';
