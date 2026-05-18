-- =========================================
-- Capas espaciales de referencia
-- =========================================
CREATE TABLE IF NOT EXISTS iug.localidad (
  id_localidad SERIAL PRIMARY KEY,
  nombre       TEXT NOT NULL UNIQUE,
  geom         geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS iug_localidad_gix ON iug.localidad USING GIST (geom);

CREATE TABLE IF NOT EXISTS iug.barrio (
  id_barrio SERIAL PRIMARY KEY,
  nombre TEXT NOT NULL,
  id_localidad INT NOT NULL REFERENCES iug.localidad(id_localidad) ON DELETE RESTRICT,
  descripcion TEXT,
  area_total NUMERIC(12, 2),
  poblacion_estimada NUMERIC(12, 2),
  codigo_upz INT,
  estado INT,
  geom geometry(MultiPolygon, 4326) NOT NULL,
  CONSTRAINT barrio_unq UNIQUE (id_localidad, nombre)
);

CREATE INDEX IF NOT EXISTS iug_barrio_gix     ON iug.barrio USING GIST (geom);
CREATE INDEX IF NOT EXISTS iug_barrio_loc_idx ON iug.barrio(id_localidad);
CREATE INDEX IF NOT EXISTS iug_barrio_upz_idx ON iug.barrio(codigo_upz);

-- =========================================
-- Tablas de puntos (SITP / TM)
-- =========================================
CREATE TABLE IF NOT EXISTS iug.sitp_paradero (
  id        BIGSERIAL PRIMARY KEY,
  objectid  INTEGER,
  globalid  TEXT,
  nombre    TEXT,
  codigo    TEXT,
  props     JSONB NOT NULL DEFAULT '{}',
  geom      geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS iug.tm_estacion (
  id        BIGSERIAL PRIMARY KEY,
  objectid  INTEGER,
  globalid  TEXT,
  nombre    TEXT,
  codigo    TEXT,
  cod_nodo  INTEGER,
  troncal   TEXT,
  props     JSONB NOT NULL DEFAULT '{}',
  geom      geometry(Point, 4326) NOT NULL
);

-- Índices espaciales y por JSONB
CREATE INDEX IF NOT EXISTS sitp_paradero_gix
  ON iug.sitp_paradero USING GIST (geom);
CREATE INDEX IF NOT EXISTS sitp_paradero_props_gin
  ON iug.sitp_paradero USING GIN (props);

CREATE INDEX IF NOT EXISTS tm_estacion_gix
  ON iug.tm_estacion USING GIST (geom);
CREATE INDEX IF NOT EXISTS tm_estacion_props_gin
  ON iug.tm_estacion USING GIN (props);

-- Índices únicos parciales por objectid (para ON CONFLICT DO NOTHING)
CREATE UNIQUE INDEX IF NOT EXISTS sitp_paradero_objectid_uniq
  ON iug.sitp_paradero(objectid) WHERE objectid IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS tm_estacion_objectid_uniq
  ON iug.tm_estacion(objectid) WHERE objectid IS NOT NULL;

-- =========================================
-- (Opcional) Migrar SRID a 4326 si quedaron columnas con SRID ≠ 4326
-- =========================================
DO $$
BEGIN
  -- localidad
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='iug' AND table_name='localidad' AND column_name='geom'
  ) THEN
    EXECUTE $mig$
      ALTER TABLE iug.localidad
      ALTER COLUMN geom TYPE geometry(MultiPolygon, 4326)
      USING CASE
        WHEN ST_SRID(geom)=0 THEN ST_SetSRID(geom,4326)
        WHEN ST_SRID(geom)<>4326 THEN ST_Transform(geom,4326)
        ELSE geom
      END;
    $mig$;
  END IF;

  -- barrio
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='iug' AND table_name='barrio' AND column_name='geom'
  ) THEN
    EXECUTE $mig$
      ALTER TABLE iug.barrio
      ALTER COLUMN geom TYPE geometry(MultiPolygon, 4326)
      USING CASE
        WHEN ST_SRID(geom)=0 THEN ST_SetSRID(geom,4326)
        WHEN ST_SRID(geom)<>4326 THEN ST_Transform(geom,4326)
        ELSE geom
      END;
    $mig$;
  END IF;

  -- sitp_paradero
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='iug' AND table_name='sitp_paradero' AND column_name='geom'
  ) THEN
    EXECUTE $mig$
      ALTER TABLE iug.sitp_paradero
      ALTER COLUMN geom TYPE geometry(Point, 4326)
      USING CASE
        WHEN ST_SRID(geom)=0 THEN ST_SetSRID(geom,4326)
        WHEN ST_SRID(geom)<>4326 THEN ST_Transform(geom,4326)
        ELSE geom
      END;
    $mig$;
  END IF;

  -- tm_estacion
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='iug' AND table_name='tm_estacion' AND column_name='geom'
  ) THEN
    EXECUTE $mig$
      ALTER TABLE iug.tm_estacion
      ALTER COLUMN geom TYPE geometry(Point, 4326)
      USING CASE
        WHEN ST_SRID(geom)=0 THEN ST_SetSRID(geom,4326)
        WHEN ST_SRID(geom)<>4326 THEN ST_Transform(geom,4326)
        ELSE geom
      END;
    $mig$;
  END IF;
END$$;
