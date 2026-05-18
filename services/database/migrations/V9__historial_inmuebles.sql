-- =============================================================================
-- V9__historial_inmuebles.sql
-- Flyway Migration: Sistema de historial para tracking de cambios
-- =============================================================================

-- 1. Nuevas columnas en inmueble
ALTER TABLE iug.inmueble ADD COLUMN IF NOT EXISTS estado_oferta TEXT DEFAULT 'activo';
ALTER TABLE iug.inmueble ADD COLUMN IF NOT EXISTS primera_vista TIMESTAMP DEFAULT now();
ALTER TABLE iug.inmueble ADD COLUMN IF NOT EXISTS ultima_vista TIMESTAMP DEFAULT now();
ALTER TABLE iug.inmueble ADD COLUMN IF NOT EXISTS n_scrapeos INT DEFAULT 1;

-- Constraint para estado_oferta
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_estado_oferta') THEN
        ALTER TABLE iug.inmueble ADD CONSTRAINT chk_estado_oferta 
        CHECK (estado_oferta IN ('activo', 'vendido', 'agotado', 'inactivo', 'pausado'));
    END IF;
END $$;

-- 2. Tabla de historial de cambios
CREATE TABLE IF NOT EXISTS iug.inmueble_historial (
    id_historial BIGSERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    campo_modificado TEXT NOT NULL,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    fecha_cambio TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_historial_inmueble ON iug.inmueble_historial(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_historial_fecha ON iug.inmueble_historial(fecha_cambio);

-- 3. Tabla de scrapeos individuales
CREATE TABLE IF NOT EXISTS iug.inmueble_scrapeo (
    id_scrapeo BIGSERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    fecha_scrapeo TIMESTAMP DEFAULT now(),
    pagina TEXT NOT NULL,
    precio_momento NUMERIC(14,2),  -- precio en el momento del scrapeo
    raw_data JSONB  -- datos crudos del scraper (opcional)
);

CREATE INDEX IF NOT EXISTS idx_scrapeo_inmueble ON iug.inmueble_scrapeo(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_scrapeo_fecha ON iug.inmueble_scrapeo(fecha_scrapeo);
CREATE INDEX IF NOT EXISTS idx_scrapeo_pagina ON iug.inmueble_scrapeo(pagina);

-- 4. Trigger de auditoría para cambios importantes
CREATE OR REPLACE FUNCTION iug.f_audit_inmueble_changes()
RETURNS TRIGGER AS $$
BEGIN
    -- Registrar cambio de precio
    IF OLD.precio IS DISTINCT FROM NEW.precio THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'precio', OLD.precio::TEXT, NEW.precio::TEXT);
    END IF;
    
    -- Registrar cambio de estado_oferta
    IF OLD.estado_oferta IS DISTINCT FROM NEW.estado_oferta THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'estado_oferta', OLD.estado_oferta, NEW.estado_oferta);
    END IF;
    
    -- Registrar cambio de área
    IF OLD.area_construida IS DISTINCT FROM NEW.area_construida THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'area_construida', OLD.area_construida::TEXT, NEW.area_construida::TEXT);
    END IF;
    
    -- Actualizar ultima_vista
    NEW.ultima_vista := now();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inmueble_audit ON iug.inmueble;
CREATE TRIGGER trg_inmueble_audit
BEFORE UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.f_audit_inmueble_changes();

-- 5. Función para upsert inteligente (usada desde Python)
CREATE OR REPLACE FUNCTION iug.f_upsert_inmueble(
    p_pagina TEXT,
    p_codigo_fuente TEXT,
    p_precio NUMERIC,
    p_area_construida NUMERIC,
    p_habitaciones SMALLINT,
    p_banos SMALLINT,
    p_estrato SMALLINT,
    p_tipo_inmueble TEXT,
    p_ubicacion TEXT,
    p_direccion TEXT,
    p_lat FLOAT,
    p_lon FLOAT,
    p_image TEXT,
    p_descripcion TEXT,
    p_inmobiliaria TEXT,
    p_proyecto BOOLEAN,
    p_raw_data JSONB DEFAULT NULL
)
RETURNS TABLE (
    id_inmueble BIGINT,
    accion TEXT,  -- 'inserted', 'updated', 'unchanged'
    cambios_detectados TEXT[]
) AS $$
DECLARE
    v_existing RECORD;
    v_id BIGINT;
    v_accion TEXT := 'unchanged';
    v_cambios TEXT[] := ARRAY[]::TEXT[];
    v_geom geometry;
