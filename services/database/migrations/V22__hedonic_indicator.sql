-- =====================================================
-- V22: Indicador Hedónico (Precios Hedónicos)
-- =====================================================
-- Implementa modelo de regresión ln(Precio/m²) con variables estructurales
-- Normalización 0-5 usando percentil ranking

-- =====================================================
-- 1. TABLA: Coeficientes del Modelo Hedónico
-- =====================================================
CREATE TABLE IF NOT EXISTS iug.hedonic_model_coefs (
    tipo_inmueble VARCHAR(50) PRIMARY KEY,
    
    -- Coeficientes del modelo lineal: ln(precio_m2) = intercept + coef_area*area + ...
    intercept NUMERIC(12, 6) NOT NULL,
    coef_area NUMERIC(12, 6),
    coef_habitaciones NUMERIC(12, 6),
    coef_banos NUMERIC(12, 6),
    coef_parqueaderos NUMERIC(12, 6),
    coef_estrato NUMERIC(12, 6),
    
    -- Métricas del modelo
    r2_score NUMERIC(5, 4),
    rmse NUMERIC(12, 4),
    mae NUMERIC(12, 4),
    n_samples INTEGER,
    
    -- Estadísticas de normalización (para referencia)
    min_score NUMERIC(12, 6),
    max_score NUMERIC(12, 6),
    mean_score NUMERIC(12, 6),
    std_score NUMERIC(12, 6),
    
    -- Metadata
    fecha_entrenamiento TIMESTAMP DEFAULT now(),
    version INTEGER DEFAULT 1
);

COMMENT ON TABLE iug.hedonic_model_coefs IS 'Coeficientes del modelo de precios hedónicos por tipo de inmueble';
COMMENT ON COLUMN iug.hedonic_model_coefs.intercept IS 'Constante α del modelo';
COMMENT ON COLUMN iug.hedonic_model_coefs.coef_area IS 'Coeficiente β para área construida (m²)';
COMMENT ON COLUMN iug.hedonic_model_coefs.r2_score IS 'R² del modelo (bondad de ajuste)';

-- =====================================================
-- 2. TABLA: Scores Raw Hedónicos
-- =====================================================
CREATE TABLE IF NOT EXISTS iug.indicador_hedonic_raw (
    id_indicador SERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble VARCHAR(50),
    
    -- Score raw: predicción del modelo ln(precio_m2)
    score_hedonic_raw NUMERIC(12, 6),
    
    -- Variables usadas en el cálculo (para auditoría)
    area_construida NUMERIC(10, 2),
    habitaciones INTEGER,
    banos INTEGER,
    parqueaderos INTEGER,
    estrato SMALLINT,
    
    -- Precio real (para comparación)
    precio_real NUMERIC(15, 2),
    precio_m2_real NUMERIC(12, 2),
    ln_precio_m2_real NUMERIC(12, 6),
    
    -- Residual (predicción - real)
    residual NUMERIC(12, 6),
    
    fecha_calculo TIMESTAMP DEFAULT now(),
    UNIQUE(id_inmueble)
);

CREATE INDEX idx_hedonic_raw_tipo ON iug.indicador_hedonic_raw(tipo_inmueble);
CREATE INDEX idx_hedonic_raw_inmueble ON iug.indicador_hedonic_raw(id_inmueble);

COMMENT ON TABLE iug.indicador_hedonic_raw IS 'Scores raw del modelo hedónico (escala ln)';
COMMENT ON COLUMN iug.indicador_hedonic_raw.score_hedonic_raw IS 'Predicción del modelo: ln(precio/m²)';
COMMENT ON COLUMN iug.indicador_hedonic_raw.residual IS 'Error: predicción - valor real';

