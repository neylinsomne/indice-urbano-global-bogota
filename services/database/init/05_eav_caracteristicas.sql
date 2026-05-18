-- Catálogo opcional de características (EAV tipada)
CREATE TABLE IF NOT EXISTS iug.cat_caracteristica (
  id_caracteristica SERIAL PRIMARY KEY,
  nombre TEXT UNIQUE NOT NULL,                           -- ej.: 'ascensor', 'shut_basuras'
  tipo   TEXT NOT NULL CHECK (tipo IN ('bool','num','text','date'))
);

-- Características por inmueble
CREATE TABLE IF NOT EXISTS iug.inmueble_caracteristica (
  id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
  nombre      TEXT NOT NULL,            -- clave (opcionalmente referenciable a cat_caracteristica(nombre))
  valor_bool  BOOLEAN,
  valor_num   NUMERIC(14,4),
  valor_text  TEXT,
  valor_date  DATE,
  fuente      TEXT,
  updated_at  TIMESTAMP DEFAULT now(),
  PRIMARY KEY (id_inmueble, nombre)
);

CREATE INDEX IF NOT EXISTS iug_idx_ic_nombre     ON iug.inmueble_caracteristica (nombre);
CREATE INDEX IF NOT EXISTS iug_idx_ic_valor_num  ON iug.inmueble_caracteristica (valor_num);
CREATE INDEX IF NOT EXISTS iug_idx_ic_valor_bool ON iug.inmueble_caracteristica (valor_bool);
