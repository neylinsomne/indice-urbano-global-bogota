/*
================================================================================
CALCULO DEL INDICADOR NORMATIVO DE POTENCIAL DE USO DEL SUELO (I_PNU)
================================================================================

Objetivo: Calificar el potencial de desarrollo inmobiliario según normativa POT 555

Formula: I_PNU = (0.4 × S_Trat) + (0.4 × S_Alt) + (0.2 × S_Uso)

Donde:
- S_Trat: Score de Tratamiento Urbanístico (1-5)
- S_Alt: Score de Edificabilidad/Altura (1-5)
- S_Uso: Score de Área de Actividad/Uso (1-5)

Resultado: Valor entre 0-5 en columna iug.inmueble.ipnu
================================================================================
*/

-- ============================================================================
-- PASO 1: Crear función de scoring para Tratamiento Urbanístico
-- ============================================================================
CREATE OR REPLACE FUNCTION iug.score_tratamiento(nombre_tratamiento TEXT)
RETURNS NUMERIC AS $$
BEGIN
    RETURN CASE
        -- Renovación Urbana: Máximo potencial de valorización (permite desarrollo nuevo)
        WHEN nombre_tratamiento ILIKE '%renovaci%' THEN 5.0

        -- Desarrollo: Alto potencial (zonas de expansión)
        WHEN nombre_tratamiento ILIKE '%desarrollo%' THEN 4.5

        -- Consolidación: Potencial medio (mejoras permitidas, densificación moderada)
        WHEN nombre_tratamiento ILIKE '%consolidaci%' THEN 3.0

        -- Mejoramiento Integral: Potencial medio-bajo (intervenciones limitadas)
        WHEN nombre_tratamiento ILIKE '%mejoramiento%' THEN 2.0

        -- Conservación: Restricciones fuertes (protección patrimonial/ambiental)
        WHEN nombre_tratamiento ILIKE '%conservaci%' THEN 1.0

        -- Otros casos
        ELSE 2.5
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ============================================================================
-- PASO 2: Crear función de scoring para Edificabilidad
-- ============================================================================
CREATE OR REPLACE FUNCTION iug.score_edificabilidad(rango TEXT)
RETURNS NUMERIC AS $$
BEGIN
    RETURN CASE
        -- Rango 4: Alta edificabilidad (>12 pisos, torres permitidas)
        WHEN rango IN ('4', '4A', '4B', '4C', '4D') THEN 5.0

        -- Rango 3: Media-alta edificabilidad (7-12 pisos)
        WHEN rango = '3' THEN 4.0

        -- Rango 2: Media edificabilidad (4-6 pisos)
        WHEN rango = '2' THEN 3.0

        -- Rango 1: Baja edificabilidad (1-3 pisos)
        WHEN rango = '1' THEN 2.0

        -- N/A o NULL: Asignar score neutral
        ELSE 2.5
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ============================================================================
-- PASO 3: Crear función de scoring para Área de Actividad
-- ============================================================================
CREATE OR REPLACE FUNCTION iug.score_area_actividad(codigo TEXT)
RETURNS NUMERIC AS $$
BEGIN
    RETURN CASE
        -- AAERAE: Área Estructurante Receptora de Actividad Económica
        -- (Comercio y servicios, alto flujo, máximo valor)
        WHEN codigo = 'AAERAE' THEN 5.0

        -- AAGSM: Grandes Servicios Metropolitanos
        -- (Centros comerciales, hospitales, alto valor)
        WHEN codigo = 'AAGSM' THEN 4.5

        -- AAERVIS: Área Estructurante Receptora de Vivienda y Servicios
        -- (Uso mixto residencial-comercial, buen potencial)
        WHEN codigo = 'AAERVIS' THEN 4.0

        -- AAPGSU: Proximidad Generadora de Soporte Urbano
        -- (Servicios de proximidad, potencial medio-alto)
        WHEN codigo = 'AAPGSU' THEN 3.5

        -- AAPRSU: Proximidad Receptora de Soporte Urbano
        -- (Principalmente residencial con servicios básicos)
        WHEN codigo = 'AAPRSU' THEN 3.0

        -- PEMP: Plan Especial de Manejo y Protección
        -- (Patrimonio, restricciones fuertes)
        WHEN codigo = 'PEMP' THEN 1.0

        -- Otros
        ELSE 3.0
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ============================================================================
-- PASO 4: Calcular I_PNU para todos los inmuebles en Bogotá
-- ============================================================================
DO $$
DECLARE
    total_actualizados INTEGER := 0;
    total_sin_pot INTEGER := 0;
    rec RECORD;
