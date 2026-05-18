-- ============================================================================
-- V10__fix_upsert_and_catalogs.sql
-- Flyway Migration: Corregir f_upsert_inmueble y agregar tipos faltantes
-- ============================================================================

-- 1. Agregar tipos de inmueble faltantes al catálogo
INSERT INTO iug.cat_tipo_inmueble (tipo_inmueble)
VALUES 
    ('Local'),
    ('Bodega'),
    ('Oficina'),
    ('Finca'),
    ('Consultorio'),
    ('Parqueadero'),
    ('Local Comercial'),
    ('Edificio')
ON CONFLICT DO NOTHING;

-- 2. Agregar estados faltantes
INSERT INTO iug.cat_estado_inmueble (estado)
VALUES 
    ('Buen estado'),
    ('Para remodelar'),
    ('Sobre planos'),
    ('Remodelado')
ON CONFLICT DO NOTHING;

-- 3. Recrear función f_upsert_inmueble con referencias de columna explícitas
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
    accion TEXT,
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
    
    -- Buscar existente por codigo_fuente
    SELECT i.* INTO v_existing
    FROM iug.inmueble i
    WHERE i.pagina = p_pagina AND i.codigo_fuente = p_codigo_fuente;
    
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
            -- UPDATE con cambios
            UPDATE iug.inmueble i SET
                precio = COALESCE(p_precio, i.precio),
                area_construida = COALESCE(p_area_construida, i.area_construida),
                habitaciones = COALESCE(p_habitaciones, i.habitaciones),
                banos = COALESCE(p_banos, i.banos),
                estrato = COALESCE(p_estrato, i.estrato),
                ubicacion = COALESCE(p_ubicacion, i.ubicacion),
                direccion = COALESCE(p_direccion, i.direccion),
                geom = COALESCE(v_geom, i.geom),
                image = COALESCE(p_image, i.image),
                descripcion = COALESCE(p_descripcion, i.descripcion),
                n_scrapeos = i.n_scrapeos + 1
            WHERE i.id_inmueble = v_id;
            
            v_accion := 'updated';
        ELSE
            -- Solo touch (sin cambios importantes)
            UPDATE iug.inmueble i SET
                ultima_vista = now(),
                n_scrapeos = i.n_scrapeos + 1
            WHERE i.id_inmueble = v_id;
        END IF;
    END IF;
    
    -- Registrar scrapeo
    INSERT INTO iug.inmueble_scrapeo (id_inmueble, pagina, precio_momento, raw_data)
    VALUES (v_id, p_pagina, p_precio, p_raw_data);
    
    RETURN QUERY SELECT v_id, v_accion, v_cambios;
END;
$$ LANGUAGE plpgsql;

-- Comentario
COMMENT ON FUNCTION iug.f_upsert_inmueble IS 'Upsert corregido: referencias de columna explícitas con alias i.';