-- =====================================================
-- 3. VISTA MATERIALIZADA: Indicador Final Normalizado (0-5)
-- =====================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_hedonic_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    r.score_hedonic_raw,
    
    -- Normalización 0-5 usando PERCENT_RANK (percentil)
    -- PERCENT_RANK() retorna 0-1, multiplicamos por 5
    ROUND(
        (5.0 * PERCENT_RANK() OVER (
            PARTITION BY r.tipo_inmueble 
            ORDER BY r.score_hedonic_raw
        ))::numeric, 
        4
    ) as score_hedonic_final,
    
    -- Ranking absoluto dentro del tipo
    RANK() OVER (
        PARTITION BY r.tipo_inmueble 
        ORDER BY r.score_hedonic_raw DESC
    ) as ranking,
    
    -- Percentil
    ROUND(
        (PERCENT_RANK() OVER (
            PARTITION BY r.tipo_inmueble 
            ORDER BY r.score_hedonic_raw
        ) * 100)::numeric, 
        2
    ) as percentil,
    
    r.precio_real,
    r.residual,
    r.fecha_calculo
FROM iug.indicador_hedonic_raw r;

CREATE UNIQUE INDEX idx_hedonic_final_inmueble ON iug.indicador_hedonic_final(id_inmueble);
CREATE INDEX idx_hedonic_final_tipo ON iug.indicador_hedonic_final(tipo_inmueble);
CREATE INDEX idx_hedonic_final_score ON iug.indicador_hedonic_final(score_hedonic_final);

COMMENT ON MATERIALIZED VIEW iug.indicador_hedonic_final IS 'Indicador hedónico normalizado 0-5 usando percentil ranking';

-- =====================================================
-- 4. FUNCIÓN: Calcular Score Hedónico Individual
-- =====================================================
CREATE OR REPLACE FUNCTION iug.calcular_score_hedonic(
    p_tipo_inmueble TEXT,
    p_area NUMERIC,
    p_habitaciones INTEGER DEFAULT NULL,
    p_banos INTEGER DEFAULT NULL,
    p_parqueaderos INTEGER DEFAULT NULL,
    p_estrato SMALLINT DEFAULT NULL
) RETURNS NUMERIC AS $$
DECLARE
    v_intercept NUMERIC;
    v_coef_area NUMERIC;
    v_coef_hab NUMERIC;
    v_coef_banos NUMERIC;
    v_coef_parq NUMERIC;
    v_coef_estrato NUMERIC;
    v_score_raw NUMERIC;
BEGIN
    -- Validaciones
    IF p_area IS NULL OR p_area <= 0 THEN
        RETURN NULL;
    END IF;
    
    -- Obtener coeficientes del modelo para este tipo
    SELECT 
        intercept, 
        COALESCE(coef_area, 0),
        COALESCE(coef_habitaciones, 0),
        COALESCE(coef_banos, 0),
        COALESCE(coef_parqueaderos, 0),
        COALESCE(coef_estrato, 0)
    INTO 
        v_intercept, 
        v_coef_area, 
        v_coef_hab, 
        v_coef_banos, 
        v_coef_parq,
        v_coef_estrato
    FROM iug.hedonic_model_coefs
    WHERE tipo_inmueble = p_tipo_inmueble;
    
    -- Si no hay modelo para este tipo, retornar NULL
    IF v_intercept IS NULL THEN
        RAISE NOTICE '[HEDONIC] No existe modelo para tipo: %', p_tipo_inmueble;
        RETURN NULL;
    END IF;
    
    -- Calcular score raw usando la ecuación lineal
    -- ln(precio_m2) = α + β_area*area + β_hab*hab + β_banos*banos + β_parq*parq + β_estrato*estrato
    v_score_raw := v_intercept + 
                   (v_coef_area * p_area) +
                   (v_coef_hab * COALESCE(p_habitaciones, 0)) +
                   (v_coef_banos * COALESCE(p_banos, 0)) +
                   (v_coef_parq * COALESCE(p_parqueaderos, 0)) +
                   (v_coef_estrato * COALESCE(p_estrato, 0));
    
    RAISE NOTICE '[HEDONIC] Score raw calculado: % (tipo: %)', ROUND(v_score_raw::numeric, 4), p_tipo_inmueble;
    
    RETURN v_score_raw;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.calcular_score_hedonic IS 'Calcula score hedónico raw usando coeficientes del modelo';

