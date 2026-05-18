/*
================================================================================
CALCULO DEL INDICADOR URBANISTICO GLOBAL (I_URB)
================================================================================

Objetivo: Calcular indicador global como suma ponderada de:
- I_ACC (Accesibilidad) - 25%
- I_SEG (Seguridad) - 20%
- I_HED (Calidad Hedónica) - 25%
- I_PNU (Potencial Normativo) - 30%

Formula: I_URB = (0.25×I_ACC + 0.20×I_SEG + 0.25×I_HED + 0.30×I_PNU) / total_pesos

Resultado: Valor entre 0-5 en columna iug.inmueble.iurb
================================================================================
*/

DO $$
DECLARE
    total_actualizados INTEGER := 0;
    total_sin_indicadores INTEGER := 0;
    rec RECORD;
BEGIN
    RAISE NOTICE '========================================================================';
    RAISE NOTICE 'CALCULANDO INDICADOR I_URB (INDICADOR URBANISTICO GLOBAL)';
    RAISE NOTICE '========================================================================';

    -- Verificar si columna iurb existe, si no, crearla
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'iug'
        AND table_name = 'inmueble'
        AND column_name = 'iurb'
    ) THEN
        ALTER TABLE iug.inmueble ADD COLUMN iurb NUMERIC(3,2);
        RAISE NOTICE '[INFO] Columna iurb creada en iug.inmueble';
    END IF;

    RAISE NOTICE '';
    RAISE NOTICE '[INFO] Pesos configurados:';
    RAISE NOTICE '  I_ACC (Accesibilidad):     25%%';
    RAISE NOTICE '  I_SEG (Seguridad):         20%%';
    RAISE NOTICE '  I_HED (Calidad Hedonica):  25%%';
    RAISE NOTICE '  I_PNU (Potencial Normativo): 30%%';
    RAISE NOTICE '';

    -- Calcular I_URB usando suma ponderada normalizada
    -- Solo para inmuebles con al menos 2 indicadores disponibles
    UPDATE iug.inmueble
    SET iurb = (
        COALESCE(iacc * 0.25, 0) +
        COALESCE(iseg * 0.20, 0) +
        COALESCE(ihed * 0.25, 0) +
        COALESCE(ipnu * 0.30, 0)
    ) / (
        (CASE WHEN iacc IS NOT NULL THEN 0.25 ELSE 0 END) +
        (CASE WHEN iseg IS NOT NULL THEN 0.20 ELSE 0 END) +
        (CASE WHEN ihed IS NOT NULL THEN 0.25 ELSE 0 END) +
        (CASE WHEN ipnu IS NOT NULL THEN 0.30 ELSE 0 END)
    )
    WHERE (
        (CASE WHEN iacc IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN iseg IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN ihed IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN ipnu IS NOT NULL THEN 1 ELSE 0 END)
    ) >= 2;  -- Mínimo 2 indicadores

    GET DIAGNOSTICS total_actualizados = ROW_COUNT;

    -- Contar inmuebles sin suficientes indicadores
    SELECT COUNT(*) INTO total_sin_indicadores
    FROM iug.inmueble
    WHERE iurb IS NULL
    AND (
        (CASE WHEN iacc IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN iseg IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN ihed IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN ipnu IS NOT NULL THEN 1 ELSE 0 END)
    ) < 2;

    RAISE NOTICE '';
    RAISE NOTICE '[OK] Inmuebles actualizados: %', total_actualizados;
    RAISE NOTICE '[INFO] Inmuebles sin I_URB (< 2 indicadores): %', total_sin_indicadores;
    RAISE NOTICE '';

    -- Mostrar estadísticas generales
    FOR rec IN
        SELECT
            COUNT(*) as total,
            COUNT(iurb) as con_iurb,
            ROUND(AVG(iurb)::numeric, 2) as promedio,
            ROUND(STDDEV(iurb)::numeric, 2) as desviacion,
            ROUND(MIN(iurb)::numeric, 2) as minimo,
            ROUND(MAX(iurb)::numeric, 2) as maximo,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as p25,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as mediana,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as p75
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
    LOOP
        RAISE NOTICE '[ESTADISTICAS] Distribución del I_URB:';
        RAISE NOTICE '  Total inmuebles:  %', rec.total;
        RAISE NOTICE '  Con I_URB:        %', rec.con_iurb;
        RAISE NOTICE '  Cobertura:        %%%', ROUND((rec.con_iurb::numeric / rec.total * 100), 1);
        RAISE NOTICE '';
        RAISE NOTICE '  Promedio:    %', rec.promedio;
        RAISE NOTICE '  Desv. Est:   %', rec.desviacion;
        RAISE NOTICE '  Mínimo:      %', rec.minimo;
        RAISE NOTICE '  P25:         %', rec.p25;
        RAISE NOTICE '  Mediana:     %', rec.mediana;
        RAISE NOTICE '  P75:         %', rec.p75;
        RAISE NOTICE '  Máximo:      %', rec.maximo;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE '[DISTRIBUCION] Por categoría:';

    -- Distribución por categoría
    FOR rec IN
        SELECT
            CASE
                WHEN iurb >= 4.5 THEN 'Excelente'
                WHEN iurb >= 4.0 THEN 'Muy Bueno'
                WHEN iurb >= 3.5 THEN 'Bueno'
                WHEN iurb >= 3.0 THEN 'Regular'
                WHEN iurb >= 2.5 THEN 'Por Debajo Promedio'
                WHEN iurb >= 2.0 THEN 'Deficiente'
                ELSE 'Muy Deficiente'
            END as categoria,
            COUNT(*) as cantidad,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as porcentaje
        FROM iug.inmueble
        WHERE iurb IS NOT NULL
        GROUP BY categoria
        ORDER BY MIN(iurb) DESC
    LOOP
        RAISE NOTICE '  %: % inmuebles (%%)', RPAD(rec.categoria, 25), LPAD(rec.cantidad::text, 5), rec.porcentaje;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE '[INDICADORES] Cobertura de indicadores base:';

    -- Cobertura de cada indicador
    SELECT
        COUNT(iacc) as n_iacc,
        COUNT(iseg) as n_iseg,
        COUNT(ihed) as n_ihed,
        COUNT(ipnu) as n_ipnu
    INTO rec
    FROM iug.inmueble;

    RAISE NOTICE '  I_ACC (Accesibilidad):     % inmuebles', rec.n_iacc;
    RAISE NOTICE '  I_SEG (Seguridad):         % inmuebles', rec.n_iseg;
    RAISE NOTICE '  I_HED (Calidad Hedonica):  % inmuebles', rec.n_ihed;
    RAISE NOTICE '  I_PNU (Potencial Normativo): % inmuebles', rec.n_ipnu;

    RAISE NOTICE '';
    RAISE NOTICE '========================================================================';
    RAISE NOTICE '[OK] CALCULO DE I_URB COMPLETADO';
    RAISE NOTICE '========================================================================';
END $$;


-- ============================================================================
-- Ver ejemplos de resultados
-- ============================================================================
SELECT
    i.id_inmueble,
    LEFT(i.ubicacion, 40) as ubicacion,
    i.tipo_inmueble,
    ROUND(i.iurb::numeric, 2) as iurb,
    ROUND(i.iacc::numeric, 2) as iacc,
    ROUND(i.iseg::numeric, 2) as iseg,
    ROUND(i.ihed::numeric, 2) as ihed,
    ROUND(i.ipnu::numeric, 2) as ipnu,
    CASE
        WHEN i.iurb >= 4.5 THEN 'Excelente'
        WHEN i.iurb >= 4.0 THEN 'Muy Bueno'
        WHEN i.iurb >= 3.5 THEN 'Bueno'
        WHEN i.iurb >= 3.0 THEN 'Regular'
        WHEN i.iurb >= 2.5 THEN 'Por Debajo Promedio'
        ELSE 'Deficiente'
    END as categoria
FROM iug.inmueble i
WHERE i.iurb IS NOT NULL
ORDER BY i.iurb DESC
LIMIT 10;
