/*
================================================================================
RATIO PRECIO/I_URB - ANALISIS DE OPORTUNIDADES
================================================================================

Crea columna y vista materializada para analizar eficiencia precio/calidad:
- precio_por_iurb: Cuánto se paga por cada punto de I_URB
- Valores bajos = Buena oportunidad (alta calidad, bajo precio)
- Valores altos = Sobrevalorado (baja calidad, alto precio)

Uso:
- Ranking de oportunidades
- Comparación mercado vs calidad
- Detección de propiedades subvaloradas
================================================================================
*/

-- ============================================================================
-- PASO 1: Agregar columna precio_por_iurb
-- ============================================================================
ALTER TABLE iug.inmueble
ADD COLUMN IF NOT EXISTS precio_por_iurb NUMERIC(15,2);

COMMENT ON COLUMN iug.inmueble.precio_por_iurb IS
'Ratio precio/I_URB. Valores bajos indican buenas oportunidades (alta calidad urbana, precio razonable)';


-- ============================================================================
-- PASO 2: Función para calcular precio_por_iurb
-- ============================================================================
CREATE OR REPLACE FUNCTION iug.calcular_precio_por_iurb()
RETURNS INTEGER AS $$
DECLARE
    n_actualizados INTEGER;
BEGIN
    UPDATE iug.inmueble
    SET precio_por_iurb = CASE
        WHEN iurb IS NOT NULL AND iurb > 0 AND precio IS NOT NULL AND precio > 0
        THEN ROUND((precio / iurb)::numeric, 2)
        ELSE NULL
    END
    WHERE iurb IS NOT NULL AND precio IS NOT NULL;

    GET DIAGNOSTICS n_actualizados = ROW_COUNT;
    RETURN n_actualizados;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.calcular_precio_por_iurb() IS
'Calcula el ratio precio/I_URB para todos los inmuebles. Retorna número de registros actualizados.';


-- ============================================================================
-- PASO 3: Trigger para actualizar automáticamente
-- ============================================================================
CREATE OR REPLACE FUNCTION iug.trg_actualizar_precio_por_iurb()
RETURNS TRIGGER AS $$
BEGIN
    -- Calcular ratio si ambos valores existen
    IF NEW.iurb IS NOT NULL AND NEW.iurb > 0 AND NEW.precio IS NOT NULL AND NEW.precio > 0 THEN
        NEW.precio_por_iurb := ROUND((NEW.precio / NEW.iurb)::numeric, 2);
    ELSE
        NEW.precio_por_iurb := NULL;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inmueble_precio_por_iurb ON iug.inmueble;

CREATE TRIGGER trg_inmueble_precio_por_iurb
    BEFORE INSERT OR UPDATE OF precio, iurb
    ON iug.inmueble
    FOR EACH ROW
    EXECUTE FUNCTION iug.trg_actualizar_precio_por_iurb();

COMMENT ON TRIGGER trg_inmueble_precio_por_iurb ON iug.inmueble IS
'Actualiza automáticamente precio_por_iurb cuando cambia precio o I_URB';


-- ============================================================================
-- PASO 4: Vista materializada para análisis de oportunidades
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS iug.analisis_oportunidades CASCADE;

CREATE MATERIALIZED VIEW iug.analisis_oportunidades AS
SELECT
    i.id_inmueble,
    i.ubicacion,
    i.tipo_inmueble,
    i.precio,
    i.area,
    i.habitaciones,
    i.banos,

    -- Indicadores
    ROUND(i.iurb::numeric, 2) as iurb,
    ROUND(i.iacc::numeric, 2) as iacc,
    ROUND(i.iseg::numeric, 2) as iseg,
    ROUND(i.ihed::numeric, 2) as ihed,
    ROUND(i.ipnu::numeric, 2) as ipnu,

    -- Ratio y análisis
    ROUND(i.precio_por_iurb::numeric, 2) as precio_por_iurb,
    ROUND((i.precio / NULLIF(i.area, 0))::numeric, 0) as precio_m2,

    -- Percentiles para comparación
    ROUND(PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb)::numeric * 100, 1) as percentil_ratio,
    ROUND(PERCENT_RANK() OVER (PARTITION BY i.tipo_inmueble ORDER BY i.precio_por_iurb)::numeric * 100, 1) as percentil_ratio_tipo,

    -- Categorización de oportunidad
    CASE
        WHEN i.iurb >= 4.0 AND PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb) <= 0.25 THEN 'Excelente Oportunidad'
        WHEN i.iurb >= 3.5 AND PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb) <= 0.33 THEN 'Muy Buena Oportunidad'
        WHEN i.iurb >= 3.0 AND PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb) <= 0.50 THEN 'Buena Oportunidad'
        WHEN PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb) <= 0.50 THEN 'Oportunidad Razonable'
        WHEN PERCENT_RANK() OVER (ORDER BY i.precio_por_iurb) >= 0.75 THEN 'Sobrevalorado'
        ELSE 'Precio Justo'
    END as categoria_oportunidad,

    -- Metadata
    i.fuente,
    i.fecha_publicacion,
    ST_AsText(i.geom) as geom_wkt

