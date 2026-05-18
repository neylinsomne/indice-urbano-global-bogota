-- Tabla principal inmueble + índices
CREATE TABLE IF NOT EXISTS iug.inmueble (
  id_inmueble       BIGSERIAL PRIMARY KEY,

  -- Origen / metadata
  id_origen         TEXT,               -- _id de la fuente (Mongo)
  pagina            TEXT,               -- finca_raiz, etc.
  codigo_fuente     TEXT,               -- codigo_fr u otro

  image             TEXT,               -- URL
  ubicacion         TEXT,
  ubicacion_asociada TEXT,
  direccion         TEXT,
  inmobiliaria      TEXT,
  descripcion       TEXT,

  estado            TEXT REFERENCES iug.cat_estado_inmueble(estado),
  edad              TEXT,
  estrato           SMALLINT CHECK (estrato BETWEEN 1 AND 6),

  proyecto          BOOLEAN,            -- TRUE solo si Apartamento
  fecha             DATE,

  tipo_inmueble     TEXT REFERENCES iug.cat_tipo_inmueble(tipo_inmueble),

  habitaciones      SMALLINT,
  banos             SMALLINT,
  area_construida   NUMERIC(10,2),
  area_privada      NUMERIC(10,2),
  precio            NUMERIC(14,2),

  -- Geometría y FKs espaciales
  geom              geometry(POINT, 4326),
  id_barrio         INT REFERENCES iug.barrio(id_barrio),
  id_localidad      INT REFERENCES iug.localidad(id_localidad),

  -- Indicadores
  ihed              NUMERIC(6,3),
  iacc              NUMERIC(6,3),
  iseg              NUMERIC(6,3),
  idot              NUMERIC(6,3),
  ipnu              NUMERIC(6,3),
  iug               NUMERIC(6,3),
  precio_std        NUMERIC(6,3),
  ratio             NUMERIC(8,4)
);

-- Índices prácticos
CREATE INDEX IF NOT EXISTS iug_inmueble_gix          ON iug.inmueble USING GIST (geom);
CREATE INDEX IF NOT EXISTS iug_inmueble_barrio_idx   ON iug.inmueble(id_barrio);
CREATE INDEX IF NOT EXISTS iug_inmueble_localidad_idx ON iug.inmueble(id_localidad);
CREATE INDEX IF NOT EXISTS iug_inmueble_tipo_idx     ON iug.inmueble(tipo_inmueble);

-- Regla de negocio: proyecto=TRUE solo si Apartamento
CREATE OR REPLACE FUNCTION iug.enforce_proyecto_apartamento()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.proyecto IS TRUE AND NEW.tipo_inmueble <> 'Apartamento' THEN
    RAISE EXCEPTION 'El flag proyecto=TRUE solo aplica a tipo_inmueble=Apartamento';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_proyecto_tipo ON iug.inmueble;
CREATE TRIGGER trg_proyecto_tipo
BEFORE INSERT OR UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.enforce_proyecto_apartamento();

-- Clave natural/antiduplicado que coAmentaste: (fuente + unidad básica)
ALTER TABLE iug.inmueble
  ADD CONSTRAINT uniq_inmueble_fuente_unidad
  UNIQUE (pagina, codigo_fuente, area_construida, habitaciones, banos);
