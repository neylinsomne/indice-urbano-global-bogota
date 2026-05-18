-- Agregar columnas faltantes para tracking de scraping
ALTER TABLE iug.inmueble 
  ADD COLUMN IF NOT EXISTS primera_vista timestamp DEFAULT now(),
  ADD COLUMN IF NOT EXISTS ultima_vista timestamp DEFAULT now(),
  ADD COLUMN IF NOT EXISTS n_scrapeos integer DEFAULT 1;

-- Crear tabla de histórico de scrapeos
CREATE TABLE IF NOT EXISTS iug.inmueble_scrapeo (
    id_scrapeo bigserial PRIMARY KEY,
    id_inmueble bigint REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    pagina text,
    precio_momento numeric(14,2),
    raw_data jsonb,
    fecha_scrapeo timestamp DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scrapeo_inmueble ON iug.inmueble_scrapeo(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_scrapeo_fecha ON iug.inmueble_scrapeo(fecha_scrapeo DESC);
