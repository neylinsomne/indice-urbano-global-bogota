-- =============================================================================
-- V7__tablas_indicadores.sql
-- Flyway Migration: Tablas de indicadores por localidad y mejoras
-- Los cálculos se hacen en Python (ML/clustering), la BD solo almacena
-- =============================================================================

-- Crear tabla localidad si no existe (necesaria para FK)
CREATE TABLE IF NOT EXISTS iug.localidad (
  id_localidad SERIAL PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  geom GEOMETRY(MultiPolygon, 4326)
);

-- Tabla de indicadores por LOCALIDAD
CREATE TABLE IF NOT EXISTS iug.indicador_localidad (
  id_localidad INT PRIMARY KEY REFERENCES iug.localidad(id_localidad) ON DELETE CASCADE,
  -- Subíndices (escala 0-5, calculados en Python)
  iacc NUMERIC(6,3),  -- Accesibilidad y transporte
  iseg NUMERIC(6,3),  -- Seguridad
  idot NUMERIC(6,3),  -- Dotación de servicios
  ipnu NUMERIC(6,3),  -- Potencial normativo
  -- Agregado
  iug  NUMERIC(6,3),  -- Índice Urbano Global
  -- Metadata
  n_barrios INT,      -- Cantidad de barrios en la localidad
  n_inmuebles INT,    -- Cantidad de inmuebles en la localidad
  updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ind_localidad_iug ON iug.indicador_localidad (iug);

-- Tabla genérica de POIs (educación, salud, comercio, recreación)
CREATE TABLE IF NOT EXISTS iug.poi (
    id_poi BIGSERIAL PRIMARY KEY,
    categoria TEXT NOT NULL,  -- 'educacion', 'salud', 'comercio', 'recreacion', 'parque'
    subcategoria TEXT,
    nombre TEXT,
    direccion TEXT,
    props JSONB DEFAULT '{}',
    geom geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS poi_gix ON iug.poi USING GIST (geom);
CREATE INDEX IF NOT EXISTS poi_cat_idx ON iug.poi (categoria);

-- Tabla para malla vial (futuro: vectores de calles)
CREATE TABLE IF NOT EXISTS iug.malla_vial (
    id_via BIGSERIAL PRIMARY KEY,
    tipo_via TEXT,  -- 'arterial', 'local', 'peatonal', etc.
    nombre TEXT,
    props JSONB DEFAULT '{}',
    geom geometry(LineString, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS malla_vial_gix ON iug.malla_vial USING GIST (geom);

-- Tabla para coeficientes del modelo hedónico (calculados en Python)
CREATE TABLE IF NOT EXISTS iug.modelo_hedonico (
    id_modelo SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT 'default',
    tipo_inmueble TEXT,  -- NULL = aplica a todos
    -- Coeficientes beta (calculados por regresión en Python)
    coeficientes JSONB NOT NULL DEFAULT '{}',
    -- Métricas del modelo
    r_squared NUMERIC,
    rmse NUMERIC,
    n_observaciones INT,
    -- Metadata
    created_at TIMESTAMP DEFAULT now(),
    activo BOOLEAN DEFAULT true,
    CONSTRAINT modelo_hedonico_uniq UNIQUE (nombre, tipo_inmueble)
);

-- Tabla de pesos para el IUG (configurable)
CREATE TABLE IF NOT EXISTS iug.pesos_iug (
    id_config SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT 'default',
    w_hed NUMERIC NOT NULL DEFAULT 1.0,
    w_acc NUMERIC NOT NULL DEFAULT 1.0,
    w_seg NUMERIC NOT NULL DEFAULT 1.0,
    w_dot NUMERIC NOT NULL DEFAULT 1.0,
    w_pnu NUMERIC NOT NULL DEFAULT 1.0,
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT pesos_iug_uniq UNIQUE (nombre)
);

-- Insertar configuración default
INSERT INTO iug.pesos_iug (nombre) VALUES ('default') ON CONFLICT DO NOTHING;

-- Comentarios
COMMENT ON TABLE iug.indicador_localidad IS 'Indicadores agregados por localidad (calculados en Python)';
COMMENT ON TABLE iug.poi IS 'Puntos de Interés para análisis espacial';
COMMENT ON TABLE iug.malla_vial IS 'Red vial para análisis de conectividad (futuro)';
COMMENT ON TABLE iug.modelo_hedonico IS 'Coeficientes de regresión hedónica (calculados en Python)';
