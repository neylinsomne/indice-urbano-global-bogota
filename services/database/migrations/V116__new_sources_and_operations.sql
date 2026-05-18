-- =====================================================
-- V116: Nuevas fuentes de datos y tipos de operación
-- =====================================================

-- 1. Constraint para tipo_operacion (permitir nuevos valores)
ALTER TABLE iug.inmueble DROP CONSTRAINT IF EXISTS chk_tipo_operacion;
ALTER TABLE iug.inmueble ADD CONSTRAINT chk_tipo_operacion
  CHECK (tipo_operacion IN ('Venta', 'Arriendo', 'Subasta', 'REO', 'Preventa'));

-- 2. Catálogo de fuentes de datos
CREATE TABLE IF NOT EXISTS iug.cat_fuente (
    pagina TEXT PRIMARY KEY,
    nombre_display TEXT NOT NULL,
    url TEXT,
    tipo TEXT,
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now()
);

INSERT INTO iug.cat_fuente (pagina, nombre_display, url, tipo) VALUES
    ('finca_raiz', 'FincaRaíz', 'https://www.fincaraiz.com.co', 'portal'),
    ('habi', 'Habi', 'https://habi.co', 'portal'),
    ('properati', 'Properati', 'https://www.properati.com.co', 'api'),
    ('bancolombia_reo', 'Bancolombia REO', 'https://inmobiliariatu360.bancolombia.com', 'banco'),
    ('sae', 'SAE', 'https://www.saesas.gov.co', 'gobierno'),
    ('ciencuadras', 'Ciencuadras', 'https://www.ciencuadras.com', 'portal')
ON CONFLICT DO NOTHING;

-- 3. Índice en pagina para filtrar por fuente
CREATE INDEX IF NOT EXISTS idx_inmueble_pagina ON iug.inmueble(pagina);

-- 4. Actualizar f_upsert_inmueble para aceptar tipo_operacion
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
    p_raw_data JSONB DEFAULT NULL,
    p_tipo_operacion TEXT DEFAULT 'Venta'
)
RETURNS TABLE (id_inmueble INT, accion TEXT, cambios INT) AS $$
DECLARE
    v_id INT;
    v_accion TEXT;
    v_cambios INT := 0;
    v_geom geometry(Point, 4326);
BEGIN
    -- Construir geometría si hay coordenadas
    IF p_lat IS NOT NULL AND p_lon IS NOT NULL
       AND p_lat BETWEEN -90 AND 90 AND p_lon BETWEEN -180 AND 180
       AND ABS(p_lat) > 0.1 AND ABS(p_lon) > 0.1 THEN
        v_geom := ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326);
    END IF;

    -- Intentar UPDATE primero
    UPDATE iug.inmueble SET
        precio = COALESCE(p_precio, precio),
        area_construida = COALESCE(p_area_construida, area_construida),
        habitaciones = COALESCE(p_habitaciones, habitaciones),
        banos = COALESCE(p_banos, banos),
        estrato = COALESCE(p_estrato, estrato),
        tipo_inmueble = COALESCE(NULLIF(p_tipo_inmueble, ''), tipo_inmueble),
        tipo_operacion = COALESCE(NULLIF(p_tipo_operacion, ''), tipo_operacion),
        ubicacion = COALESCE(NULLIF(p_ubicacion, ''), ubicacion),
        direccion = COALESCE(NULLIF(p_direccion, ''), direccion),
        geom = COALESCE(v_geom, geom),
        image = COALESCE(NULLIF(p_image, ''), image),
        descripcion = COALESCE(NULLIF(p_descripcion, ''), descripcion),
        inmobiliaria = COALESCE(NULLIF(p_inmobiliaria, ''), inmobiliaria),
        proyecto = COALESCE(p_proyecto, proyecto),
        ultima_vista = now(),
        n_scrapeos = COALESCE(n_scrapeos, 0) + 1
    WHERE pagina = p_pagina AND codigo_fuente = p_codigo_fuente
    RETURNING iug.inmueble.id_inmueble INTO v_id;

    IF FOUND THEN
        v_accion := 'updated';
        v_cambios := 1;
    ELSE
        -- INSERT
        INSERT INTO iug.inmueble (
            pagina, codigo_fuente, precio, area_construida,
            habitaciones, banos, estrato, tipo_inmueble, tipo_operacion,
            ubicacion, direccion, geom, image, descripcion,
            inmobiliaria, proyecto, primera_vista, ultima_vista, n_scrapeos
        ) VALUES (
            p_pagina, p_codigo_fuente, p_precio, p_area_construida,
            p_habitaciones, p_banos, p_estrato,
            COALESCE(NULLIF(p_tipo_inmueble, ''), 'Inmueble'),
            COALESCE(NULLIF(p_tipo_operacion, ''), 'Venta'),
            p_ubicacion, p_direccion, v_geom, p_image, p_descripcion,
            p_inmobiliaria, COALESCE(p_proyecto, false),
            now(), now(), 1
        )
        RETURNING iug.inmueble.id_inmueble INTO v_id;
        v_accion := 'inserted';
        v_cambios := 1;
    END IF;

    RETURN QUERY SELECT v_id, v_accion, v_cambios;
END;
$$ LANGUAGE plpgsql;
