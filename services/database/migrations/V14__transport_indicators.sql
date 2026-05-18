-- V14: Sistema de Indicadores de Transporte con Gravity-based y PCA optimizado
-- Calcula scores gravity UNA VEZ por inmueble, PCA se actualiza por batch

-- ============================================
-- 1. FUNCIÓN: Cálculo Gravity-based (Distancia Manhattan) CON LOGS
-- ============================================
CREATE OR REPLACE FUNCTION iug.calcular_score_transporte_gravity(
    p_inmueble_geom geometry,
    p_capa_transporte text,  -- 'transmilenio', 'sitp', 'vias', 'parques'
    p_radio_max numeric DEFAULT 500
) RETURNS numeric AS $$
DECLARE
    v_score_acumulado numeric := 0;
    v_count_features integer := 0;
    v_geom_type text;
BEGIN
    -- LOG: Inicio de cálculo
    RAISE NOTICE '[GRAVITY] Calculando % para radio=%m', p_capa_transporte, p_radio_max;
    
    -- Verificar tipo de geometría del inmueble
    v_geom_type := GeometryType(p_inmueble_geom);
    RAISE NOTICE '[GRAVITY] Geometría inmueble: %', v_geom_type;
    
    -- Contar features disponibles en la capa
    SELECT COUNT(*) INTO v_count_features FROM (
        SELECT geom FROM iug.estacion_transmilenio WHERE p_capa_transporte = 'transmilenio'
        UNION ALL
        SELECT geom FROM iug.osm_transport WHERE p_capa_transporte = 'sitp' AND type = 'bus_stop'
        UNION ALL
        SELECT geom FROM iug.osm_main_roads WHERE p_capa_transporte = 'vias'
        UNION ALL
        SELECT geom FROM iug.osm_parks WHERE p_capa_transporte = 'parques'
    ) t;
    
    RAISE NOTICE '[GRAVITY] Features en capa %: %', p_capa_transporte, v_count_features;
    
    -- Acumular "fuerza gravitacional" de cada punto de transporte cercano
    -- Formula: Score = Σ(1 - Distancia_Manhattan / RadioMax)
    SELECT COALESCE(SUM(
        GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116))))
            / p_radio_max
        ))
    ), 0) INTO v_score_acumulado
    FROM (
        -- Seleccionar capa según tipo
        SELECT geom FROM iug.estacion_transmilenio WHERE p_capa_transporte = 'transmilenio'
        UNION ALL
        SELECT geom FROM iug.osm_transport WHERE p_capa_transporte = 'sitp' AND type = 'bus_stop'
        UNION ALL
        SELECT geom FROM iug.osm_main_roads WHERE p_capa_transporte = 'vias'
        UNION ALL
        SELECT geom FROM iug.osm_parks WHERE p_capa_transporte = 'parques'
    ) t
    WHERE ST_DWithin(
        ST_Transform(p_inmueble_geom, 3116), 
        ST_Transform(ST_Centroid(t.geom), 3116), 
        p_radio_max
    );
    
    RAISE NOTICE '[GRAVITY] Score calculado para %: % (de % features cercanas)', 
                 p_capa_transporte, v_score_acumulado, v_count_features;
    
    RETURN v_score_acumulado;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- 2. TABLAS: Almacenamiento de Scores
-- ============================================