FROM iug.inmueble i
WHERE i.precio_por_iurb IS NOT NULL
  AND i.precio IS NOT NULL
  AND i.iurb IS NOT NULL;

-- Índices para performance
CREATE INDEX idx_oportunidades_ratio ON iug.analisis_oportunidades(precio_por_iurb);
CREATE INDEX idx_oportunidades_iurb ON iug.analisis_oportunidades(iurb);
CREATE INDEX idx_oportunidades_precio ON iug.analisis_oportunidades(precio);
CREATE INDEX idx_oportunidades_tipo ON iug.analisis_oportunidades(tipo_inmueble);
CREATE INDEX idx_oportunidades_categoria ON iug.analisis_oportunidades(categoria_oportunidad);

COMMENT ON MATERIALIZED VIEW iug.analisis_oportunidades IS
'Vista materializada para análisis de oportunidades basado en ratio precio/I_URB';


-- ============================================================================
-- PASO 5: Calcular valores iniciales
-- ============================================================================
DO $$
DECLARE
    n_actualizados INTEGER;
BEGIN
    RAISE NOTICE '========================================================================';
    RAISE NOTICE 'CALCULANDO RATIO PRECIO/I_URB';
    RAISE NOTICE '========================================================================';

    SELECT iug.calcular_precio_por_iurb() INTO n_actualizados;

    RAISE NOTICE '';
    RAISE NOTICE '[OK] Calculado precio_por_iurb para % inmuebles', n_actualizados;
    RAISE NOTICE '';

    -- Estadísticas
    RAISE NOTICE '[ESTADISTICAS] Distribución precio/I_URB:';
    DECLARE
        rec RECORD;
    BEGIN
        FOR rec IN
            SELECT
                COUNT(*) as total,
                ROUND(AVG(precio_por_iurb)::numeric, 0) as promedio,
                ROUND(STDDEV(precio_por_iurb)::numeric, 0) as desviacion,
                ROUND(MIN(precio_por_iurb)::numeric, 0) as minimo,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY precio_por_iurb)::numeric, 0) as p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY precio_por_iurb)::numeric, 0) as mediana,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY precio_por_iurb)::numeric, 0) as p75,
                ROUND(MAX(precio_por_iurb)::numeric, 0) as maximo
            FROM iug.inmueble
            WHERE precio_por_iurb IS NOT NULL
        LOOP
            RAISE NOTICE '  Total:       %', rec.total;
            RAISE NOTICE '  Promedio:    $%', rec.promedio;
            RAISE NOTICE '  Desv. Est:   $%', rec.desviacion;
            RAISE NOTICE '  Mínimo:      $%', rec.minimo;
            RAISE NOTICE '  P25:         $%', rec.p25;
            RAISE NOTICE '  Mediana:     $%', rec.mediana;
            RAISE NOTICE '  P75:         $%', rec.p75;
            RAISE NOTICE '  Máximo:      $%', rec.maximo;
        END LOOP;
    END;

    RAISE NOTICE '';
    RAISE NOTICE '========================================================================';
    RAISE NOTICE '[OK] CALCULO COMPLETADO';
    RAISE NOTICE '========================================================================';
END $$;


-- ============================================================================
-- PASO 6: Queries útiles (comentadas)
-- ============================================================================

/*
-- Top 20 mejores oportunidades (alta calidad, bajo precio relativo)
SELECT
    ubicacion,
    tipo_inmueble,
    precio,
    iurb,
    precio_por_iurb,
    categoria_oportunidad
FROM iug.analisis_oportunidades
WHERE iurb >= 3.5  -- Calidad mínima
ORDER BY precio_por_iurb ASC
LIMIT 20;

-- Inmuebles sobrevalorados
SELECT
    ubicacion,
    precio,
    iurb,
    precio_por_iurb,
    percentil_ratio
FROM iug.analisis_oportunidades
WHERE percentil_ratio >= 75
ORDER BY precio_por_iurb DESC
LIMIT 20;

-- Comparar por tipo de inmueble
SELECT
    tipo_inmueble,
    COUNT(*) as n,
    ROUND(AVG(precio)::numeric, 0) as precio_promedio,
    ROUND(AVG(iurb)::numeric, 2) as iurb_promedio,
    ROUND(AVG(precio_por_iurb)::numeric, 0) as ratio_promedio
FROM iug.analisis_oportunidades
GROUP BY tipo_inmueble
ORDER BY ratio_promedio ASC;

-- Refresh vista materializada
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.analisis_oportunidades;
*/
