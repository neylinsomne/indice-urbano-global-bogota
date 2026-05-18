-- V103: Aumentar peso TransMilenio + Estructura Metro
-- A) Subir peso_transmilenio de 0.25 a 0.50
-- B) Crear tabla estacion_metro y preparar columnas/función/trigger/vista para cuando se carguen datos
-- Nota: peso_metro = 0 y score_metro_raw = 0 → no altera scores actuales

-- ============================================================
-- A) SUBIR PESO TRANSMILENIO
-- ============================================================

UPDATE iug.pca_pesos_tipo
SET peso_transmilenio = 0.50,
    fecha_actualizacion = now();

-- ============================================================
-- B) ESTRUCTURA METRO
-- ============================================================

-- 1. Tabla de estaciones de metro
CREATE TABLE IF NOT EXISTS iug.estacion_metro (
    id_estacion SERIAL PRIMARY KEY,
    codigo VARCHAR(20),
    nombre VARCHAR(200) NOT NULL,
    linea VARCHAR(50),               -- 'linea_1', 'linea_2', etc.
    tipo VARCHAR(50) DEFAULT 'estandar',  -- 'estandar', 'intercambio', 'terminal'
    geom geometry(Point, 4326),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_estacion_metro_geom
    ON iug.estacion_metro USING GIST(geom);

COMMENT ON TABLE iug.estacion_metro IS
    'Estaciones del Metro de Bogotá (Primera Línea). Cargar datos cuando estén disponibles.';

-- 2. Columna score_metro_raw en indicador_transporte_raw
ALTER TABLE iug.indicador_transporte_raw
ADD COLUMN IF NOT EXISTS score_metro_raw NUMERIC DEFAULT 0;

-- 3. Columna peso_metro en pca_pesos_tipo (default 0 = no afecta hasta que se carguen estaciones)
ALTER TABLE iug.pca_pesos_tipo
ADD COLUMN IF NOT EXISTS peso_metro NUMERIC DEFAULT 0;

-- 4. Agregar capa 'metro' a la función gravity
CREATE OR REPLACE FUNCTION iug.calcular_score_transporte_gravity(
    p_inmueble_geom geometry,
    p_capa_transporte text,
    p_radio_max integer DEFAULT 500
)
RETURNS NUMERIC AS $$
DECLARE
    v_score_acumulado numeric := 0;
    v_count_features integer := 0;
BEGIN
    IF p_capa_transporte = 'transmilenio' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.estacion_transmilenio
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'sitp' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_transport
        WHERE type = 'bus_stop' AND ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'vias' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_main_roads
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'metro' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.estacion_metro
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'parques' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.osm_parks
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'salud' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.centro_salud
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'educacion_basica' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.colegio
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'educacion_superior' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.universidad
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);

    ELSIF p_capa_transporte = 'seguridad' THEN
        SELECT COALESCE(SUM(GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) +
             ABS(ST_Y(ST_Centroid(ST_Transform(geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116)))) / p_radio_max
        ))), 0), COUNT(*) INTO v_score_acumulado, v_count_features
        FROM iug.sector_seguridad
        WHERE ST_DWithin(ST_Transform(p_inmueble_geom, 3116), ST_Transform(ST_Centroid(geom), 3116), p_radio_max);
    END IF;

    RAISE NOTICE '[GRAVITY] Score % = % (de % features en radio %m)', p_capa_transporte, ROUND(v_score_acumulado, 4), v_count_features, p_radio_max;

    RETURN v_score_acumulado;
END;
$$ LANGUAGE plpgsql;

