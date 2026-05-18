-- =====================================================
-- V23: Indicador de Dimensión (I_Dim) via PCA
-- =====================================================
-- Componente del indicador hedónico objetivo
-- Usa PCA de variables continuas estructurales
-- Normalización 0-5 usando percentil ranking

-- =====================================================
-- 1. TABLA: Loadings PCA por Tipo de Inmueble
-- =====================================================
CREATE TABLE IF NOT EXISTS iug.pca_loadings_dimension (
    tipo_inmueble VARCHAR(50) PRIMARY KEY,
    
    -- Loadings (φ) de PC1 - cargas factoriales (SOLO variables físicas de tamaño)
    phi_area_construida NUMERIC(10, 8),
    phi_area_privada NUMERIC(10, 8),
    phi_habitaciones NUMERIC(10, 8),
    phi_banos NUMERIC(10, 8),
    
    -- Parámetros de estandarización (para aplicar el modelo)
    mean_area_construida NUMERIC(10, 2),
    std_area_construida NUMERIC(10, 2),
    mean_area_privada NUMERIC(10, 2),
    std_area_privada NUMERIC(10, 2),
    mean_habitaciones NUMERIC(6, 2),
    std_habitaciones NUMERIC(6, 2),
    mean_banos NUMERIC(6, 2),
    std_banos NUMERIC(6, 2),
    
    -- Métricas del PCA
    explained_variance NUMERIC(6, 4),  -- % varianza explicada por PC1
    n_samples INTEGER,
    n_components INTEGER DEFAULT 1,
    
    -- Metadata
    fecha_calculo TIMESTAMP DEFAULT now(),
    version INTEGER DEFAULT 1
);

COMMENT ON TABLE iug.pca_loadings_dimension IS 'Loadings y parámetros del PCA para el componente I_Dim por tipo de inmueble';
COMMENT ON COLUMN iug.pca_loadings_dimension.phi_area_construida IS 'Carga factorial de área construida en PC1';
COMMENT ON COLUMN iug.pca_loadings_dimension.explained_variance IS 'Porcentaje de varianza explicada por primera componente';

-- =====================================================
-- 2. TABLA: Scores Raw I_Dim (PC1)
-- =====================================================
CREATE TABLE IF NOT EXISTS iug.indicador_dimension_raw (
    id_indicador SERIAL PRIMARY KEY,
    id_inmueble BIGINT NOT NULL REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE,
    tipo_inmueble VARCHAR(50),
    
    -- Score PC1 (valor de la primera componente principal)
    pc1_score NUMERIC(12, 6),
    
    -- Variables estandarizadas usadas
    z_area_construida NUMERIC(10, 6),
    z_area_privada NUMERIC(10, 6),
    z_habitaciones NUMERIC(10, 6),
    z_banos NUMERIC(10, 6),
    
    -- Variables originales (para auditoría)
    area_construida NUMERIC(10, 2),
    area_privada NUMERIC(10, 2),
    habitaciones SMALLINT,
    banos SMALLINT,
    
    fecha_calculo TIMESTAMP DEFAULT now(),
    UNIQUE(id_inmueble)
);

CREATE INDEX idx_dimension_raw_tipo ON iug.indicador_dimension_raw(tipo_inmueble);
CREATE INDEX idx_dimension_raw_inmueble ON iug.indicador_dimension_raw(id_inmueble);
CREATE INDEX idx_dimension_raw_pc1 ON iug.indicador_dimension_raw(pc1_score);

COMMENT ON TABLE iug.indicador_dimension_raw IS 'Scores PC1 del PCA para componente de dimensión';
COMMENT ON COLUMN iug.indicador_dimension_raw.pc1_score IS 'Primera componente principal (tamaño/envergadura)';

