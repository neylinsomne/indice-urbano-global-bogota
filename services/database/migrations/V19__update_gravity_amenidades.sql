--V19: Actualizar función gravity para soportar capas de amenidades

CREATE OR REPLACE FUNCTION iug.calcular_score_transporte_gravity(
    p_inmueble_geom geometry,
    p_capa_transporte text,
    p_radio_max integer DEFAULT 500
)
RETURNS NUMERIC AS $$
DECLARE
    v_score_acumulado numeric := 0;
    v_count_features integer := 0;
    v_geom_type text;
BEGIN
    RAISE NOTICE '[GRAVITY] Calculando % para radio=%m', p_capa_transporte, p_radio_max;
    
    v_geom_type := GeometryType(p_inmueble_geom);
    RAISE NOTICE '[GRAVITY] Geometría inmueble: %', v_geom_type;
    
    -- Acumular score gravity-based
    SELECT COALESCE(SUM(
        GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116))))
            / p_radio_max
        ))
    ), 0), 
    COUNT(*) 
    INTO v_score_acumulado, v_count_features
    FROM (
        -- Capas de TRANSPORTE
        SELECT geom FROM iug.estacion_transmilenio WHERE p_capa_transporte = 'transmilenio'
        UNION ALL
        SELECT geom FROM iug.osm_transport WHERE p_capa_transporte = 'sitp' AND type = 'bus_stop'
        UNION ALL
        SELECT geom FROM iug.osm_main_roads WHERE p_capa_transporte = 'vias'
        
        -- Capas de AMENIDADES
        UNION ALL
        SELECT geom FROM iug.osm_parks WHERE p_capa_transporte = 'parques'
        UNION ALL
        SELECT geom FROM iug.centro_salud WHERE p_capa_transporte = 'salud'
        UNION ALL
        SELECT geom FROM iug.colegio WHERE p_capa_transporte = 'educacion_basica'
        UNION ALL
        SELECT geom FROM iug.universidad WHERE p_capa_transporte = 'educacion_superior'
    ) t
    WHERE ST_DWithin(
        ST_Transform(p_inmueble_geom, 3116),
        ST_Transform(ST_Centroid(t.geom), 3116),
        p_radio_max
    );
    
    RAISE NOTICE '[GRAVITY] Score calculado para %: % (de % features cercanas)', p_capa_transporte, ROUND(v_score_acumulado, 4), v_count_features;
    
    RETURN v_score_acumulado;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.calcular_score_transporte_gravity(geometry, text, integer) IS
'Función gravity-based genérica. Capas: transmilenio, sitp, vias, parques, salud, educacion_basica, educacion_superior';