BEGIN
    -- Crear geometría si hay coordenadas
    IF p_lat IS NOT NULL AND p_lon IS NOT NULL THEN
        v_geom := ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326);
    END IF;
    
    -- Buscar existente
    SELECT * INTO v_existing
    FROM iug.inmueble
    WHERE pagina = p_pagina AND codigo_fuente = p_codigo_fuente;
    
    IF v_existing IS NULL THEN
        -- INSERT nuevo
        INSERT INTO iug.inmueble (
            pagina, codigo_fuente, precio, area_construida, habitaciones, banos,
            estrato, tipo_inmueble, ubicacion, direccion, geom, image, descripcion,
            inmobiliaria, proyecto, primera_vista, ultima_vista, n_scrapeos
        ) VALUES (
            p_pagina, p_codigo_fuente, p_precio, p_area_construida, p_habitaciones, p_banos,
            p_estrato, p_tipo_inmueble, p_ubicacion, p_direccion, v_geom, p_image, p_descripcion,
            p_inmobiliaria, p_proyecto, now(), now(), 1
        )
        RETURNING iug.inmueble.id_inmueble INTO v_id;
        
        v_accion := 'inserted';
        
    ELSE
        v_id := v_existing.id_inmueble;
        
        -- Detectar cambios
        IF v_existing.precio IS DISTINCT FROM p_precio THEN
            v_cambios := array_append(v_cambios, 'precio');
        END IF;
        IF v_existing.area_construida IS DISTINCT FROM p_area_construida THEN
            v_cambios := array_append(v_cambios, 'area_construida');
        END IF;
        
        IF array_length(v_cambios, 1) > 0 THEN
            -- UPDATE con cambios (el trigger registrará en historial)
            UPDATE iug.inmueble SET
                precio = COALESCE(p_precio, precio),
                area_construida = COALESCE(p_area_construida, area_construida),
                habitaciones = COALESCE(p_habitaciones, habitaciones),
                banos = COALESCE(p_banos, banos),
                estrato = COALESCE(p_estrato, estrato),
                ubicacion = COALESCE(p_ubicacion, ubicacion),
                direccion = COALESCE(p_direccion, direccion),
                geom = COALESCE(v_geom, geom),
                image = COALESCE(p_image, image),
                descripcion = COALESCE(p_descripcion, descripcion),
                n_scrapeos = n_scrapeos + 1
            WHERE id_inmueble = v_id;
            
            v_accion := 'updated';
        ELSE
            -- Solo touch (sin cambios importantes)
            UPDATE iug.inmueble SET
                ultima_vista = now(),
                n_scrapeos = n_scrapeos + 1
            WHERE id_inmueble = v_id;
        END IF;
    END IF;
    
    -- Registrar scrapeo
    INSERT INTO iug.inmueble_scrapeo (id_inmueble, pagina, precio_momento, raw_data)
    VALUES (v_id, p_pagina, p_precio, p_raw_data);
    
    RETURN QUERY SELECT v_id, v_accion, v_cambios;
END;
$$ LANGUAGE plpgsql;

-- 6. Vista para análisis de cambios de precio
CREATE OR REPLACE VIEW iug.v_historial_precios AS
SELECT 
    i.id_inmueble,
    i.codigo_fuente,
    i.pagina,
    i.ubicacion,
    h.valor_anterior::NUMERIC AS precio_anterior,
    h.valor_nuevo::NUMERIC AS precio_nuevo,
    ROUND((h.valor_nuevo::NUMERIC - h.valor_anterior::NUMERIC) / NULLIF(h.valor_anterior::NUMERIC, 0) * 100, 2) AS variacion_pct,
    h.fecha_cambio
FROM iug.inmueble_historial h
JOIN iug.inmueble i ON i.id_inmueble = h.id_inmueble
WHERE h.campo_modificado = 'precio'
ORDER BY h.fecha_cambio DESC;

-- Comentarios
COMMENT ON TABLE iug.inmueble_historial IS 'Registro de cambios en inmuebles (precio, estado, etc.)';
COMMENT ON TABLE iug.inmueble_scrapeo IS 'Registro de cada scrapeo individual por inmueble';
COMMENT ON FUNCTION iug.f_upsert_inmueble IS 'Upsert inteligente: INSERT si nuevo, UPDATE si cambió, TOUCH si igual';