-- =====================================================
-- 3. VISTA MATERIALIZADA: I_Dim Normalizado (0-5)
-- =====================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS iug.indicador_dimension_final AS
SELECT 
    r.id_inmueble,
    r.tipo_inmueble,
    r.pc1_score,
    
    -- Normalización 0-5 usando PERCENT_RANK (percentil)
    ROUND(
        (5.0 * PERCENT_RANK() OVER (
            PARTITION BY r.tipo_inmueble 
            ORDER BY r.pc1_score
        ))::numeric, 
        4
    ) as i_dim_final,
    
    -- Ranking dentro del tipo
    RANK() OVER (
        PARTITION BY r.tipo_inmueble 
        ORDER BY r.pc1_score DESC
    ) as ranking,
    
    -- Percentil
    ROUND(
        (PERCENT_RANK() OVER (
            PARTITION BY r.tipo_inmueble 
            ORDER BY r.pc1_score
        ) * 100)::numeric, 
        2
    ) as percentil,
    
    r.area_construida,
    r.habitaciones,
    r.banos,
    r.fecha_calculo
FROM iug.indicador_dimension_raw r;

CREATE UNIQUE INDEX idx_dimension_final_inmueble ON iug.indicador_dimension_final(id_inmueble);
CREATE INDEX idx_dimension_final_tipo ON iug.indicador_dimension_final(tipo_inmueble);
CREATE INDEX idx_dimension_final_score ON iug.indicador_dimension_final(i_dim_final);

COMMENT ON MATERIALIZED VIEW iug.indicador_dimension_final IS 'Indicador I_Dim normalizado 0-5 usando percentil ranking';

-- =====================================================
-- 4. FUNCIÓN: Calcular PC1 Individual
-- =====================================================
CREATE OR REPLACE FUNCTION iug.calcular_pc1_dimension(
    p_tipo_inmueble TEXT,
    p_area_construida NUMERIC,
    p_area_privada NUMERIC DEFAULT NULL,
    p_habitaciones INTEGER DEFAULT NULL,
    p_banos INTEGER DEFAULT NULL
) RETURNS NUMERIC AS $$
DECLARE
    v_phi_area NUMERIC;
    v_phi_area_priv NUMERIC;
    v_phi_hab NUMERIC;
    v_phi_banos NUMERIC;
    
    v_mean_area NUMERIC;
    v_std_area NUMERIC;
    v_mean_area_priv NUMERIC;
    v_std_area_priv NUMERIC;
    v_mean_hab NUMERIC;
    v_std_hab NUMERIC;
    v_mean_banos NUMERIC;
    v_std_banos NUMERIC;
    
    v_z_area NUMERIC;
    v_z_area_priv NUMERIC;
    v_z_hab NUMERIC;
    v_z_banos NUMERIC;
    
    v_pc1 NUMERIC;
BEGIN
    -- Validación
    IF p_area_construida IS NULL OR p_area_construida <= 0 THEN
        RETURN NULL;
    END IF;
    
    -- Obtener loadings y parámetros (SOLO variables físicas de tamaño)
    SELECT 
        phi_area_construida, phi_area_privada, phi_habitaciones, phi_banos,
        mean_area_construida, std_area_construida,
        mean_area_privada, std_area_privada,
        mean_habitaciones, std_habitaciones,
        mean_banos, std_banos
    INTO 
        v_phi_area, v_phi_area_priv, v_phi_hab, v_phi_banos,
        v_mean_area, v_std_area,
        v_mean_area_priv, v_std_area_priv,
        v_mean_hab, v_std_hab,
        v_mean_banos, v_std_banos
    FROM iug.pca_loadings_dimension
    WHERE tipo_inmueble = p_tipo_inmueble;
    
    -- Si no existe PCA para este tipo, retornar NULL
    IF v_phi_area IS NULL THEN
        RAISE NOTICE '[PCA] No existe modelo PCA para tipo: %', p_tipo_inmueble;
        RETURN NULL;
    END IF;
    
    -- Estandarizar variables (Z-score)
    v_z_area := CASE WHEN v_std_area > 0 THEN (p_area_construida - v_mean_area) / v_std_area ELSE 0 END;
    v_z_area_priv := CASE WHEN v_std_area_priv > 0 AND p_area_privada IS NOT NULL 
                          THEN (p_area_privada - v_mean_area_priv) / v_std_area_priv ELSE 0 END;
    v_z_hab := CASE WHEN v_std_hab > 0 AND p_habitaciones IS NOT NULL 
                    THEN (p_habitaciones - v_mean_hab) / v_std_hab ELSE 0 END;
    v_z_banos := CASE WHEN v_std_banos > 0 AND p_banos IS NOT NULL 
                      THEN (p_banos - v_mean_banos) / v_std_banos ELSE 0 END;
    
    -- Calcular PC1 = suma de (phi * Z) - SOLO 4 variables físicas
    v_pc1 := (COALESCE(v_phi_area, 0) * v_z_area) +
             (COALESCE(v_phi_area_priv, 0) * v_z_area_priv) +
             (COALESCE(v_phi_hab, 0) * v_z_hab) +
             (COALESCE(v_phi_banos, 0) * v_z_banos);
    
    RAISE NOTICE '[PCA] PC1 calculado: % (tipo: %)', ROUND(v_pc1::numeric, 4), p_tipo_inmueble;
    
    RETURN v_pc1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.calcular_pc1_dimension IS 'Calcula score PC1 para un inmueble usando loadings del PCA';