-- =====================================================
-- 5. FUNCIÓN: Trigger para Calcular Hedónico
-- =====================================================
CREATE OR REPLACE FUNCTION iug.trigger_calcular_hedonic()
RETURNS TRIGGER AS $$
DECLARE
    v_score_raw NUMERIC;
    v_precio_m2 NUMERIC;
    v_ln_precio_m2 NUMERIC;
    v_residual NUMERIC;
BEGIN
    -- Solo calcular si hay área válida
    IF NEW.area_construida IS NOT NULL AND NEW.area_construida > 0 
       AND NEW.tipo_inmueble IS NOT NULL THEN
        
        -- Calcular score usando el modelo
        v_score_raw := iug.calcular_score_hedonic(
            NEW.tipo_inmueble,
            NEW.area_construida,
            NEW.habitaciones,
            NEW.banos,
            NEW.parqueaderos,
            NEW.estrato
        );
        
        -- Si se calculó el score
        IF v_score_raw IS NOT NULL THEN
            
            -- Calcular precio/m2 real si existe precio
            IF NEW.precio IS NOT NULL AND NEW.precio > 0 THEN
                v_precio_m2 := NEW.precio / NEW.area_construida;
                v_ln_precio_m2 := LN(v_precio_m2);
                v_residual := v_score_raw - v_ln_precio_m2;
            END IF;
            
            -- Insertar o actualizar
            INSERT INTO iug.indicador_hedonic_raw (
                id_inmueble,
                tipo_inmueble,
                score_hedonic_raw,
                area_construida,
                habitaciones,
                banos,
                parqueaderos,
                estrato,
                precio_real,
                precio_m2_real,
                ln_precio_m2_real,
                residual
            ) VALUES (
                NEW.id_inmueble,
                NEW.tipo_inmueble,
                v_score_raw,
                NEW.area_construida,
                NEW.habitaciones,
                NEW.banos,
                NEW.parqueaderos,
                NEW.estrato,
                NEW.precio,
                v_precio_m2,
                v_ln_precio_m2,
                v_residual
            )
            ON CONFLICT (id_inmueble) DO UPDATE SET
                tipo_inmueble = EXCLUDED.tipo_inmueble,
                score_hedonic_raw = EXCLUDED.score_hedonic_raw,
                area_construida = EXCLUDED.area_construida,
                habitaciones = EXCLUDED.habitaciones,
                banos = EXCLUDED.banos,
                parqueaderos = EXCLUDED.parqueaderos,
                estrato = EXCLUDED.estrato,
                precio_real = EXCLUDED.precio_real,
                precio_m2_real = EXCLUDED.precio_m2_real,
                ln_precio_m2_real = EXCLUDED.ln_precio_m2_real,
                residual = EXCLUDED.residual,
                fecha_calculo = now();
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Crear trigger
DROP TRIGGER IF EXISTS trg_inmueble_hedonic ON iug.inmueble;
CREATE TRIGGER trg_inmueble_hedonic
AFTER INSERT OR UPDATE OF area_construida, habitaciones, banos, parqueaderos, estrato, tipo_inmueble, precio
ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trigger_calcular_hedonic();

COMMENT ON TRIGGER trg_inmueble_hedonic ON iug.inmueble IS 'Calcula indicador hedónico automáticamente al insertar/actualizar inmueble';

-- =====================================================
-- 6. FUNCIÓN: Refrescar Vista Materializada
-- =====================================================
CREATE OR REPLACE FUNCTION iug.refresh_hedonic_final()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_hedonic_final;
    RAISE NOTICE '[HEDONIC] Vista materializada refrescada';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.refresh_hedonic_final IS 'Refresca la vista materializada del indicador hedónico final';
