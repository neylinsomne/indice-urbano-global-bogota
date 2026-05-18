-- V20: Corregir función gravity y agregar seguridad

-- Primero, recrear la función gravity correctamente
CREATE OR REPLACE FUNCTION iug.calcular_score_transporte_gravity(
    p_inmueble_geom geometry,
    p_capa_transporte text,
    p_radio_max integer DEFAULT 500
)
RETURNS NUMERIC AS $$
DECLARE
    v_score_acumulado numeric := 0;
    v_count_features integer := 0;
BEGIN
    -- Acumular score usando query dinámico según la capa
    IF p_capa_transporte = 'transmilenio' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.estacion_transmilenio
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'sitp' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_transport
        WHERE type = 'bus_stop' AND ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'vias' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_main_roads
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'parques' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_parks
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'salud' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.centro_salud
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'educacion_basica' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.colegio
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'educacion_superior' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.universidad
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
        
    ELSIF p_capa_transporte = 'seguridad' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.sector_seguridad
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
    END IF;
    
    RAISE NOTICE '[GRAVITY] Score % = % (de % features en radio %m)', p_capa_transporte, ROUND(v_score_acumulado, 4), v_count_features, p_radio_max;
    
    RETURN v_score_acumulado;
END;
$$ LANGUAGE plpgsql;

-- Tabla para sectores de seguridad (zonas priorizadas)
CREATE TABLE IF NOT EXISTS iug.sector_seguridad (
    id_sector SERIAL PRIMARY KEY,
    codigo VARCHAR(50),
    nombre VARCHAR(200),
    tipo VARCHAR(100),  -- Tipo de sector prioritario
    descripcion TEXT,
    geom geometry(Polygon, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sector_seguridad_geom ON iug.sector_seguridad USING GIST(geom);

COMMENT ON TABLE iug.sector_seguridad IS 'Sectores priorizados de seguridad - zonas de recuperación del espacio público';