BEGIN
    RAISE NOTICE '========================================================================';
    RAISE NOTICE 'CALCULANDO INDICADOR I_PNU (POTENCIAL NORMATIVO DE USO DEL SUELO)';
    RAISE NOTICE '========================================================================';

    -- Actualizar inmuebles que tienen información POT completa
    WITH scores AS (
        SELECT
            i.id_inmueble,
            -- Score Tratamiento (40%)
            COALESCE(
                MAX(iug.score_tratamiento(t.nombre)),
                2.5  -- Valor por defecto si no hay tratamiento
            ) as s_trat,

            -- Score Edificabilidad (40%)
            COALESCE(
                MAX(iug.score_edificabilidad(e.rango)),
                2.5  -- Valor por defecto si no hay edificabilidad
            ) as s_alt,

            -- Score Área de Actividad (20%)
            COALESCE(
                MAX(iug.score_area_actividad(a.codigo)),
                3.0  -- Valor por defecto si no hay área de actividad
            ) as s_uso
        FROM iug.inmueble i
        LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
        LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
        LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
        WHERE i.ubicacion ILIKE '%bogot%'
        AND i.geom IS NOT NULL
        GROUP BY i.id_inmueble
    )
    UPDATE iug.inmueble i
    SET ipnu = LEAST(5.0, GREATEST(0.0,
        (0.4 * s.s_trat) + (0.4 * s.s_alt) + (0.2 * s.s_uso)
    ))
    FROM scores s
    WHERE i.id_inmueble = s.id_inmueble;

    GET DIAGNOSTICS total_actualizados = ROW_COUNT;

    -- Contar inmuebles en Bogotá sin información POT
    SELECT COUNT(*) INTO total_sin_pot
    FROM iug.inmueble
    WHERE ubicacion ILIKE '%bogot%'
    AND ipnu IS NULL
    AND geom IS NOT NULL;

    RAISE NOTICE '';
    RAISE NOTICE '[OK] Inmuebles actualizados: %', total_actualizados;
    RAISE NOTICE '[INFO] Inmuebles sin POT: %', total_sin_pot;
    RAISE NOTICE '';

    -- Mostrar estadísticas
    FOR rec IN
        SELECT
            ROUND(AVG(ipnu)::numeric, 2) as promedio,
            ROUND(STDDEV(ipnu)::numeric, 2) as desviacion,
            MIN(ipnu) as minimo,
            MAX(ipnu) as maximo,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ipnu) as percentil_25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ipnu) as mediana,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ipnu) as percentil_75
        FROM iug.inmueble
        WHERE ipnu IS NOT NULL
    LOOP
        RAISE NOTICE '[ESTADISTICAS] Distribución del I_PNU:';
        RAISE NOTICE '  Promedio:    %', rec.promedio;
        RAISE NOTICE '  Desv. Est:   %', rec.desviacion;
        RAISE NOTICE '  Mínimo:      %', rec.minimo;
        RAISE NOTICE '  P25:         %', rec.percentil_25;
        RAISE NOTICE '  Mediana:     %', rec.mediana;
        RAISE NOTICE '  P75:         %', rec.percentil_75;
        RAISE NOTICE '  Máximo:      %', rec.maximo;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE '========================================================================';
    RAISE NOTICE '[OK] CALCULO DE I_PNU COMPLETADO';
    RAISE NOTICE '========================================================================';
END $$;


-- ============================================================================
-- PASO 5: Ver ejemplos de resultados
-- ============================================================================
SELECT
    i.id_inmueble,
    LEFT(i.ubicacion, 30) as ubicacion,
    t.nombre as tratamiento,
    e.rango as edificabilidad,
    a.codigo as area_actividad,
    ROUND(i.ipnu::numeric, 2) as ipnu
FROM iug.inmueble i
LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
WHERE i.ipnu IS NOT NULL
ORDER BY i.ipnu DESC
LIMIT 10;
