-- =====================================================
-- V104: Agregar image y descripcion a v_inmuebles_contexto
-- =====================================================
-- Propósito: Incluir URL de imagen y descripción del inmueble
-- en la vista de contexto para mostrar property cards en el frontend

DROP VIEW IF EXISTS iug.v_inmuebles_contexto CASCADE;

CREATE OR REPLACE VIEW iug.v_inmuebles_contexto AS
SELECT
    i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
    i.image,
    i.descripcion,
    i.iurb,
    i.iacc,
    i.iseg,
    i.ihed,
    i.ipnu,
    i.precio_por_iurb,
    ST_Y(i.geom) as latitud,
    ST_X(i.geom) as longitud,
    l.nombre as nombre_localidad,
    -- Dotaciones cercanas (500m)
    (SELECT COUNT(*) FROM iug.dotaciones_poi d
     WHERE d.categoria IN ('ips', 'farmacia')
     AND ST_DWithin(d.geom::geography, i.geom::geography, 500)) as salud_500m,
    (SELECT COUNT(*) FROM iug.dotaciones_poi d
     WHERE d.categoria IN ('colegio', 'universidad')
     AND ST_DWithin(d.geom::geography, i.geom::geography, 500)) as educacion_500m,
    (SELECT COUNT(*) FROM iug.dotaciones_poi d
     WHERE d.categoria IN ('parque', 'cancha_futbol')
     AND ST_DWithin(d.geom::geography, i.geom::geography, 500)) as recreacion_500m,
    -- Transporte cercano
    (SELECT COUNT(*) FROM iug.estacion_transmilenio e
     WHERE ST_DWithin(e.geom::geography, i.geom::geography, 500)) as transmilenio_500m,
    -- Seguridad
    (SELECT c.hurto_personas_2024 FROM iug.criminalidad_localidad c
     WHERE c.nombre_localidad = l.nombre
     LIMIT 1) as tasa_hurto_localidad
FROM iug.inmueble i
LEFT JOIN iug.localidad l ON ST_Contains(l.geom, i.geom);
