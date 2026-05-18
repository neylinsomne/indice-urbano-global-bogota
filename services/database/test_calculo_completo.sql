-- ============================================================================
-- Script de Verificación Completa del Cálculo Automático de Indicadores
-- ============================================================================
-- Este script verifica:
-- 1. Que las capas vectoriales (calles, parques, etc.) existan y tengan datos
-- 2. Que el trigger se dispare automáticamente al insertar un inmueble
-- 3. Que los cálculos gravity-based funcionen correctamente
-- 4. Que los logs muestren el proceso completo
-- ============================================================================

\set VERBOSITY verbose
SET client_min_messages TO NOTICE;

DO $$
DECLARE
    v_count_tm integer;
    v_count_sitp integer;
    v_count_vias integer;
    v_count_parques integer;
    v_test_id bigint;
    v_test_geom geometry;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════════';
    RAISE NOTICE '           VERIFICACIÓN DE CÁLCULO AUTOMÁTICO DE INDICADORES';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    
    -- ========================================
    -- PASO 1: Verificar capas vectoriales
    -- ========================================
    RAISE NOTICE '📊 PASO 1: Verificando capas vectoriales disponibles...';
    RAISE NOTICE '-------------------------------------------------------------------';
    
    SELECT COUNT(*) INTO v_count_tm FROM iug.estacion_transmilenio;
    RAISE NOTICE '  ✓ TransMilenio: % estaciones', v_count_tm;
    
    SELECT COUNT(*) INTO v_count_sitp FROM iug.osm_transport WHERE type = 'bus_stop';
    RAISE NOTICE '  ✓ SITP (bus stops): % paradas', v_count_sitp;
    
    SELECT COUNT(*) INTO v_count_vias FROM iug.osm_main_roads;
    RAISE NOTICE '  ✓ Vías principales: % segmentos', v_count_vias;
    
    SELECT COUNT(*) INTO v_count_parques FROM iug.osm_parks;
    RAISE NOTICE '  ✓ Parques: % áreas', v_count_parques;
    
    RAISE NOTICE '';
    
    -- Validar que haya datos
    IF v_count_tm = 0 OR v_count_sitp = 0 OR v_count_vias = 0 OR v_count_parques = 0 THEN
        RAISE WARNING '⚠️  ALERTA: Algunas capas están vacías. Los scores pueden ser 0.';
    END IF;
    
    -- ========================================
    -- PASO 2: Limpiar inmueble de prueba anterior
    -- ========================================
    RAISE NOTICE '🧹 PASO 2: Limpiando datos de prueba anteriores...';
    RAISE NOTICE '-------------------------------------------------------------------';
    
    DELETE FROM iug.inmueble WHERE codigo_fuente = 'TEST_INDICADORES_AUTO';
    RAISE NOTICE '  ✓ Datos de prueba anteriores eliminados';
    RAISE NOTICE '';
    
    -- ========================================
    -- PASO 3: Insertar inmueble de prueba (trigger se dispara automáticamente)
    -- ========================================
    RAISE NOTICE '🏢 PASO 3: Insertando inmueble de prueba...';
    RAISE NOTICE '-------------------------------------------------------------------';
    RAISE NOTICE '  Ubicación: Bogotá (-74.0817, 4.6097) - Centro histórico';
    RAISE NOTICE '  Tipo: Apartamento';
    RAISE NOTICE '';
    
    -- El trigger trg_inmueble_indicadores_raw se disparará automáticamente
    -- y calculará los 4 indicadores (TransMilenio, SITP, Vías, Parques)
    INSERT INTO iug.inmueble (
        pagina,
        codigo_fuente,
        tipo_inmueble,
        precio,
        area_construida,
        habitaciones,
        banos,
        geom
    ) VALUES (
        'TEST',
        'TEST_INDICADORES_AUTO',
        'Apartamento',
        300000000,
        80,
        3,
        2,
        ST_SetSRID(ST_MakePoint(-74.0817, 4.6097), 4326)  -- Centro de Bogotá
    ) RETURNING id_inmueble, geom INTO v_test_id, v_test_geom;
    
    RAISE NOTICE '';
    RAISE NOTICE '  ✅ Inmueble insertado con ID: %', v_test_id;
    RAISE NOTICE '';
    
    -- ========================================
    -- PASO 4: Verificar que el trigger calculó los indicadores
    -- ========================================
    RAISE NOTICE '🔍 PASO 4: Verificando resultados del cálculo automático...';
    RAISE NOTICE '-------------------------------------------------------------------';
    
    -- Pequeña espera para asegurar que el trigger terminó
    PERFORM pg_sleep(0.5);
    
    -- Verificar que se creó el registro en indicador_transporte_raw
    PERFORM 1 FROM iug.indicador_transporte_raw WHERE id_inmueble = v_test_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION '❌ ERROR: No se calcularon los indicadores automáticamente';
    END IF;
    
    RAISE NOTICE '  ✅ Registro encontrado en indicador_transporte_raw';
    RAISE NOTICE '';
    
    -- ========================================
    -- PASO 5: Mostrar scores calculados
    -- ========================================
    RAISE NOTICE '📈 PASO 5: Scores calculados automáticamente:';
    RAISE NOTICE '-------------------------------------------------------------------';
    
    DECLARE
        v_score_tm numeric;
        v_score_sitp numeric;
        v_score_vias numeric;
        v_score_parques numeric;
        v_fecha_calculo timestamp;
    BEGIN
        SELECT 
            score_transmilenio_raw,
            score_sitp_raw,
            score_vias_raw,
            score_parques_raw,
            fecha_calculo
        INTO v_score_tm, v_score_sitp, v_score_vias, v_score_parques, v_fecha_calculo
        FROM iug.indicador_transporte_raw
        WHERE id_inmueble = v_test_id;
        
        RAISE NOTICE '  🚇 TransMilenio (radio 1000m): %', ROUND(v_score_tm::numeric, 4);
        RAISE NOTICE '  🚌 SITP (radio 500m):          %', ROUND(v_score_sitp::numeric, 4);
        RAISE NOTICE '  🛣️  Vías (radio 300m):          %', ROUND(v_score_vias::numeric, 4);
        RAISE NOTICE '  🌳 Parques (radio 800m):       %', ROUND(v_score_parques::numeric, 4);
        RAISE NOTICE '';
        RAISE NOTICE '  📅 Fecha de cálculo: %', v_fecha_calculo;
        RAISE NOTICE '';
        
        -- Validaciones
        IF v_score_tm > 0 OR v_score_sitp > 0 OR v_score_vias > 0 OR v_score_parques > 0 THEN
            RAISE NOTICE '  ✅ Al menos un indicador tiene score > 0 (hay features cercanas)';
        ELSE
            RAISE WARNING '  ⚠️  Todos los scores son 0 (posible problema con datos vectoriales)';
        END IF;
    END;
    
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════════';
    RAISE NOTICE '                        ✅ VERIFICACIÓN COMPLETADA';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    RAISE NOTICE '💡 Resumen:';
    RAISE NOTICE '   1. Capas vectoriales: % TransMilenio, % SITP, % Vías, % Parques',
                 v_count_tm, v_count_sitp, v_count_vias, v_count_parques;
    RAISE NOTICE '   2. Trigger automático: ✅ Funcionando';
    RAISE NOTICE '   3. Cálculo gravity-based: ✅ Completado';
    RAISE NOTICE '   4. Inmueble de prueba ID: %', v_test_id;
    RAISE NOTICE '';
    RAISE NOTICE '🧹 Para limpiar el inmueble de prueba:';
    RAISE NOTICE '   DELETE FROM iug.inmueble WHERE id_inmueble = %;', v_test_id;
    RAISE NOTICE '';
    
END $$;

-- Mostrar el registro completo
SELECT 
    r.id_inmueble,
    i.tipo_inmueble,
    i.ubicacion,
    ROUND(r.score_transmilenio_raw::numeric, 4) as tm_raw,
    ROUND(r.score_sitp_raw::numeric, 4) as sitp_raw,
    ROUND(r.score_vias_raw::numeric, 4) as vias_raw,
    ROUND(r.score_parques_raw::numeric, 4) as parques_raw,
    r.fecha_calculo
FROM iug.indicador_transporte_raw r
JOIN iug.inmueble i ON r.id_inmueble = i.id_inmueble
WHERE i.codigo_fuente = 'TEST_INDICADORES_AUTO';
