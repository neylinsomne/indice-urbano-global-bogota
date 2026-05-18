-- Script de prueba para calcular indicadores de UN inmueble y ver los logs

-- 1. Habilitar logging en cliente
\set VERBOSITY verbose
SET client_min_messages TO NOTICE;

-- 2. Seleccionar un inmueble de prueba (el primero con geometría)
DO $$
DECLARE
    v_test_id bigint;
    v_test_geom geometry;
    v_test_tipo text;
BEGIN
    -- Obtener primer inmueble con geometría válida
    SELECT id_inmueble, geom, tipo_inmueble 
    INTO v_test_id, v_test_geom, v_test_tipo
    FROM iug.inmueble 
    WHERE geom IS NOT NULL 
    LIMIT 1;
    
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'PRUEBA DE CÁLCULO DE INDICADORES';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Inmueble ID: %', v_test_id;
    RAISE NOTICE 'Tipo: %', v_test_tipo;
    RAISE NOTICE 'Geometría: % (SRID %)', GeometryType(v_test_geom), ST_SRID(v_test_geom);
    RAISE NOTICE '';
    
    -- Disparar el trigger manualmente forzando un UPDATE
    UPDATE iug.inmueble 
    SET geom = geom  -- Update sin cambiar nada, solo para disparar trigger
    WHERE id_inmueble = v_test_id;
    
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    
    -- Mostrar resultados
    RAISE NOTICE 'RESULTADOS GUARDADOS:';
    PERFORM 
        RAISE NOTICE '  TransMilenio: %', score_transmilenio_raw,
        RAISE NOTICE '  SITP: %', score_sitp_raw,
        RAISE NOTICE '  Vías: %', score_vias_raw,
        RAISE NOTICE '  Parques: %', score_parques_raw
    FROM iug.indicador_transporte_raw
    WHERE id_inmueble = v_test_id;
    
    RAISE NOTICE '═══════════════════════════════════════════════════════';
END $$;

-- 3. Mostrar resultado final en tabla
SELECT 
    id_inmueble,
    tipo_inmueble,
    ROUND(score_transmilenio_raw::numeric, 2) as tm,
    ROUND(score_sitp_raw::numeric, 2) as sitp,
    ROUND(score_vias_raw::numeric, 2) as vias,
    ROUND(score_parques_raw::numeric, 2) as parques,
    fecha_calculo
FROM iug.indicador_transporte_raw
ORDER BY id_inmueble DESC
LIMIT 1;