-- Tabla 1: Scores RAW (se calcula 1 vez por inmueble, NO cambia)
CREATE TABLE IF NOT EXISTS iug.indicador_transporte_raw (
    id_inmueble integer PRIMARY KEY REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble varchar(50) NOT NULL,
    
    -- Scores gravity-based (sin normalizar, pueden ser > 5)
    score_transmilenio_raw numeric(10,4),
    score_sitp_raw numeric(10,4),
    score_vias_raw numeric(10,4),
    score_parques_raw numeric(10,4),
    
    fecha_calculo timestamp DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_tipo ON iug.indicador_transporte_raw(tipo_inmueble);

-- Tabla 2: Pesos PCA por tipo de inmueble (se actualiza esporádicamente)
CREATE TABLE IF NOT EXISTS iug.pca_pesos_tipo (
    tipo_inmueble varchar(50) PRIMARY KEY,
    
    -- Pesos de la Primera Componente Principal
    peso_transmilenio numeric(10,6) DEFAULT 0.25,
    peso_sitp numeric(10,6) DEFAULT 0.25,
    peso_vias numeric(10,6) DEFAULT 0.25,
    peso_parques numeric(10,6) DEFAULT 0.25,
    
    -- Parámetros de normalización (min/max de PC1)
    pc1_min numeric(10,6) DEFAULT 0,
    pc1_max numeric(10,6) DEFAULT 1,
    
    -- Metadata
    pca_version integer DEFAULT 1,
    total_muestras integer DEFAULT 0,  -- Cuántos inmuebles se usaron para calcular PCA
    varianza_explicada numeric(5,4),   -- % varianza explicada por PC1
    fecha_actualizacion timestamp DEFAULT now()
);

-- Inicializar con pesos por defecto (equiponderados)
INSERT INTO iug.pca_pesos_tipo (tipo_inmueble) 
VALUES ('Apartamento'), ('Casa'), ('Lote'), ('Local'), ('Oficina'), ('Bodega')
ON CONFLICT (tipo_inmueble) DO NOTHING;

-- ============================================
-- 3. VISTA MATERIALIZADA: Score Final (raw × pesos)
-- ============================================
CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_transporte_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    
    -- PC1 raw (antes de normalizar)
    (r.score_transmilenio_raw * p.peso_transmilenio + 
     r.score_sitp_raw * p.peso_sitp + 
     r.score_vias_raw * p.peso_vias + 
     r.score_parques_raw * p.peso_parques) as pc1_value,
    
    -- Score final normalizado (0-5)
    CASE 
        WHEN (p.pc1_max - p.pc1_min) > 0 THEN
            5 * ((r.score_transmilenio_raw * p.peso_transmilenio + 
                  r.score_sitp_raw * p.peso_sitp + 
                  r.score_vias_raw * p.peso_vias + 
                  r.score_parques_raw * p.peso_parques) - p.pc1_min) 
                / (p.pc1_max - p.pc1_min)
        ELSE 2.5  -- Valor por defecto si no hay rango
    END as score_transporte_final,
    
    p.pca_version,
    r.fecha_calculo as fecha_calculo_gravity,
    p.fecha_actualizacion as fecha_calculo_pca
    
FROM iug.indicador_transporte_raw r
JOIN iug.pca_pesos_tipo p ON r.tipo_inmueble = p.tipo_inmueble;

-- Índices para consultas rápidas
CREATE UNIQUE INDEX IF NOT EXISTS idx_final_id ON iug.indicador_transporte_final(id_inmueble);
CREATE INDEX IF NOT EXISTS idx_final_tipo ON iug.indicador_transporte_final(tipo_inmueble);

-- ============================================
-- 4. TRIGGER: Auto-cálculo de Scores RAW en INSERT CON LOGS
-- ============================================
CREATE OR REPLACE FUNCTION iug.trigger_calcular_indicadores_raw()
RETURNS TRIGGER AS $$
DECLARE
    v_start_time timestamp;
BEGIN
    -- Solo calcular si tiene geometría válida y tipo
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN
        v_start_time := clock_timestamp();
        
        RAISE NOTICE '[TRIGGER] ========================================';
        RAISE NOTICE '[TRIGGER] Inicio cálculo para inmueble ID=%', NEW.id_inmueble;
        RAISE NOTICE '[TRIGGER] Tipo: %, Ubicación: %', NEW.tipo_inmueble, NEW.ubicacion;
        
        -- Calcular scores gravity-based individuales
        INSERT INTO iug.indicador_transporte_raw (
            id_inmueble, 
            tipo_inmueble,
            score_transmilenio_raw, 
            score_sitp_raw, 
            score_vias_raw, 
            score_parques_raw
        ) VALUES (
            NEW.id_inmueble,
            NEW.tipo_inmueble,
            iug.calcular_score_transporte_gravity(NEW.geom, 'transmilenio', 1000),
            iug.calcular_score_transporte_gravity(NEW.geom, 'sitp', 500),
            iug.calcular_score_transporte_gravity(NEW.geom, 'vias', 300),
            iug.calcular_score_transporte_gravity(NEW.geom, 'parques', 800)
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_transmilenio_raw = EXCLUDED.score_transmilenio_raw,
            score_sitp_raw = EXCLUDED.score_sitp_raw,
            score_vias_raw = EXCLUDED.score_vias_raw,
            score_parques_raw = EXCLUDED.score_parques_raw,
            fecha_calculo = now();
        
        RAISE NOTICE '[TRIGGER] ✅ Scores guardados en indicador_transporte_raw';
        RAISE NOTICE '[TRIGGER] Tiempo total: % ms', 
                     EXTRACT(MILLISECOND FROM clock_timestamp() - v_start_time);
        RAISE NOTICE '[TRIGGER] ========================================';
        
        -- Refrescar la vista materializada (incremental si es posible)
        -- Nota: Para millones de registros, esto se haría en batch
        -- REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_transporte_final;
        
        -- Notificar vía PostgreSQL NOTIFY (para WebSocket)
        -- PERFORM pg_notify('indicadores_actualizados', 
        --     json_build_object(
        --         'timestamp', now(),
        --         'id_inmueble', NEW.id_inmueble
        --     )::text
        -- );
    ELSE
        RAISE NOTICE '[TRIGGER] Inmueble ID=% omitido (geom=%, tipo=%)', 
                     NEW.id_inmueble, 
                     CASE WHEN NEW.geom IS NULL THEN 'NULL' ELSE 'OK' END,
                     COALESCE(NEW.tipo_inmueble, 'NULL');
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inmueble_indicadores_raw
AFTER INSERT OR UPDATE OF geom, tipo_inmueble ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trigger_calcular_indicadores_raw();

-- ============================================
-- 5. FUNCIÓN: Recalcular Vista Materializada
-- ============================================
-- Para refrescar después de batch de scraping o actualización de pesos PCA
CREATE OR REPLACE FUNCTION iug.refresh_indicadores_transporte()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_transporte_final;
    
    -- Notificar vía PostgreSQL NOTIFY (para WebSocket)
    PERFORM pg_notify('indicadores_actualizados', 
        json_build_object(
            'timestamp', now(),
            'action', 'refresh_completed'
        )::text
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 6. COMENTARIOS Y DOCUMENTACIÓN
-- ============================================
COMMENT ON TABLE iug.indicador_transporte_raw IS 
'Scores gravity-based calculados UNA VEZ por inmueble. NO cambian a menos que se actualice la geometría.';

COMMENT ON TABLE iug.pca_pesos_tipo IS 
'Pesos de PCA calculados por batch (ej. después de scraping). Se actualizan esporádicamente usando Python + scikit-learn.';

COMMENT ON MATERIALIZED VIEW iug.indicador_transporte_final IS 
'Score final = raw_scores × pesos_pca. Se refresca después de actualizar pesos o después de batch de inserciones.';

COMMENT ON FUNCTION iug.calcular_score_transporte_gravity IS 
'Calcula score usando metodología Gravity-based con distancia Manhattan. Radio por defecto 500m.';
