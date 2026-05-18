-- =====================================================
-- Vistas para consultas LLM
-- =====================================================
-- Propósito: Crear vistas optimizadas para que el LLM
-- acceda a datos agregados sin impactar performance

-- Drop vistas existentes para recrear con columnas actualizadas
DROP VIEW IF EXISTS iug.v_estadisticas_localidad CASCADE;
DROP VIEW IF EXISTS iug.v_top_oportunidades CASCADE;
DROP VIEW IF EXISTS iug.v_dotaciones_por_zona CASCADE;
DROP VIEW IF EXISTS iug.v_inmuebles_contexto CASCADE;
DROP VIEW IF EXISTS iug.v_precios_por_tipo CASCADE;
DROP VIEW IF EXISTS iug.v_ranking_zonas CASCADE;

-- Vista: Estadísticas por localidad
CREATE OR REPLACE VIEW iug.v_estadisticas_localidad AS
SELECT
    l.nombre as nombre_localidad,
    COUNT(i.id_inmueble) as total_inmuebles,
    AVG(i.precio)::BIGINT as precio_promedio,
    MIN(i.precio)::BIGINT as precio_minimo,
    MAX(i.precio)::BIGINT as precio_maximo,
    AVG(i.iurb)::NUMERIC(4,2) as iurb_promedio,
    AVG(i.iacc)::NUMERIC(4,2) as iacc_promedio,
    AVG(i.iseg)::NUMERIC(4,2) as iseg_promedio,
    AVG(i.ihed)::NUMERIC(4,2) as ihed_promedio,
    AVG(i.ipnu)::NUMERIC(4,2) as ipnu_promedio,
    AVG(i.precio_por_iurb)::NUMERIC(15,2) as precio_por_iurb_promedio,
    COUNT(CASE WHEN i.tipo_inmueble = 'Apartamento' THEN 1 END) as total_apartamentos,
    COUNT(CASE WHEN i.tipo_inmueble = 'Casa' THEN 1 END) as total_casas,
    l.geom
FROM iug.localidad l
LEFT JOIN iug.inmueble i ON ST_Contains(l.geom, i.geom)
GROUP BY l.nombre, l.geom;

-- Vista: Top inmuebles por oportunidad
CREATE OR REPLACE VIEW iug.v_top_oportunidades AS
SELECT
    i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
    i.iurb,
    i.iacc,
    i.iseg,
    i.ihed,
    i.ipnu,
    i.precio_por_iurb,
    ST_Y(i.geom) as latitud,
    ST_X(i.geom) as longitud,
    PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb ASC) as percentil_oportunidad
FROM iug.inmueble i
WHERE i.iurb IS NOT NULL
  AND i.precio_por_iurb IS NOT NULL
  AND i.iurb >= 3.0;

-- Vista: Resumen de dotaciones por zona
CREATE OR REPLACE VIEW iug.v_dotaciones_por_zona AS
WITH grid AS (
    SELECT
        (ST_SquareGrid(0.01, ST_SetSRID(ST_MakeBox2D(
            ST_Point(-74.2, 4.4),
            ST_Point(-74.0, 4.9)
        ), 4326))).geom
)
SELECT
    g.geom,
    ST_Y(ST_Centroid(g.geom)) as lat_centro,
    ST_X(ST_Centroid(g.geom)) as lon_centro,
    COUNT(CASE WHEN d.categoria IN ('ips', 'farmacia') THEN 1 END) as total_salud,
    COUNT(CASE WHEN d.categoria IN ('colegio', 'universidad') THEN 1 END) as total_educacion,
    COUNT(CASE WHEN d.categoria IN ('centro_comercial', 'plaza_mercado') THEN 1 END) as total_comercio,
    COUNT(CASE WHEN d.categoria IN ('biblioteca', 'teatro') THEN 1 END) as total_cultura,
    COUNT(CASE WHEN d.categoria IN ('parque', 'cancha_futbol') THEN 1 END) as total_recreacion,
    COUNT(d.id) as total_dotaciones
FROM grid g
LEFT JOIN iug.dotaciones_poi d ON ST_Contains(g.geom, d.geom)
GROUP BY g.geom;

-- Vista: Inmuebles con contexto completo
CREATE OR REPLACE VIEW iug.v_inmuebles_contexto AS
SELECT
    i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
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

-- Vista: Comparación de precios por tipo
CREATE OR REPLACE VIEW iug.v_precios_por_tipo AS
SELECT
    tipo_inmueble,
    COUNT(*) as total,
    AVG(precio)::BIGINT as precio_promedio,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY precio)::BIGINT as precio_p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY precio)::BIGINT as precio_mediana,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY precio)::BIGINT as precio_p75,
    MIN(precio)::BIGINT as precio_min,
    MAX(precio)::BIGINT as precio_max,
    AVG(area)::NUMERIC(10,2) as area_promedio,
    AVG(precio / NULLIF(area, 0))::BIGINT as precio_m2_promedio
FROM iug.inmueble
WHERE precio IS NOT NULL AND area IS NOT NULL
GROUP BY tipo_inmueble;

-- Vista: Ranking de zonas por indicador
CREATE OR REPLACE VIEW iug.v_ranking_zonas AS
SELECT
    l.nombre as nombre_localidad,
    AVG(i.iurb)::NUMERIC(4,2) as iurb_promedio,
    AVG(i.iacc)::NUMERIC(4,2) as iacc_promedio,
    AVG(i.iseg)::NUMERIC(4,2) as iseg_promedio,
    AVG(i.ihed)::NUMERIC(4,2) as ihed_promedio,
    AVG(i.ipnu)::NUMERIC(4,2) as ipnu_promedio,
    COUNT(i.id_inmueble) as total_inmuebles,
    RANK() OVER (ORDER BY AVG(i.iurb) DESC) as ranking_iurb,
    RANK() OVER (ORDER BY AVG(i.iacc) DESC) as ranking_iacc,
    RANK() OVER (ORDER BY AVG(i.iseg) DESC) as ranking_iseg,
    RANK() OVER (ORDER BY AVG(i.ihed) DESC) as ranking_ihed,
    RANK() OVER (ORDER BY AVG(i.ipnu) DESC) as ranking_ipnu
FROM iug.localidad l
LEFT JOIN iug.inmueble i ON ST_Contains(l.geom, i.geom)
GROUP BY l.nombre
HAVING COUNT(i.id_inmueble) > 0;

-- Índices para optimizar consultas
CREATE INDEX IF NOT EXISTS idx_inmueble_tipo ON iug.inmueble(tipo_inmueble);
CREATE INDEX IF NOT EXISTS idx_inmueble_precio_iurb ON iug.inmueble(precio_por_iurb) WHERE precio_por_iurb IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dotaciones_categoria ON iug.dotaciones_poi(categoria);

-- Comentarios para documentación
COMMENT ON VIEW iug.v_estadisticas_localidad IS 'Estadísticas agregadas por localidad para consultas LLM';
COMMENT ON VIEW iug.v_top_oportunidades IS 'Ranking de inmuebles por oportunidad (precio/I_URB)';
COMMENT ON VIEW iug.v_dotaciones_por_zona IS 'Grid con conteo de dotaciones por zona (1km x 1km)';
COMMENT ON VIEW iug.v_inmuebles_contexto IS 'Inmuebles con contexto completo (dotaciones, transporte, seguridad)';
COMMENT ON VIEW iug.v_precios_por_tipo IS 'Estadísticas de precios agrupadas por tipo de inmueble';
COMMENT ON VIEW iug.v_ranking_zonas IS 'Ranking de localidades por cada indicador';