-- 5. Actualizar trigger para calcular score_metro_raw (radio 1500m)
CREATE OR REPLACE FUNCTION iug.trigger_calcular_indicadores_raw()
RETURNS TRIGGER AS $$
DECLARE
    v_start_time timestamp;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN
        v_start_time := clock_timestamp();

        RAISE NOTICE '[TRIGGER] ========================================';
        RAISE NOTICE '[TRIGGER] Inicio calculo para inmueble ID=%', NEW.id_inmueble;
        RAISE NOTICE '[TRIGGER] Tipo: %, Ubicacion: %', NEW.tipo_inmueble, NEW.ubicacion;

        -- Calcular 4 indicadores de TRANSPORTE (metro incluido)
        INSERT INTO iug.indicador_transporte_raw (
            id_inmueble,
            tipo_inmueble,
            score_transmilenio_raw,
            score_sitp_raw,
            score_vias_raw,
            score_metro_raw
        ) VALUES (
            NEW.id_inmueble,
            NEW.tipo_inmueble,
            iug.calcular_score_transporte_gravity(NEW.geom, 'transmilenio', 1000),
            iug.calcular_score_transporte_gravity(NEW.geom, 'sitp', 500),
            iug.calcular_score_transporte_gravity(NEW.geom, 'vias', 500),
            iug.calcular_score_transporte_gravity(NEW.geom, 'metro', 1500)
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_transmilenio_raw = EXCLUDED.score_transmilenio_raw,
            score_sitp_raw = EXCLUDED.score_sitp_raw,
            score_vias_raw = EXCLUDED.score_vias_raw,
            score_metro_raw = EXCLUDED.score_metro_raw,
            fecha_calculo = now();

        RAISE NOTICE '[TRIGGER] 4 scores de transporte guardados (incl. metro)';
        RAISE NOTICE '[TRIGGER] Tiempo: % ms',
                     EXTRACT(MILLISECOND FROM clock_timestamp() - v_start_time);
        RAISE NOTICE '[TRIGGER] ========================================';
    ELSE
        RAISE NOTICE '[TRIGGER] Inmueble ID=% omitido (geom o tipo nulo)', NEW.id_inmueble;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 6. Recrear vista materializada con 4 componentes
DROP MATERIALIZED VIEW IF EXISTS iug.indicador_transporte_final CASCADE;

CREATE MATERIALIZED VIEW iug.indicador_transporte_final AS
SELECT
    r.id_inmueble,
    r.tipo_inmueble,

    -- PC1 raw (4 componentes de transporte)
    (r.score_transmilenio_raw * p.peso_transmilenio +
     r.score_sitp_raw * p.peso_sitp +
     r.score_vias_raw * p.peso_vias +
     r.score_metro_raw * p.peso_metro) as pc1_value,

    -- Score final normalizado (0-5)
    CASE
        WHEN (p.pc1_max - p.pc1_min) > 0 THEN
            LEAST(5, GREATEST(0,
                5 * ((r.score_transmilenio_raw * p.peso_transmilenio +
                      r.score_sitp_raw * p.peso_sitp +
                      r.score_vias_raw * p.peso_vias +
                      r.score_metro_raw * p.peso_metro) - p.pc1_min)
                    / (p.pc1_max - p.pc1_min)
            ))
        ELSE 2.5
    END as score_transporte_final,

    p.pca_version,
    r.fecha_calculo as fecha_calculo_gravity,
    p.fecha_actualizacion as fecha_calculo_pca

FROM iug.indicador_transporte_raw r
JOIN iug.pca_pesos_tipo p ON r.tipo_inmueble = p.tipo_inmueble;

CREATE UNIQUE INDEX idx_final_id ON iug.indicador_transporte_final(id_inmueble);
CREATE INDEX idx_final_tipo ON iug.indicador_transporte_final(tipo_inmueble);

-- 7. Refresh vista materializada
REFRESH MATERIALIZED VIEW iug.indicador_transporte_final;

-- Comentarios actualizados
COMMENT ON TABLE iug.indicador_transporte_raw IS
    'Scores gravity-based para 4 capas de TRANSPORTE: TransMilenio (1000m), SITP (500m), Vias (500m), Metro (1500m)';

COMMENT ON MATERIALIZED VIEW iug.indicador_transporte_final IS
    'Score final de transporte (0-5) = raw_scores x pesos_pca. Metro con peso_metro=0 hasta que se carguen estaciones.';