-- =====================================================
-- 5. FUNCIÓN: Trigger para Calcular I_Dim
-- =====================================================
CREATE OR REPLACE FUNCTION iug.trigger_calcular_dimension()
RETURNS TRIGGER AS $$
DECLARE
    v_pc1 NUMERIC;
    v_z_area NUMERIC;
    v_z_area_priv NUMERIC;
    v_z_hab NUMERIC;
    v_z_banos NUMERIC;
    v_z_estrato NUMERIC;
BEGIN
    -- Solo calcular si hay área válida y tipo
    IF NEW.area_construida IS NOT NULL AND NEW.area_construida > 0 
       AND NEW.tipo_inmueble IS NOT NULL THEN
        
        -- Calcular PC1 (solo variables físicas de tamaño)
        v_pc1 := iug.calcular_pc1_dimension(
            NEW.tipo_inmueble,
            NEW.area_construida,
            NEW.area_privada,
            NEW.habitaciones,
            NEW.banos
        );
        
        -- Si se calculó el PC1
        IF v_pc1 IS NOT NULL THEN
            
            -- Insertar o actualizar
            INSERT INTO iug.indicador_dimension_raw (
                id_inmueble,
                tipo_inmueble,
                pc1_score,
                area_construida,
                area_privada,
                habitaciones,
                banos
            ) VALUES (
                NEW.id_inmueble,
                NEW.tipo_inmueble,
                v_pc1,
                NEW.area_construida,
                NEW.area_privada,
                NEW.habitaciones,
                NEW.banos
            )
            ON CONFLICT (id_inmueble) DO UPDATE SET
                tipo_inmueble = EXCLUDED.tipo_inmueble,
                pc1_score = EXCLUDED.pc1_score,
                area_construida = EXCLUDED.area_construida,
                area_privada = EXCLUDED.area_privada,
                habitaciones = EXCLUDED.habitaciones,
                banos = EXCLUDED.banos,
                fecha_calculo = now();
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Crear trigger
DROP TRIGGER IF EXISTS trg_inmueble_dimension ON iug.inmueble;
CREATE TRIGGER trg_inmueble_dimension
AFTER INSERT OR UPDATE OF area_construida, area_privada, habitaciones, banos, tipo_inmueble
ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.trigger_calcular_dimension();

COMMENT ON TRIGGER trg_inmueble_dimension ON iug.inmueble IS 'Calcula indicador I_Dim automáticamente';

-- =====================================================
-- 6. FUNCIÓN: Refrescar Vista Materializada
-- =====================================================
CREATE OR REPLACE FUNCTION iug.refresh_dimension_final()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_dimension_final;
    RAISE NOTICE '[I_DIM] Vista materializada refrescada';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION iug.refresh_dimension_final IS 'Refresca vista materializada del indicador I_Dim';
