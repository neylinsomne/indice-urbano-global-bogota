-- V117: I_SEG Tridimensional
-- Integra tres dimensiones de seguridad:
--   1. Micro-espacial (CAI + sectores priorizados) - ya existente
--   2. Objetiva (criminalidad normalizada por km2 del ICSU)
--   3. Subjetiva (percepcion EPV 2024 del ICSU)
--
-- Justificacion: La correlacion entre criminalidad objetiva y
-- percepcion subjetiva es r=0.3174 (debil). El 44% de localidades
-- exhiben la "paradoja de inseguridad" (baja criminalidad, alta
-- percepcion). El I_SEG anterior solo usaba datos objetivos.

-- ============================================
-- 1. TABLA: Dimensiones ICSU por localidad
-- ============================================
CREATE TABLE IF NOT EXISTS iug.icsu_localidad (
    id_localidad INT PRIMARY KEY REFERENCES iug.localidad(id_localidad),
    nombre_localidad VARCHAR(200),

    -- Dimension objetiva (PCA sobre 7 tipos de delito/km2)
    score_objetivo NUMERIC(8, 4),       -- PC1 criminalidad normalizada
    -- Componentes objetivos (para auditoria)
    homicidios_km2 NUMERIC(10, 6),
    lesiones_km2 NUMERIC(10, 6),
    hurto_personas_km2 NUMERIC(10, 6),
    hurto_residencias_km2 NUMERIC(10, 6),
    hurto_autos_km2 NUMERIC(10, 6),
    delitos_sexuales_km2 NUMERIC(10, 6),
    violencia_intrafamiliar_km2 NUMERIC(10, 6),

    -- Dimension subjetiva (PCA sobre 8 variables EPV 2024)
    score_subjetivo NUMERIC(8, 4),      -- PC1+PC2 percepcion
    -- Componentes subjetivos (para auditoria)
    pct_barrio_inseguro NUMERIC(6, 2),
    pct_victima_delito NUMERIC(6, 2),
    pct_testigo_delito NUMERIC(6, 2),
    pct_percibe_aumento NUMERIC(6, 2),
    score_espacios_publicos NUMERIC(6, 3),
    score_policia NUMERIC(6, 3),
    pct_hogar_victima NUMERIC(6, 2),

    -- Compuesto ICSU (0-5, donde 5 = mas inseguro)
    icsu_compuesto NUMERIC(6, 3),

    -- Cluster de paradoja (1-4)
    cluster_id INTEGER,
    cluster_perfil VARCHAR(100),        -- 'bajo_bajo', 'alto_bajo', 'alto_alto', 'bajo_alto'

    -- Metadata
    fuente_objetiva TEXT DEFAULT 'Secretaria de Seguridad 2024',
    fuente_subjetiva TEXT DEFAULT 'EPV 2024 Camara de Comercio',
    fecha_carga TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE iug.icsu_localidad IS
'ICSU: Indicador Compuesto de Seguridad Urbana por localidad. '
'Combina dimension objetiva (criminalidad) y subjetiva (percepcion EPV). '
'Correlacion entre dimensiones: r=0.3174 (debil, justifica separacion).';

-- ============================================
-- 2. TABLA: Pesos para integracion tridimensional
-- ============================================
CREATE TABLE IF NOT EXISTS iug.pesos_seguridad_tridimensional (
    id SERIAL PRIMARY KEY,
    nombre_perfil VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,

    -- Pesos (suman 1.0)
    peso_micro NUMERIC(5, 4) NOT NULL,     -- CAI + sectores priorizados
    peso_objetivo NUMERIC(5, 4) NOT NULL,  -- Criminalidad ICSU
    peso_subjetivo NUMERIC(5, 4) NOT NULL, -- Percepcion EPV

    activo BOOLEAN DEFAULT FALSE,
    fecha_creacion TIMESTAMP DEFAULT now()
);

INSERT INTO iug.pesos_seguridad_tridimensional
    (nombre_perfil, descripcion, peso_micro, peso_objetivo, peso_subjetivo, activo)
VALUES
    ('equilibrado', 'Balance igual entre las tres dimensiones',
     0.34, 0.33, 0.33, FALSE),
    ('recomendado', 'Micro 40%, objetivo 30%, subjetivo 30% (default)',
     0.40, 0.30, 0.30, TRUE),
    ('objetivo', 'Mayor peso a criminalidad reportada',
     0.30, 0.50, 0.20, FALSE),
    ('percepcion', 'Mayor peso a experiencia vivida (paradoja)',
     0.25, 0.25, 0.50, FALSE)
ON CONFLICT (nombre_perfil) DO NOTHING;

-- ============================================
-- 3. COLUMNAS: Scores tridimensionales en raw
-- ============================================
ALTER TABLE iug.indicador_seguridad_raw
    ADD COLUMN IF NOT EXISTS score_icsu_objetivo NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS score_icsu_subjetivo NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS metodo_calculo VARCHAR(20) DEFAULT 'v21_micro';

COMMENT ON COLUMN iug.indicador_seguridad_raw.score_icsu_objetivo IS
'Dimension objetiva ICSU de la localidad del inmueble (0-5, 5=peor)';
COMMENT ON COLUMN iug.indicador_seguridad_raw.score_icsu_subjetivo IS
'Dimension subjetiva ICSU de la localidad del inmueble (0-5, 5=peor)';

-- ============================================
-- 4. FUNCION: Calcular I_SEG tridimensional
-- ============================================
CREATE OR REPLACE FUNCTION iug.calcular_seguridad_tridimensional(
    p_geom geometry,
    p_tipo_inmueble TEXT DEFAULT NULL
)
RETURNS TABLE(
    score_micro NUMERIC,
    score_objetivo NUMERIC,
    score_subjetivo NUMERIC,
    score_final NUMERIC,
    localidad_nombre TEXT,
    metodo TEXT
) AS $$
DECLARE
    v_micro NUMERIC;
    v_objetivo NUMERIC;
    v_subjetivo NUMERIC;
    v_final NUMERIC;
    v_localidad TEXT;
    v_id_localidad INT;
    -- Pesos activos
    v_peso_micro NUMERIC;
    v_peso_obj NUMERIC;
    v_peso_subj NUMERIC;
    -- Componentes micro (existentes)
    v_cai NUMERIC;
    v_crimen NUMERIC;
    v_sector NUMERIC;
    v_cai_max NUMERIC;
    v_crimen_min NUMERIC;
    v_crimen_max NUMERIC;
    v_peso_cai NUMERIC;
    v_peso_crimen NUMERIC;
    v_peso_sector NUMERIC;
BEGIN
    -- 1. Obtener pesos activos
    SELECT peso_micro, peso_objetivo, peso_subjetivo
    INTO v_peso_micro, v_peso_obj, v_peso_subj
    FROM iug.pesos_seguridad_tridimensional
    WHERE activo = TRUE
    LIMIT 1;

    -- Fallback a recomendado
    v_peso_micro := COALESCE(v_peso_micro, 0.40);
    v_peso_obj := COALESCE(v_peso_obj, 0.30);
    v_peso_subj := COALESCE(v_peso_subj, 0.30);

    -- 2. Calcular dimension micro (CAI + crimen localidad + sector)
    --    Reutiliza la logica existente de V21
    SELECT * INTO v_cai, v_crimen, v_sector, v_localidad
    FROM (
        SELECT
            calc.score_cai,
            calc.score_crimen,
            calc.score_sector,
            calc.localidad
        FROM iug.calcular_seguridad_raw(p_geom) calc
    ) sub;

    -- Obtener parametros de normalizacion
    SELECT cai_max, crimen_min, crimen_max, peso_cai, peso_crimen, peso_sector
    INTO v_cai_max, v_crimen_min, v_crimen_max, v_peso_cai, v_peso_crimen, v_peso_sector
    FROM iug.normalizacion_seguridad
    WHERE tipo_inmueble = COALESCE(p_tipo_inmueble, 'Apartamento');

    v_cai_max := COALESCE(v_cai_max, 2.0);
    v_crimen_min := COALESCE(v_crimen_min, 0);
    v_crimen_max := COALESCE(v_crimen_max, 1);
    v_peso_cai := COALESCE(v_peso_cai, 0.35);
    v_peso_crimen := COALESCE(v_peso_crimen, 0.45);
    v_peso_sector := COALESCE(v_peso_sector, 0.20);

    -- Score micro normalizado 0-5 (logica V21)
    v_micro := LEAST(5, GREATEST(0,
        (v_peso_cai * 5 * LEAST(COALESCE(v_cai, 0), v_cai_max) / NULLIF(v_cai_max, 0)) +
        (v_peso_crimen * (5 - 5 * CASE
            WHEN NULLIF((v_crimen_max - v_crimen_min), 0) > 0 THEN
                (COALESCE(v_crimen, 0) - v_crimen_min) / (v_crimen_max - v_crimen_min)
            ELSE 0.5
        END)) +
        (v_peso_sector * (5 - 5 * COALESCE(v_sector, 0)))
    ));

    -- 3. Obtener dimensiones ICSU de la localidad
    SELECT l.id_localidad INTO v_id_localidad
    FROM iug.localidad l
    WHERE ST_Within(p_geom, l.geom)
    LIMIT 1;

    IF v_id_localidad IS NOT NULL THEN
        SELECT
            -- Invertir: ICSU alto = inseguro, pero I_SEG alto = seguro
            -- Entonces: 5 - score_normalizado
            5.0 - LEAST(5, GREATEST(0, icsu.score_objetivo)),
            5.0 - LEAST(5, GREATEST(0, icsu.score_subjetivo))
        INTO v_objetivo, v_subjetivo
        FROM iug.icsu_localidad icsu
        WHERE icsu.id_localidad = v_id_localidad;
    END IF;

    -- Fallback: si no hay ICSU, usar solo micro
    v_objetivo := COALESCE(v_objetivo, v_micro);
    v_subjetivo := COALESCE(v_subjetivo, v_micro);

    -- 4. Combinar tridimensionalmente
    v_final := LEAST(5, GREATEST(0,
        v_peso_micro * v_micro +
        v_peso_obj * v_objetivo +
        v_peso_subj * v_subjetivo
    ));

    RETURN QUERY SELECT v_micro, v_objetivo, v_subjetivo, v_final,
                        v_localidad,
                        'v117_tridimensional'::TEXT;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION iug.calcular_seguridad_tridimensional IS
'I_SEG tridimensional: combina micro-espacial (CAI/sectores), '
'criminalidad objetiva (ICSU), y percepcion subjetiva (EPV). '
'Formula: I_SEG = w1*micro + w2*objetivo + w3*subjetivo, '
'pesos configurables en pesos_seguridad_tridimensional.';

-- ============================================
-- 5. FUNCION: Actualizar I_SEG de inmuebles existentes
-- ============================================
CREATE OR REPLACE FUNCTION iug.actualizar_seguridad_tridimensional(
    p_tipo_inmueble TEXT DEFAULT NULL
)
RETURNS void AS $$
DECLARE
    v_count INTEGER := 0;
    v_row RECORD;
    v_result RECORD;
BEGIN
    FOR v_row IN
        SELECT id_inmueble, geom, tipo_inmueble
        FROM iug.inmueble
        WHERE geom IS NOT NULL
          AND tipo_inmueble IS NOT NULL
          AND (p_tipo_inmueble IS NULL OR tipo_inmueble = p_tipo_inmueble)
    LOOP
        SELECT * INTO v_result
        FROM iug.calcular_seguridad_tridimensional(v_row.geom, v_row.tipo_inmueble);

        UPDATE iug.indicador_seguridad_raw
        SET score_icsu_objetivo = v_result.score_objetivo,
            score_icsu_subjetivo = v_result.score_subjetivo,
            metodo_calculo = v_result.metodo
        WHERE id_inmueble = v_row.id_inmueble;

        v_count := v_count + 1;
        IF v_count % 500 = 0 THEN
            RAISE NOTICE 'Actualizados % inmuebles...', v_count;
        END IF;
    END LOOP;

    -- Refrescar vista materializada con la nueva formula
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_seguridad_final;

    RAISE NOTICE 'Actualizacion tridimensional completa: % inmuebles', v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 6. VISTA: Resumen de paradoja por localidad
-- ============================================
CREATE OR REPLACE VIEW iug.v_paradoja_seguridad AS
SELECT
    l.nombre AS localidad,
    icsu.score_objetivo,
    icsu.score_subjetivo,
    icsu.icsu_compuesto,
    icsu.cluster_id,
    icsu.cluster_perfil,
    CASE
        WHEN icsu.cluster_perfil = 'bajo_alto' THEN
            'PARADOJA: Baja criminalidad pero alta percepcion de inseguridad'
        WHEN icsu.cluster_perfil = 'alto_bajo' THEN
            'HABITUACION: Alta criminalidad pero baja percepcion'
        WHEN icsu.cluster_perfil = 'bajo_bajo' THEN
            'SEGURO: Baja criminalidad y baja percepcion'
        WHEN icsu.cluster_perfil = 'alto_alto' THEN
            'CRITICO: Alta criminalidad y alta percepcion'
        ELSE 'Sin clasificar'
    END AS interpretacion,
    COUNT(i.id_inmueble) AS total_inmuebles,
    ROUND(AVG(i.iseg)::numeric, 2) AS iseg_promedio_actual,
    ROUND(AVG(i.precio)::numeric, 0) AS precio_promedio
FROM iug.icsu_localidad icsu
JOIN iug.localidad l ON l.id_localidad = icsu.id_localidad
LEFT JOIN iug.inmueble i ON i.id_localidad = icsu.id_localidad
GROUP BY l.nombre, icsu.score_objetivo, icsu.score_subjetivo,
         icsu.icsu_compuesto, icsu.cluster_id, icsu.cluster_perfil
ORDER BY icsu.icsu_compuesto DESC;

COMMENT ON VIEW iug.v_paradoja_seguridad IS
'Resumen de la paradoja de inseguridad por localidad: '
'compara criminalidad objetiva vs percepcion subjetiva, '
'con conteo de inmuebles y I_SEG promedio actual.';
