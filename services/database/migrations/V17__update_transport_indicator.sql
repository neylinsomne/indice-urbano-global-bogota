-- V17: Actualizar indicador de transporte
-- 1. Cambiar radio de vías de 300m a 500m
-- 2. Remover parques (serán parte de indicador de amenidades)

-- Actualizar tabla para remover campo de parques
ALTER TABLE iug.indicador_transporte_raw 
DROP COLUMN IF EXISTS score_parques_raw;

-- Actualizar pesos PCA para remover parques
ALTER TABLE iug.pca_pesos_tipo
DROP COLUMN IF EXISTS peso_parques;

-- Actualizar trigger para calcular solo 3 indicadores con nuevo radio
CREATE OR REPLACE FUNCTION iug.trigger_calcular_indicadores_raw()
RETURNS TRIGGER AS $$
DECLARE
    v_start_time timestamp;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN
        v_start_time := clock_timestamp();
        
        RAISE NOTICE '[TRIGGER] ========================================';
        RAISE NOTICE '[TRIGGER] Inicio cálculo para inmueble ID=%', NEW.id_inmueble;
        RAISE NOTICE '[TRIGGER] Tipo: %, Ubicación: %', NEW.tipo_inmueble, NEW.ubicacion;
        
        -- Calcular solo 3 indicadores de TRANSPORTE
        INSERT INTO iug.indicador_transporte_raw (
            id_inmueble, 
            tipo_inmueble,
            score_transmilenio_raw, 
            score_sitp_raw, 
            score_vias_raw
        ) VALUES (
            NEW.id_inmueble,
            NEW.tipo_inmueble,
            iug.calcular_score_transporte_gravity(NEW.geom, 'transmilenio', 1000),
            iug.calcular_score_transporte_gravity(NEW.geom, 'sitp', 500),
            iug.calcular_score_transporte_gravity(NEW.geom, 'vias', 500)  -- Cambiado a 500m
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_transmilenio_raw = EXCLUDED.score_transmilenio_raw,
            score_sitp_raw = EXCLUDED.score_sitp_raw,
            score_vias_raw = EXCLUDED.score_vias_raw,
            fecha_calculo = now();
        
        RAISE NOTICE '[TRIGGER] ✅ 3 scores de transporte guardados';
        RAISE NOTICE '[TRIGGER] Tiempo: % ms', 
                     EXTRACT(MILLISECOND FROM clock_timestamp() - v_start_time);
        RAISE NOTICE '[TRIGGER] ========================================';
    ELSE
        RAISE NOTICE '[TRIGGER] Inmueble ID=% omitido (geom o tipo nulo)', NEW.id_inmueble;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recrear vista materializada sin parques
DROP MATERIALIZED VIEW IF EXISTS iug.indicador_transporte_final CASCADE;

CREATE MATERIALIZED VIEW iug.indicador_transporte_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    
    -- PC1 raw (3 componentes de transporte)
    (r.score_transmilenio_raw * p.peso_transmilenio + 
     r.score_sitp_raw * p.peso_sitp + 
     r.score_vias_raw * p.peso_vias) as pc1_value,
    
    -- Score final normalizado (0-5)
    CASE 
        WHEN (p.pc1_max - p.pc1_min) > 0 THEN
            5 * ((r.score_transmilenio_raw * p.peso_transmilenio + 
                  r.score_sitp_raw * p.peso_sitp + 
                  r.score_vias_raw * p.peso_vias) - p.pc1_min) 
                / (p.pc1_max - p.pc1_min)
        ELSE 2.5
    END as score_transporte_final,
    
    p.pca_version,
    r.fecha_calculo as fecha_calculo_gravity,
    p.fecha_actualizacion as fecha_calculo_pca
    
FROM iug.indicador_transporte_raw r
JOIN iug.pca_pesos_tipo p ON r.tipo_inmueble = p.tipo_inmueble;

CREATE UNIQUE INDEX idx_final_id ON iug.indicador_transporte_final(id_inmueble);
CREATE INDEX idx_final_tipo ON iug.indicador_transporte_final(tipo_inmueble);

-- Actualizar comentarios
COMMENT ON TABLE iug.indicador_transporte_raw IS 
'Scores gravity-based para 3 capas de TRANSPORTE: TransMilenio (1000m), SITP (500m), Vías (500m)';

COMMENT ON MATERIALIZED VIEW iug.indicador_transporte_final IS
'Score final de transporte (0-5) = raw_scores × pesos_pca';
