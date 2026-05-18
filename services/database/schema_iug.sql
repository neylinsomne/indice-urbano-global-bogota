--
-- PostgreSQL database dump
--

-- Dumped from database version 16.4 (Debian 16.4-1.pgdg110+2)
-- Dumped by pg_dump version 16.4 (Debian 16.4-1.pgdg110+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: iug; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA iug;


--
-- Name: calcular_idot(public.geometry); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_idot(p_geom public.geometry) RETURNS numeric
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_score_salud NUMERIC := 0;
    v_score_educacion NUMERIC := 0;
    v_score_abastecimiento NUMERIC := 0;
    v_score_cultura NUMERIC := 0;
    v_score_recreacion NUMERIC := 0;
    v_peso RECORD;
    v_idot NUMERIC := 0;
    v_temp_score NUMERIC;
    v_temp_count INTEGER;
BEGIN
    -- Obtener pesos
    FOR v_peso IN SELECT categoria, peso, radio_metros FROM iug.pesos_dotacion WHERE activo LOOP
        CASE v_peso.categoria
            WHEN 'salud' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_salud', v_peso.radio_metros);
                v_score_salud := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'educacion' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_educacion', v_peso.radio_metros);
                v_score_educacion := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'abastecimiento' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_abastecimiento', v_peso.radio_metros);
                v_score_abastecimiento := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'cultura' THEN
                SELECT score, conteo INTO v_temp_score, v_temp_count
                FROM iug.calcular_score_dotacion_categoria(p_geom, 'iug.dotacion_cultura', v_peso.radio_metros);
                v_score_cultura := v_temp_score;
                v_idot := v_idot + (v_peso.peso * v_temp_score);
                
            WHEN 'recreacion' THEN
                -- Usa osm_parks existente + dotacion_recreacion
                SELECT 
                    COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
                INTO v_temp_score
                FROM (
                    SELECT geom FROM iug.dotacion_recreacion 
                    WHERE ST_DWithin(p_geom::geography, geom::geography, v_peso.radio_metros)
                    UNION ALL
                    SELECT ST_Centroid(geom) as geom FROM iug.osm_parks
                    WHERE ST_DWithin(p_geom::geography, ST_Centroid(geom)::geography, v_peso.radio_metros)
                ) combined;
                v_score_recreacion := COALESCE(v_temp_score, 0);
                v_idot := v_idot + (v_peso.peso * v_score_recreacion);
        END CASE;
    END LOOP;
    
    RETURN v_idot;
END;
$$;


--
-- Name: FUNCTION calcular_idot(p_geom public.geometry); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.calcular_idot(p_geom public.geometry) IS 'Calcula I_DOT usando gravity model: ??(peso ?? ??(1/distancia))';


--
-- Name: calcular_idot_poi(public.geometry); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_idot_poi(p_geom public.geometry) RETURNS numeric
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_idot NUMERIC := 0;
    v_temp NUMERIC := 0;
BEGIN
    -- Salud: farmacia + ips + hospital + clinica (peso 0.20, radio 1000m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotaciones_poi
    WHERE categoria IN ('farmacia', 'ips', 'hospital', 'clinica')
      AND ST_DWithin(p_geom::geography, geom::geography, 1000);
    v_idot := v_idot + (0.20 * v_temp);
    
    -- Educacion: colegio + universidad + jardin (peso 0.20, radio 1500m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotaciones_poi
    WHERE categoria IN ('colegio', 'universidad', 'jardin')
      AND ST_DWithin(p_geom::geography, geom::geography, 1500);
    v_idot := v_idot + (0.20 * v_temp);
    
    -- Abastecimiento: centro_comercial + supermercado + plaza_mercado + tienda (peso 0.25, radio 800m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotaciones_poi
    WHERE categoria IN ('centro_comercial', 'supermercado', 'plaza_mercado', 'tienda')
      AND ST_DWithin(p_geom::geography, geom::geography, 800);
    v_idot := v_idot + (0.25 * v_temp);
    
    -- Cultura: biblioteca + teatro + museo (peso 0.15, radio 2000m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotaciones_poi
    WHERE categoria IN ('biblioteca', 'teatro', 'museo')
      AND ST_DWithin(p_geom::geography, geom::geography, 2000);
    v_idot := v_idot + (0.15 * v_temp);
    
    -- Recreacion: parque + cancha + escenario_deportivo (peso 0.20, radio 1500m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotaciones_poi
    WHERE categoria IN ('parque', 'cancha', 'escenario_deportivo')
      AND ST_DWithin(p_geom::geography, geom::geography, 1500);
    v_idot := v_idot + (0.20 * v_temp);
    
    RETURN v_idot;
END;
$$;


--
-- Name: calcular_idot_simple(public.geometry); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_idot_simple(p_geom public.geometry) RETURNS numeric
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_idot NUMERIC := 0;
    v_temp NUMERIC := 0;
BEGIN
    -- Salud (peso 0.20, radio 1000m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotacion_salud
    WHERE ST_DWithin(p_geom::geography, geom::geography, 1000);
    v_idot := v_idot + (0.20 * v_temp);
    
    -- Educacion (peso 0.20, radio 1500m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotacion_educacion
    WHERE ST_DWithin(p_geom::geography, geom::geography, 1500);
    v_idot := v_idot + (0.20 * v_temp);
    
    -- Abastecimiento (peso 0.25, radio 800m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotacion_abastecimiento
    WHERE ST_DWithin(p_geom::geography, geom::geography, 800);
    v_idot := v_idot + (0.25 * v_temp);
    
    -- Cultura (peso 0.15, radio 2000m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, geom::geography), 50)), 0)
    INTO v_temp
    FROM iug.dotacion_cultura
    WHERE ST_DWithin(p_geom::geography, geom::geography, 2000);
    v_idot := v_idot + (0.15 * v_temp);
    
    -- Recreacion: usa osm_parks existente (peso 0.20, radio 1500m)
    SELECT COALESCE(SUM(1.0 / GREATEST(ST_Distance(p_geom::geography, ST_Centroid(geom)::geography), 50)), 0)
    INTO v_temp
    FROM iug.osm_parks
    WHERE ST_DWithin(p_geom::geography, ST_Centroid(geom)::geography, 1500);
    v_idot := v_idot + (0.20 * v_temp);
    
    RETURN v_idot;
END;
$$;


--
-- Name: calcular_precio_por_iurb(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_precio_por_iurb() RETURNS integer
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: FUNCTION calcular_precio_por_iurb(); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.calcular_precio_por_iurb() IS 'Calcula el ratio precio/I_URB para todos los inmuebles. Retorna número de registros actualizados.';


--
-- Name: calcular_score_dotacion_categoria(public.geometry, text, integer); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_score_dotacion_categoria(p_geom public.geometry, p_tabla text, p_radio_m integer) RETURNS TABLE(score numeric, conteo integer)
    LANGUAGE plpgsql STABLE
    AS $_$
DECLARE
    v_score NUMERIC := 0;
    v_count INTEGER := 0;
BEGIN
    -- Gravity model: ??(1 / distancia_metros)
    -- Distancia m??nima = 50m para evitar divisi??n por cero
    EXECUTE format('
        SELECT 
            COALESCE(SUM(1.0 / GREATEST(ST_Distance($1::geography, geom::geography), 50)), 0),
            COUNT(*)
        FROM %I
        WHERE ST_DWithin($1::geography, geom::geography, $2)
    ', p_tabla)
    INTO v_score, v_count
    USING p_geom, p_radio_m;
    
    RETURN QUERY SELECT v_score, v_count;
END;
$_$;


--
-- Name: calcular_score_transporte_gravity(public.geometry, text, integer); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max integer DEFAULT 500) RETURNS numeric
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: FUNCTION calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max integer); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max integer) IS 'Funci??n gravity-based gen??rica. Capas: transmilenio, sitp, vias, parques, salud, educacion_basica, educacion_superior';


--
-- Name: calcular_score_transporte_gravity(public.geometry, text, numeric); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max numeric DEFAULT 500) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    v_score_acumulado numeric := 0;
    v_count_features integer := 0;
    v_geom_type text;
BEGIN
    -- LOG: Inicio de c??lculo
    RAISE NOTICE '[GRAVITY] Calculando % para radio=%m', p_capa_transporte, p_radio_max;
    
    -- Verificar tipo de geometr??a del inmueble
    v_geom_type := GeometryType(p_inmueble_geom);
    RAISE NOTICE '[GRAVITY] Geometr??a inmueble: %', v_geom_type;
    
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
    -- Formula: Score = ??(1 - Distancia_Manhattan / RadioMax)
    SELECT COALESCE(SUM(
        GREATEST(0, 1 - (
            (ABS(ST_X(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_X(ST_Transform(p_inmueble_geom, 3116))) + 
             ABS(ST_Y(ST_Centroid(ST_Transform(t.geom, 3116))) - ST_Y(ST_Transform(p_inmueble_geom, 3116))))
            / p_radio_max
        ))
    ), 0) INTO v_score_acumulado
    FROM (
        -- Seleccionar capa seg??n tipo
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
$$;


--
-- Name: FUNCTION calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max numeric); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.calcular_score_transporte_gravity(p_inmueble_geom public.geometry, p_capa_transporte text, p_radio_max numeric) IS 'Calcula score usando metodolog??a Gravity-based con distancia Manhattan. Radio por defecto 500m.';


--
-- Name: calcular_seguridad_raw(public.geometry); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.calcular_seguridad_raw(p_geom public.geometry) RETURNS TABLE(score_cai numeric, score_crimen numeric, score_sector numeric, localidad text, masa_crimen_val numeric, en_sector boolean, num_cais integer)
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_cai NUMERIC := 0;
    v_crimen NUMERIC := 0;
    v_sector NUMERIC := 0;
    v_localidad TEXT;
    v_masa NUMERIC;
    v_en_sector BOOLEAN := FALSE;
    v_num_cais INTEGER := 0;
BEGIN
    -- 1. CAI (Gravity-based, radio 800m)
    SELECT
        COALESCE(SUM(GREATEST(0, 1 - ST_Distance(
            ST_Transform(p_geom, 3116),
            ST_Transform(cai.geom, 3116)
        ) / 800)), 0),
        COUNT(*)
    INTO v_cai, v_num_cais
    FROM iug.cai_policia cai
    WHERE ST_DWithin(ST_Transform(p_geom, 3116), ST_Transform(cai.geom, 3116), 800);

    -- 2. Crimen (masa de la localidad) - alias 'c' para evitar ambigüedad
    SELECT c.masa_crimen, c.nombre_localidad
    INTO v_masa, v_localidad
    FROM iug.criminalidad_localidad c
    WHERE ST_Within(p_geom, c.geom)
    LIMIT 1;

    v_crimen := COALESCE(v_masa, 0);

    -- 3. Sector priorizado (proximity 0-200m)
    WITH nearest_sector AS (
        SELECT
            ST_Distance(
                ST_Transform(p_geom, 3116),
                ST_Transform(s.geom, 3116)
            ) as dist
        FROM iug.sector_priorizado s
        WHERE ST_DWithin(ST_Transform(p_geom, 3116), ST_Transform(s.geom, 3116), 200)
        ORDER BY dist
        LIMIT 1
    )
    SELECT
        CASE
            WHEN dist = 0 THEN 1.0
            ELSE GREATEST(0, 1 - dist/200)
        END,
        (dist = 0)
    INTO v_sector, v_en_sector
    FROM nearest_sector;

    v_sector := COALESCE(v_sector, 0);

    RETURN QUERY SELECT v_cai, v_crimen, v_sector, v_localidad, v_masa, v_en_sector, v_num_cais;
END;
$$;


--
-- Name: enforce_proyecto_apartamento(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.enforce_proyecto_apartamento() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.proyecto IS TRUE AND NEW.tipo_inmueble <> 'Apartamento' THEN
    RAISE EXCEPTION 'El flag proyecto=TRUE solo aplica a tipo_inmueble=Apartamento';
  END IF;
  RETURN NEW;
END;
$$;


--
-- Name: f_audit_inmueble_changes(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_audit_inmueble_changes() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Registrar cambio de precio
    IF OLD.precio IS DISTINCT FROM NEW.precio THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'precio', OLD.precio::TEXT, NEW.precio::TEXT);
    END IF;
    
    -- Registrar cambio de estado_oferta
    IF OLD.estado_oferta IS DISTINCT FROM NEW.estado_oferta THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'estado_oferta', OLD.estado_oferta, NEW.estado_oferta);
    END IF;
    
    -- Registrar cambio de área
    IF OLD.area_construida IS DISTINCT FROM NEW.area_construida THEN
        INSERT INTO iug.inmueble_historial (id_inmueble, campo_modificado, valor_anterior, valor_nuevo)
        VALUES (NEW.id_inmueble, 'area_construida', OLD.area_construida::TEXT, NEW.area_construida::TEXT);
    END IF;
    
    -- Actualizar ultima_vista
    NEW.ultima_vista := now();
    
    RETURN NEW;
END;
$$;


--
-- Name: f_inmueble_on_barrio_change(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_inmueble_on_barrio_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  rec iug.indicador_barrio%ROWTYPE;
  w1 NUMERIC := 1.0;
  w2 NUMERIC := 1.0;
  w3 NUMERIC := 1.0;
  w4 NUMERIC := 1.0;
  w5 NUMERIC := 1.0;
BEGIN
  IF NEW.id_barrio IS NOT NULL THEN
    SELECT * INTO rec FROM iug.indicador_barrio WHERE id_barrio = NEW.id_barrio;
    IF FOUND THEN
      NEW.iacc := rec.iacc;
      NEW.iseg := rec.iseg;
      NEW.idot := rec.idot;
      NEW.ipnu := rec.ipnu;
      NEW.iug := ROUND((
          COALESCE(NEW.ihed,0)*w1 + COALESCE(NEW.iacc,0)*w2 + COALESCE(NEW.iseg,0)*w3
        + COALESCE(NEW.idot,0)*w4 + COALESCE(NEW.ipnu,0)*w5
      ) / (w1+w2+w3+w4+w5), 3);
      NEW.ratio := CASE
        WHEN NEW.precio_std IS NULL OR NEW.precio_std = 0 THEN NULL
        ELSE ROUND(NEW.iug / NEW.precio_std, 4)
      END;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;


--
-- Name: f_snap_barrio_localidad(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_snap_barrio_localidad() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  loc_id INT;
BEGIN
  IF NEW.geom IS NOT NULL THEN
    SELECT id_localidad INTO loc_id
    FROM iug.localidad
    WHERE ST_Contains(geom, ST_PointOnSurface(NEW.geom))
    LIMIT 1;

    IF loc_id IS NOT NULL THEN
      NEW.id_localidad := loc_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$$;


--
-- Name: f_snap_inmueble_barrios(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_snap_inmueble_barrios() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_barrio RECORD;
BEGIN
    IF NEW.geom IS NOT NULL THEN
        -- Buscar barrio que contiene el punto
        SELECT b.id_barrio, b.id_localidad INTO v_barrio
        FROM iug.barrio b
        WHERE ST_Contains(b.geom, NEW.geom)
        LIMIT 1;

        IF v_barrio.id_barrio IS NOT NULL THEN
            NEW.id_barrio := v_barrio.id_barrio;
            NEW.id_localidad := v_barrio.id_localidad;
            
            -- Copiar indicadores del barrio si existen
            SELECT iacc, iseg, idot, ipnu INTO NEW.iacc, NEW.iseg, NEW.idot, NEW.ipnu
            FROM iug.indicador_barrio
            WHERE id_barrio = v_barrio.id_barrio;
        ELSE
            -- Fallback: buscar localidad directamente
            SELECT l.id_localidad INTO NEW.id_localidad
            FROM iug.localidad l
            WHERE ST_Contains(l.geom, NEW.geom)
            LIMIT 1;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: f_sync_indicadores_barrio(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_sync_indicadores_barrio() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_pesos RECORD;
    v_suma_pesos NUMERIC;
BEGIN
    -- Obtener pesos activos
    SELECT w_hed, w_acc, w_seg, w_dot, w_pnu INTO v_pesos
    FROM iug.pesos_iug WHERE activo = true LIMIT 1;
    
    IF v_pesos IS NULL THEN
        v_pesos := ROW(1.0, 1.0, 1.0, 1.0, 1.0);
    END IF;
    v_suma_pesos := v_pesos.w_hed + v_pesos.w_acc + v_pesos.w_seg + v_pesos.w_dot + v_pesos.w_pnu;

    -- Propagar subíndices a inmuebles del barrio
    UPDATE iug.inmueble i
    SET 
        iacc = NEW.iacc,
        iseg = NEW.iseg,
        idot = NEW.idot,
        ipnu = NEW.ipnu,
        -- Recalcular IUG del inmueble (promedio ponderado)
        iug = ROUND((
            COALESCE(i.ihed, 2.5) * v_pesos.w_hed +
            COALESCE(NEW.iacc, 2.5) * v_pesos.w_acc +
            COALESCE(NEW.iseg, 2.5) * v_pesos.w_seg +
            COALESCE(NEW.idot, 2.5) * v_pesos.w_dot +
            COALESCE(NEW.ipnu, 2.5) * v_pesos.w_pnu
        ) / v_suma_pesos, 3),
        -- Recalcular ratio
        ratio = CASE
            WHEN i.precio_std IS NULL OR i.precio_std = 0 THEN NULL
            ELSE ROUND((
                COALESCE(i.ihed, 2.5) * v_pesos.w_hed +
                COALESCE(NEW.iacc, 2.5) * v_pesos.w_acc +
                COALESCE(NEW.iseg, 2.5) * v_pesos.w_seg +
                COALESCE(NEW.idot, 2.5) * v_pesos.w_dot +
                COALESCE(NEW.ipnu, 2.5) * v_pesos.w_pnu
            ) / v_suma_pesos / i.precio_std, 4)
        END
    WHERE i.id_barrio = NEW.id_barrio;

    -- Timestamp
    NEW.updated_at := now();
    
    RETURN NEW;
END;
$$;


--
-- Name: FUNCTION f_sync_indicadores_barrio(); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.f_sync_indicadores_barrio() IS 'Propaga indicadores de barrio a inmuebles cuando se actualizan. NO calcula, solo sincroniza.';


--
-- Name: f_sync_indicadores_localidad(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_sync_indicadores_localidad() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Propagar valores de localidad a barrios (como fallback si barrio no tiene valores propios)
    UPDATE iug.indicador_barrio ib
    SET 
        iacc = COALESCE(ib.iacc, NEW.iacc),
        iseg = COALESCE(ib.iseg, NEW.iseg),
        idot = COALESCE(ib.idot, NEW.idot),
        ipnu = COALESCE(ib.ipnu, NEW.ipnu),
        updated_at = now()
    FROM iug.barrio b
    WHERE b.id_barrio = ib.id_barrio
      AND b.id_localidad = NEW.id_localidad;
    
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


--
-- Name: FUNCTION f_sync_indicadores_localidad(); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.f_sync_indicadores_localidad() IS 'Propaga indicadores de localidad a barrios (como fallback). NO calcula, solo sincroniza.';


--
-- Name: f_upsert_inmueble(text, text, numeric, numeric, smallint, smallint, smallint, text, text, text, double precision, double precision, text, text, text, boolean, jsonb); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.f_upsert_inmueble(p_pagina text, p_codigo_fuente text, p_precio numeric, p_area_construida numeric, p_habitaciones smallint, p_banos smallint, p_estrato smallint, p_tipo_inmueble text, p_ubicacion text, p_direccion text, p_lat double precision, p_lon double precision, p_image text, p_descripcion text, p_inmobiliaria text, p_proyecto boolean, p_raw_data jsonb DEFAULT NULL::jsonb) RETURNS TABLE(id_inmueble bigint, accion text, cambios_detectados text[])
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_existing RECORD;
    v_id BIGINT;
    v_accion TEXT := 'unchanged';
    v_cambios TEXT[] := ARRAY[]::TEXT[];
    v_geom geometry;
BEGIN
    -- Crear geometría si hay coordenadas
    IF p_lat IS NOT NULL AND p_lon IS NOT NULL THEN
        v_geom := ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326);
    END IF;
    
    -- Buscar existente por codigo_fuente
    SELECT i.* INTO v_existing
    FROM iug.inmueble i
    WHERE i.pagina = p_pagina AND i.codigo_fuente = p_codigo_fuente;
    
    IF v_existing IS NULL THEN
        -- INSERT nuevo
        INSERT INTO iug.inmueble (
            pagina, codigo_fuente, precio, area_construida, habitaciones, banos,
            estrato, tipo_inmueble, ubicacion, direccion, geom, image, descripcion,
            inmobiliaria, proyecto, primera_vista, ultima_vista, n_scrapeos
        ) VALUES (
            p_pagina, p_codigo_fuente, p_precio, p_area_construida, p_habitaciones, p_banos,
            p_estrato, p_tipo_inmueble, p_ubicacion, p_direccion, v_geom, p_image, p_descripcion,
            p_inmobiliaria, p_proyecto, now(), now(), 1
        )
        RETURNING iug.inmueble.id_inmueble INTO v_id;
        
        v_accion := 'inserted';
        
    ELSE
        v_id := v_existing.id_inmueble;
        
        -- Detectar cambios
        IF v_existing.precio IS DISTINCT FROM p_precio THEN
            v_cambios := array_append(v_cambios, 'precio');
        END IF;
        IF v_existing.area_construida IS DISTINCT FROM p_area_construida THEN
            v_cambios := array_append(v_cambios, 'area_construida');
        END IF;
        
        IF array_length(v_cambios, 1) > 0 THEN
            -- UPDATE con cambios
            UPDATE iug.inmueble i SET
                precio = COALESCE(p_precio, i.precio),
                area_construida = COALESCE(p_area_construida, i.area_construida),
                habitaciones = COALESCE(p_habitaciones, i.habitaciones),
                banos = COALESCE(p_banos, i.banos),
                estrato = COALESCE(p_estrato, i.estrato),
                ubicacion = COALESCE(p_ubicacion, i.ubicacion),
                direccion = COALESCE(p_direccion, i.direccion),
                geom = COALESCE(v_geom, i.geom),
                image = COALESCE(p_image, i.image),
                descripcion = COALESCE(p_descripcion, i.descripcion),
                n_scrapeos = i.n_scrapeos + 1
            WHERE i.id_inmueble = v_id;
            
            v_accion := 'updated';
        ELSE
            -- Solo touch (sin cambios importantes)
            UPDATE iug.inmueble i SET
                ultima_vista = now(),
                n_scrapeos = i.n_scrapeos + 1
            WHERE i.id_inmueble = v_id;
        END IF;
    END IF;
    
    -- Registrar scrapeo
    INSERT INTO iug.inmueble_scrapeo (id_inmueble, pagina, precio_momento, raw_data)
    VALUES (v_id, p_pagina, p_precio, p_raw_data);
    
    RETURN QUERY SELECT v_id, v_accion, v_cambios;
END;
$$;


--
-- Name: FUNCTION f_upsert_inmueble(p_pagina text, p_codigo_fuente text, p_precio numeric, p_area_construida numeric, p_habitaciones smallint, p_banos smallint, p_estrato smallint, p_tipo_inmueble text, p_ubicacion text, p_direccion text, p_lat double precision, p_lon double precision, p_image text, p_descripcion text, p_inmobiliaria text, p_proyecto boolean, p_raw_data jsonb); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.f_upsert_inmueble(p_pagina text, p_codigo_fuente text, p_precio numeric, p_area_construida numeric, p_habitaciones smallint, p_banos smallint, p_estrato smallint, p_tipo_inmueble text, p_ubicacion text, p_direccion text, p_lat double precision, p_lon double precision, p_image text, p_descripcion text, p_inmobiliaria text, p_proyecto boolean, p_raw_data jsonb) IS 'Upsert corregido: referencias de columna explícitas con alias i.';


--
-- Name: recalcular_dotacion_masivo(integer); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.recalcular_dotacion_masivo(p_limit integer DEFAULT NULL::integer) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_count INTEGER := 0;
    v_inmueble RECORD;
    v_idot NUMERIC;
BEGIN
    FOR v_inmueble IN 
        SELECT id_inmueble, geom 
        FROM iug.inmueble 
        WHERE geom IS NOT NULL
        LIMIT p_limit
    LOOP
        v_idot := iug.calcular_idot_simple(v_inmueble.geom);
        
        INSERT INTO iug.indicador_dotacion_raw (id_inmueble, idot_raw)
        VALUES (v_inmueble.id_inmueble, v_idot)
        ON CONFLICT (id_inmueble) DO UPDATE SET
            idot_raw = EXCLUDED.idot_raw,
            fecha_calculo = now();
        
        v_count := v_count + 1;
    END LOOP;
    
    RETURN v_count;
END;
$$;


--
-- Name: recalcular_dotacion_poi(integer); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.recalcular_dotacion_poi(p_limit integer DEFAULT NULL::integer) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_count INTEGER := 0;
    v_inmueble RECORD;
    v_idot NUMERIC;
BEGIN
    FOR v_inmueble IN 
        SELECT id_inmueble, geom 
        FROM iug.inmueble 
        WHERE geom IS NOT NULL
        LIMIT p_limit
    LOOP
        v_idot := iug.calcular_idot_poi(v_inmueble.geom);
        
        INSERT INTO iug.indicador_dotacion_raw (id_inmueble, idot_raw)
        VALUES (v_inmueble.id_inmueble, v_idot)
        ON CONFLICT (id_inmueble) DO UPDATE SET
            idot_raw = EXCLUDED.idot_raw,
            fecha_calculo = now();
        
        v_count := v_count + 1;
    END LOOP;
    
    RETURN v_count;
END;
$$;


--
-- Name: recalcular_normalizacion_seguridad(text); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.recalcular_normalizacion_seguridad(p_tipo_inmueble text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tipo TEXT;
BEGIN
    FOR v_tipo IN 
        SELECT DISTINCT tipo_inmueble 
        FROM iug.indicador_seguridad_raw
        WHERE (p_tipo_inmueble IS NULL OR tipo_inmueble  = p_tipo_inmueble)
    LOOP
        UPDATE iug.normalizacion_seguridad n
        SET 
            cai_min = stats.cai_min,
            cai_max = stats.cai_max,
            crimen_min = stats.crimen_min,
            crimen_max = stats.crimen_max,
            sector_min = 0,
            sector_max = 1,
            total_muestras = stats.total,
            fecha_actualizacion = now()
        FROM (
            SELECT 
                MIN(score_cai_raw) as cai_min,
                LEAST(MAX(score_cai_raw), 2.0) as cai_max,  -- Saturar en 2
                MIN(score_crimen_raw) as crimen_min,
                MAX(score_crimen_raw) as crimen_max,
                COUNT(*) as total
            FROM iug.indicador_seguridad_raw
            WHERE tipo_inmueble = v_tipo
        ) stats
        WHERE n.tipo_inmueble = v_tipo;
        
        RAISE NOTICE 'Actualizada normalizaci??n para %', v_tipo;
    END LOOP;
    
    -- Refrescar vista materializada
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_seguridad_final;
END;
$$;


--
-- Name: FUNCTION recalcular_normalizacion_seguridad(p_tipo_inmueble text); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.recalcular_normalizacion_seguridad(p_tipo_inmueble text) IS 'Recalcula min/max para normalizaci??n desde los datos actuales del dataset';


--
-- Name: refresh_indicadores_transporte(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.refresh_indicadores_transporte() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_transporte_final;
    
    -- Notificar v??a PostgreSQL NOTIFY (para WebSocket)
    PERFORM pg_notify('indicadores_actualizados', 
        json_build_object(
            'timestamp', now(),
            'action', 'refresh_completed'
        )::text
    );
END;
$$;


--
-- Name: score_area_actividad(text); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.score_area_actividad(codigo text) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
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
$$;


--
-- Name: score_edificabilidad(text); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.score_edificabilidad(rango text) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
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
$$;


--
-- Name: score_tratamiento(text); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.score_tratamiento(nombre_tratamiento text) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
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
$$;


--
-- Name: trg_actualizar_iurb(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.trg_actualizar_iurb() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Calcular I_URB con suma ponderada normalizada
    -- Solo si hay al menos 2 indicadores disponibles
    DECLARE
        n_indicadores INTEGER;
        suma_ponderada NUMERIC;
        total_pesos NUMERIC;
    BEGIN
        -- Contar indicadores disponibles
        n_indicadores :=
            (CASE WHEN NEW.iacc IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN NEW.iseg IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN NEW.ihed IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN NEW.ipnu IS NOT NULL THEN 1 ELSE 0 END);

        -- Si hay menos de 2 indicadores, I_URB = NULL
        IF n_indicadores < 2 THEN
            NEW.iurb := NULL;
            RETURN NEW;
        END IF;

        -- Calcular suma ponderada y total de pesos
        suma_ponderada :=
            COALESCE(NEW.iacc * 0.25, 0) +
            COALESCE(NEW.iseg * 0.20, 0) +
            COALESCE(NEW.ihed * 0.25, 0) +
            COALESCE(NEW.ipnu * 0.30, 0);

        total_pesos :=
            (CASE WHEN NEW.iacc IS NOT NULL THEN 0.25 ELSE 0 END) +
            (CASE WHEN NEW.iseg IS NOT NULL THEN 0.20 ELSE 0 END) +
            (CASE WHEN NEW.ihed IS NOT NULL THEN 0.25 ELSE 0 END) +
            (CASE WHEN NEW.ipnu IS NOT NULL THEN 0.30 ELSE 0 END);

        -- Calcular I_URB normalizado
        IF total_pesos > 0 THEN
            NEW.iurb := ROUND((suma_ponderada / total_pesos)::numeric, 2);
            -- Clamp a rango 0-5
            NEW.iurb := LEAST(5.0, GREATEST(0.0, NEW.iurb));
        ELSE
            NEW.iurb := NULL;
        END IF;

        RETURN NEW;
    END;
END;
$$;


--
-- Name: FUNCTION trg_actualizar_iurb(); Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON FUNCTION iug.trg_actualizar_iurb() IS 'Actualiza automáticamente I_URB cuando cambian los indicadores base (I_ACC, I_SEG, I_HED, I_PNU)';


--
-- Name: trg_actualizar_precio_por_iurb(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.trg_actualizar_precio_por_iurb() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Calcular ratio si ambos valores existen
    IF NEW.iurb IS NOT NULL AND NEW.iurb > 0 AND NEW.precio IS NOT NULL AND NEW.precio > 0 THEN
        NEW.precio_por_iurb := ROUND((NEW.precio / NEW.iurb)::numeric, 2);
    ELSE
        NEW.precio_por_iurb := NULL;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: trg_calcular_dotacion(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.trg_calcular_dotacion() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_idot NUMERIC;
BEGIN
    IF NEW.geom IS NULL THEN
        RETURN NEW;
    END IF;
    
    v_idot := iug.calcular_idot_poi(NEW.geom);
    
    INSERT INTO iug.indicador_dotacion_raw (id_inmueble, idot_raw)
    VALUES (NEW.id_inmueble, v_idot)
    ON CONFLICT (id_inmueble) DO UPDATE SET
        idot_raw = EXCLUDED.idot_raw,
        fecha_calculo = now();
    
    RETURN NEW;
END;
$$;


--
-- Name: trigger_calcular_indicadores_raw(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.trigger_calcular_indicadores_raw() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: trigger_calcular_seguridad(); Type: FUNCTION; Schema: iug; Owner: -
--

CREATE FUNCTION iug.trigger_calcular_seguridad() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_cai NUMERIC;
    v_crimen NUMERIC;
    v_sector NUMERIC;
    v_localidad TEXT;
    v_masa NUMERIC;
    v_en_sector BOOLEAN;
    v_num_cais INTEGER;
BEGIN
    IF NEW.geom IS NOT NULL AND NEW.tipo_inmueble IS NOT NULL THEN

        -- Desempaquetado explícito (evita problemas con RECORD)
        SELECT
            score_cai, score_crimen, score_sector,
            localidad, masa_crimen_val, en_sector, num_cais
        INTO
            v_cai, v_crimen, v_sector,
            v_localidad, v_masa, v_en_sector, v_num_cais
        FROM iug.calcular_seguridad_raw(NEW.geom);

        INSERT INTO iug.indicador_seguridad_raw (
            id_inmueble, tipo_inmueble,
            score_cai_raw, score_crimen_raw, score_sector_raw,
            localidad_nombre, masa_crimen_localidad,
            en_sector_priorizado, cais_cercanos
        ) VALUES (
            NEW.id_inmueble, NEW.tipo_inmueble,
            v_cai, v_crimen, v_sector,
            v_localidad, v_masa, v_en_sector, v_num_cais
        )
        ON CONFLICT (id_inmueble) DO UPDATE SET
            score_cai_raw = EXCLUDED.score_cai_raw,
            score_crimen_raw = EXCLUDED.score_crimen_raw,
            score_sector_raw = EXCLUDED.score_sector_raw,
            localidad_nombre = EXCLUDED.localidad_nombre,
            masa_crimen_localidad = EXCLUDED.masa_crimen_localidad,
            en_sector_priorizado = EXCLUDED.en_sector_priorizado,
            cais_cercanos = EXCLUDED.cais_cercanos,
            fecha_calculo = now();
    END IF;

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ahp_pesos_crimen; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.ahp_pesos_crimen (
    id integer NOT NULL,
    tipo_delito character varying(50),
    peso_ahp numeric(5,4),
    descripcion text,
    version integer DEFAULT 1,
    fecha_actualizacion timestamp without time zone DEFAULT now()
);


--
-- Name: ahp_pesos_crimen_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.ahp_pesos_crimen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ahp_pesos_crimen_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.ahp_pesos_crimen_id_seq OWNED BY iug.ahp_pesos_crimen.id;


--
-- Name: inmueble; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.inmueble (
    id_inmueble bigint NOT NULL,
    id_origen text,
    pagina text,
    codigo_fuente text,
    image text,
    ubicacion text,
    ubicacion_asociada text,
    direccion text,
    inmobiliaria text,
    descripcion text,
    estado text,
    edad text,
    estrato smallint,
    proyecto boolean,
    fecha date,
    tipo_inmueble text,
    habitaciones smallint,
    banos smallint,
    area_construida numeric(10,2),
    area_privada numeric(10,2),
    precio numeric(14,2),
    geom public.geometry(Point,4326),
    id_barrio integer,
    id_localidad integer,
    ihed numeric(6,3),
    iacc numeric(6,3),
    iseg numeric(6,3),
    idot numeric(6,3),
    ipnu numeric(6,3),
    iug numeric(6,3),
    precio_std numeric(6,3),
    ratio numeric(8,4),
    primera_vista timestamp without time zone DEFAULT now(),
    ultima_vista timestamp without time zone DEFAULT now(),
    n_scrapeos integer DEFAULT 1,
    estado_oferta text DEFAULT 'activo'::text,
    area numeric(12,2),
    iurb numeric(5,2),
    precio_por_iurb numeric(15,2),
    tipo_operacion character varying(50) DEFAULT 'Venta'::character varying,
    fecha_publicacion timestamp without time zone DEFAULT now(),
    fuente character varying(100),
    garajes integer,
    ascensor boolean DEFAULT false,
    conjunto_cerrado boolean DEFAULT false,
    piscina boolean DEFAULT false,
    gym boolean DEFAULT false,
    parqueadero boolean DEFAULT false,
    terraza boolean DEFAULT false,
    balcon boolean DEFAULT false,
    deposito boolean DEFAULT false,
    nombre_contacto character varying(200),
    telefono_contacto character varying(50),
    CONSTRAINT chk_estado_oferta CHECK ((estado_oferta = ANY (ARRAY['activo'::text, 'vendido'::text, 'agotado'::text, 'inactivo'::text, 'pausado'::text]))),
    CONSTRAINT inmueble_estrato_check CHECK (((estrato >= 1) AND (estrato <= 6)))
);


--
-- Name: COLUMN inmueble.precio_por_iurb; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON COLUMN iug.inmueble.precio_por_iurb IS 'Ratio precio/I_URB. Valores bajos indican buenas oportunidades (alta calidad urbana, precio razonable)';


--
-- Name: analisis_oportunidades; Type: MATERIALIZED VIEW; Schema: iug; Owner: -
--

CREATE MATERIALIZED VIEW iug.analisis_oportunidades AS
 SELECT id_inmueble,
    ubicacion,
    tipo_inmueble,
    precio,
    area,
    habitaciones,
    banos,
    round((iurb)::numeric, 2) AS iurb,
    round((iacc)::numeric, 2) AS iacc,
    round((iseg)::numeric, 2) AS iseg,
    round((ihed)::numeric, 2) AS ihed,
    round((ipnu)::numeric, 2) AS ipnu,
    round((precio_por_iurb)::numeric, 2) AS precio_por_iurb,
    round((precio / NULLIF(area, (0)::numeric)), 0) AS precio_m2,
    round(((percent_rank() OVER (ORDER BY precio_por_iurb))::numeric * (100)::numeric), 1) AS percentil_ratio,
    round(((percent_rank() OVER (PARTITION BY tipo_inmueble ORDER BY precio_por_iurb))::numeric * (100)::numeric), 1) AS percentil_ratio_tipo,
        CASE
            WHEN ((iurb >= 4.0) AND (percent_rank() OVER (ORDER BY precio_por_iurb) <= (0.25)::double precision)) THEN 'Excelente Oportunidad'::text
            WHEN ((iurb >= 3.5) AND (percent_rank() OVER (ORDER BY precio_por_iurb) <= (0.33)::double precision)) THEN 'Muy Buena Oportunidad'::text
            WHEN ((iurb >= 3.0) AND (percent_rank() OVER (ORDER BY precio_por_iurb) <= (0.50)::double precision)) THEN 'Buena Oportunidad'::text
            WHEN (percent_rank() OVER (ORDER BY precio_por_iurb) <= (0.50)::double precision) THEN 'Oportunidad Razonable'::text
            WHEN (percent_rank() OVER (ORDER BY precio_por_iurb) >= (0.75)::double precision) THEN 'Sobrevalorado'::text
            ELSE 'Precio Justo'::text
        END AS categoria_oportunidad,
    fuente,
    fecha_publicacion,
    public.st_astext(geom) AS geom_wkt
   FROM iug.inmueble i
  WHERE ((precio_por_iurb IS NOT NULL) AND (precio IS NOT NULL) AND (iurb IS NOT NULL))
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW analisis_oportunidades; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON MATERIALIZED VIEW iug.analisis_oportunidades IS 'Vista materializada para análisis de oportunidades basado en ratio precio/I_URB';


--
-- Name: area_actividad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.area_actividad (
    id_area integer NOT NULL,
    codigo character varying(50),
    nombre character varying(300),
    tipo_actividad character varying(200),
    geom public.geometry(Geometry,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE area_actividad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.area_actividad IS 'Áreas de actividad según POT 555';


--
-- Name: area_actividad_id_area_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.area_actividad_id_area_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: area_actividad_id_area_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.area_actividad_id_area_seq OWNED BY iug.area_actividad.id_area;


--
-- Name: barrio; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.barrio (
    id_barrio integer NOT NULL,
    nombre text NOT NULL,
    id_localidad integer NOT NULL,
    descripcion text,
    area_total numeric(12,2),
    poblacion_estimada numeric(12,2),
    codigo_upz integer,
    estado integer,
    geom public.geometry(MultiPolygon,4326) NOT NULL
);


--
-- Name: TABLE barrio; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.barrio IS 'Barrios legalizados de Bogotá';


--
-- Name: barrio_id_barrio_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.barrio_id_barrio_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: barrio_id_barrio_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.barrio_id_barrio_seq OWNED BY iug.barrio.id_barrio;


--
-- Name: cai_policia; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.cai_policia (
    id_cai integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    cuadrante character varying(100),
    direccion text,
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE cai_policia; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.cai_policia IS 'Comandos de Atenci??n Inmediata - protecci??n policial';


--
-- Name: cai_policia_id_cai_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.cai_policia_id_cai_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cai_policia_id_cai_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.cai_policia_id_cai_seq OWNED BY iug.cai_policia.id_cai;


--
-- Name: cat_caracteristica; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.cat_caracteristica (
    id_caracteristica integer NOT NULL,
    nombre text NOT NULL,
    tipo text NOT NULL,
    CONSTRAINT cat_caracteristica_tipo_check CHECK ((tipo = ANY (ARRAY['bool'::text, 'num'::text, 'text'::text, 'date'::text])))
);


--
-- Name: cat_caracteristica_id_caracteristica_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.cat_caracteristica_id_caracteristica_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cat_caracteristica_id_caracteristica_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.cat_caracteristica_id_caracteristica_seq OWNED BY iug.cat_caracteristica.id_caracteristica;


--
-- Name: cat_estado_inmueble; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.cat_estado_inmueble (
    estado text NOT NULL
);


--
-- Name: cat_tipo_inmueble; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.cat_tipo_inmueble (
    tipo_inmueble text NOT NULL
);


--
-- Name: centro_comercial; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.centro_comercial (
    id_cc integer NOT NULL,
    nombre character varying(200) NOT NULL,
    direccion character varying(200),
    localidad character varying(100),
    lat double precision,
    lon double precision,
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: centro_comercial_id_cc_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.centro_comercial_id_cc_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: centro_comercial_id_cc_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.centro_comercial_id_cc_seq OWNED BY iug.centro_comercial.id_cc;


--
-- Name: centro_salud; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.centro_salud (
    id_centro integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200) NOT NULL,
    tipo character varying(100),
    localidad character varying(100),
    direccion character varying(200),
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: centro_salud_id_centro_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.centro_salud_id_centro_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: centro_salud_id_centro_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.centro_salud_id_centro_seq OWNED BY iug.centro_salud.id_centro;


--
-- Name: colegio; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.colegio (
    id_colegio integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200) NOT NULL,
    tipo character varying(50),
    localidad character varying(100),
    direccion character varying(200),
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE colegio; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.colegio IS 'Instituciones educativas de Bogotá';


--
-- Name: colegio_id_colegio_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.colegio_id_colegio_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: colegio_id_colegio_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.colegio_id_colegio_seq OWNED BY iug.colegio.id_colegio;


--
-- Name: criminalidad_localidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.criminalidad_localidad (
    id_crim integer NOT NULL,
    codigo_localidad character varying(10),
    nombre_localidad character varying(200),
    homicidios_2024 integer DEFAULT 0,
    delitos_sexuales_2024 integer DEFAULT 0,
    hurto_personas_2024 integer DEFAULT 0,
    otros_delitos_2024 integer DEFAULT 0,
    masa_crimen numeric(12,4),
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE criminalidad_localidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.criminalidad_localidad IS 'Estad??sticas de criminalidad por localidad con masa ponderada por AHP';


--
-- Name: criminalidad_localidad_id_crim_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.criminalidad_localidad_id_crim_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: criminalidad_localidad_id_crim_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.criminalidad_localidad_id_crim_seq OWNED BY iug.criminalidad_localidad.id_crim;


--
-- Name: cuadrante_policia; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.cuadrante_policia (
    id_cuadrante integer NOT NULL,
    codigo character varying(20),
    nombre character varying(100),
    localidad character varying(100),
    geom public.geometry(MultiPolygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: cuadrante_policia_id_cuadrante_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.cuadrante_policia_id_cuadrante_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cuadrante_policia_id_cuadrante_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.cuadrante_policia_id_cuadrante_seq OWNED BY iug.cuadrante_policia.id_cuadrante;


--
-- Name: dotacion_abastecimiento; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotacion_abastecimiento (
    id integer NOT NULL,
    nombre character varying(255),
    tipo character varying(50) DEFAULT 'supermercado'::character varying,
    marca character varying(100),
    geom public.geometry(Point,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotacion_abastecimiento_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotacion_abastecimiento_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotacion_abastecimiento_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotacion_abastecimiento_id_seq OWNED BY iug.dotacion_abastecimiento.id;


--
-- Name: dotacion_cultura; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotacion_cultura (
    id integer NOT NULL,
    nombre character varying(255),
    tipo character varying(50) DEFAULT 'biblioteca'::character varying,
    geom public.geometry(Point,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotacion_cultura_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotacion_cultura_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotacion_cultura_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotacion_cultura_id_seq OWNED BY iug.dotacion_cultura.id;


--
-- Name: dotacion_educacion; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotacion_educacion (
    id integer NOT NULL,
    nombre character varying(255),
    tipo character varying(50) DEFAULT 'colegio'::character varying,
    sector character varying(50),
    geom public.geometry(Point,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotacion_educacion_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotacion_educacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotacion_educacion_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotacion_educacion_id_seq OWNED BY iug.dotacion_educacion.id;


--
-- Name: dotacion_recreacion; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotacion_recreacion (
    id integer NOT NULL,
    nombre character varying(255),
    tipo character varying(50) DEFAULT 'parque'::character varying,
    area_m2 numeric,
    geom public.geometry(Geometry,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotacion_recreacion_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotacion_recreacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotacion_recreacion_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotacion_recreacion_id_seq OWNED BY iug.dotacion_recreacion.id;


--
-- Name: dotacion_salud; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotacion_salud (
    id integer NOT NULL,
    nombre character varying(255),
    tipo character varying(50) DEFAULT 'ips'::character varying,
    direccion character varying(255),
    localidad character varying(100),
    geom public.geometry(Point,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotacion_salud_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotacion_salud_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotacion_salud_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotacion_salud_id_seq OWNED BY iug.dotacion_salud.id;


--
-- Name: dotaciones_poi; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.dotaciones_poi (
    id integer NOT NULL,
    nombre character varying(255),
    categoria character varying(50) NOT NULL,
    subcategoria character varying(50),
    fuente character varying(50),
    geom public.geometry(Point,4326),
    fecha_carga timestamp without time zone DEFAULT now()
);


--
-- Name: dotaciones_poi_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.dotaciones_poi_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dotaciones_poi_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.dotaciones_poi_id_seq OWNED BY iug.dotaciones_poi.id;


--
-- Name: edificabilidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.edificabilidad (
    id_edificabilidad integer NOT NULL,
    codigo character varying(50),
    rango_min double precision,
    rango_max double precision,
    descripcion character varying(500),
    geom public.geometry(Geometry,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE edificabilidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.edificabilidad IS 'Rangos de edificabilidad según POT 555';


--
-- Name: edificabilidad_id_edificabilidad_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.edificabilidad_id_edificabilidad_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edificabilidad_id_edificabilidad_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.edificabilidad_id_edificabilidad_seq OWNED BY iug.edificabilidad.id_edificabilidad;


--
-- Name: estacion_metro; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.estacion_metro (
    id_estacion integer NOT NULL,
    codigo character varying(20),
    nombre character varying(200) NOT NULL,
    linea character varying(50),
    tipo character varying(50) DEFAULT 'estandar'::character varying,
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE estacion_metro; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.estacion_metro IS 'Estaciones del Metro de Bogotá (Primera Línea). Cargar datos cuando estén disponibles.';


--
-- Name: estacion_metro_id_estacion_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.estacion_metro_id_estacion_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: estacion_metro_id_estacion_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.estacion_metro_id_estacion_seq OWNED BY iug.estacion_metro.id_estacion;


--
-- Name: estacion_transmilenio; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.estacion_transmilenio (
    id_estacion integer NOT NULL,
    codigo character varying(20),
    nombre character varying(100) NOT NULL,
    troncal character varying(100),
    tipo character varying(50),
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE estacion_transmilenio; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.estacion_transmilenio IS 'Estaciones y portales de TransMilenio';


--
-- Name: estacion_transmilenio_id_estacion_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.estacion_transmilenio_id_estacion_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: estacion_transmilenio_id_estacion_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.estacion_transmilenio_id_estacion_seq OWNED BY iug.estacion_transmilenio.id_estacion;


--
-- Name: flyway_schema_history; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.flyway_schema_history (
    installed_rank integer NOT NULL,
    version character varying(50),
    description character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    script character varying(1000) NOT NULL,
    checksum integer,
    installed_by character varying(100) NOT NULL,
    installed_on timestamp without time zone DEFAULT now() NOT NULL,
    execution_time integer NOT NULL,
    success boolean NOT NULL
);


--
-- Name: hedonic_model_coefs; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.hedonic_model_coefs (
    tipo_inmueble text NOT NULL,
    intercept numeric,
    coef_area numeric,
    coef_habitaciones numeric,
    coef_banos numeric,
    coef_parqueaderos numeric,
    coef_estrato numeric,
    r2_score numeric,
    rmse numeric,
    mae numeric,
    n_samples integer,
    min_score numeric,
    max_score numeric,
    mean_score numeric,
    std_score numeric,
    fecha_entrenamiento timestamp without time zone DEFAULT now(),
    version integer DEFAULT 1
);


--
-- Name: indicador_amenidades_raw; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_amenidades_raw (
    id_indicador integer NOT NULL,
    id_inmueble bigint NOT NULL,
    tipo_inmueble character varying(50),
    score_parques_raw numeric(10,4),
    score_salud_raw numeric(10,4),
    score_educacion_basica_raw numeric(10,4),
    score_educacion_superior_raw numeric(10,4),
    fecha_calculo timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE indicador_amenidades_raw; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.indicador_amenidades_raw IS 'Scores gravity-based para amenidades: Parques (800m), Salud (1500m), Educaci??n B??sica (1000m), Educaci??n Superior (2000m)';


--
-- Name: pca_pesos_amenidades; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pca_pesos_amenidades (
    tipo_inmueble character varying(50) NOT NULL,
    peso_parques numeric(10,6) DEFAULT 0.25,
    peso_salud numeric(10,6) DEFAULT 0.25,
    peso_educacion_basica numeric(10,6) DEFAULT 0.25,
    peso_educacion_superior numeric(10,6) DEFAULT 0.25,
    pc1_min numeric(10,6) DEFAULT 0,
    pc1_max numeric(10,6) DEFAULT 1,
    pca_version integer DEFAULT 1,
    total_muestras integer DEFAULT 0,
    varianza_explicada numeric(5,4),
    fecha_actualizacion timestamp without time zone DEFAULT now()
);


--
-- Name: indicador_amenidades_final; Type: MATERIALIZED VIEW; Schema: iug; Owner: -
--

CREATE MATERIALIZED VIEW iug.indicador_amenidades_final AS
 SELECT r.id_inmueble,
    r.tipo_inmueble,
    ((((r.score_parques_raw * p.peso_parques) + (r.score_salud_raw * p.peso_salud)) + (r.score_educacion_basica_raw * p.peso_educacion_basica)) + (r.score_educacion_superior_raw * p.peso_educacion_superior)) AS pc1_value,
        CASE
            WHEN ((p.pc1_max - p.pc1_min) > (0)::numeric) THEN (((5)::numeric * (((((r.score_parques_raw * p.peso_parques) + (r.score_salud_raw * p.peso_salud)) + (r.score_educacion_basica_raw * p.peso_educacion_basica)) + (r.score_educacion_superior_raw * p.peso_educacion_superior)) - p.pc1_min)) / (p.pc1_max - p.pc1_min))
            ELSE 2.5
        END AS score_amenidades_final,
    p.pca_version,
    r.fecha_calculo AS fecha_calculo_gravity,
    p.fecha_actualizacion AS fecha_calculo_pca
   FROM (iug.indicador_amenidades_raw r
     JOIN iug.pca_pesos_amenidades p ON (((r.tipo_inmueble)::text = (p.tipo_inmueble)::text)))
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW indicador_amenidades_final; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON MATERIALIZED VIEW iug.indicador_amenidades_final IS 'Score final de amenidades (0-5) normalizado con PCA';


--
-- Name: indicador_amenidades_raw_id_indicador_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.indicador_amenidades_raw_id_indicador_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicador_amenidades_raw_id_indicador_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.indicador_amenidades_raw_id_indicador_seq OWNED BY iug.indicador_amenidades_raw.id_indicador;


--
-- Name: indicador_barrio; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_barrio (
    id_barrio integer NOT NULL,
    iacc numeric(6,3),
    iseg numeric(6,3),
    idot numeric(6,3),
    ipnu numeric(6,3),
    iug numeric(6,3),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: indicador_dotacion_raw; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_dotacion_raw (
    id integer NOT NULL,
    id_inmueble integer,
    score_salud numeric(10,4),
    score_educacion numeric(10,4),
    score_abastecimiento numeric(10,4),
    score_cultura numeric(10,4),
    score_recreacion numeric(10,4),
    n_salud integer DEFAULT 0,
    n_educacion integer DEFAULT 0,
    n_abastecimiento integer DEFAULT 0,
    n_cultura integer DEFAULT 0,
    n_recreacion integer DEFAULT 0,
    idot_raw numeric(10,4),
    fecha_calculo timestamp without time zone DEFAULT now()
);


--
-- Name: indicador_dotacion_final; Type: MATERIALIZED VIEW; Schema: iug; Owner: -
--

CREATE MATERIALIZED VIEW iug.indicador_dotacion_final AS
 SELECT r.id_inmueble,
    i.tipo_inmueble,
    r.idot_raw,
    round((((5.0)::double precision * percent_rank() OVER (PARTITION BY i.tipo_inmueble ORDER BY r.idot_raw)))::numeric, 4) AS idot_normalizado,
    r.n_salud,
    r.n_educacion,
    r.n_abastecimiento,
    r.n_cultura,
    r.n_recreacion,
    r.fecha_calculo
   FROM (iug.indicador_dotacion_raw r
     JOIN iug.inmueble i ON ((r.id_inmueble = i.id_inmueble)))
  WHERE (r.idot_raw IS NOT NULL)
  WITH NO DATA;


--
-- Name: indicador_dotacion_raw_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.indicador_dotacion_raw_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicador_dotacion_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.indicador_dotacion_raw_id_seq OWNED BY iug.indicador_dotacion_raw.id;


--
-- Name: indicador_localidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_localidad (
    id_localidad integer NOT NULL,
    iacc numeric(6,3),
    iseg numeric(6,3),
    idot numeric(6,3),
    ipnu numeric(6,3),
    iug numeric(6,3),
    n_barrios integer,
    n_inmuebles integer,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE indicador_localidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.indicador_localidad IS 'Indicadores agregados por localidad (calculados en Python)';


--
-- Name: indicador_seguridad_raw; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_seguridad_raw (
    id_indicador integer NOT NULL,
    id_inmueble bigint NOT NULL,
    tipo_inmueble character varying(50),
    score_cai_raw numeric(10,4),
    score_crimen_raw numeric(12,4),
    score_sector_raw numeric(5,4),
    localidad_nombre character varying(200),
    masa_crimen_localidad numeric(12,4),
    en_sector_priorizado boolean DEFAULT false,
    cais_cercanos integer DEFAULT 0,
    fecha_calculo timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE indicador_seguridad_raw; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.indicador_seguridad_raw IS 'Scores crudos de seguridad antes de normalizaci??n 0-5';


--
-- Name: normalizacion_seguridad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.normalizacion_seguridad (
    tipo_inmueble character varying(50) NOT NULL,
    cai_min numeric(10,4) DEFAULT 0,
    cai_max numeric(10,4) DEFAULT 2.0,
    crimen_min numeric(12,4),
    crimen_max numeric(12,4),
    sector_min numeric(5,4) DEFAULT 0,
    sector_max numeric(5,4) DEFAULT 1.0,
    peso_cai numeric(5,4) DEFAULT 0.35,
    peso_crimen numeric(5,4) DEFAULT 0.45,
    peso_sector numeric(5,4) DEFAULT 0.20,
    total_muestras integer DEFAULT 0,
    fecha_actualizacion timestamp without time zone DEFAULT now(),
    version integer DEFAULT 1
);


--
-- Name: TABLE normalizacion_seguridad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.normalizacion_seguridad IS 'Par??metros min/max y pesos para normalizar scores de seguridad 0-5';


--
-- Name: indicador_seguridad_final; Type: MATERIALIZED VIEW; Schema: iug; Owner: -
--

CREATE MATERIALIZED VIEW iug.indicador_seguridad_final AS
 SELECT r.id_inmueble,
    r.tipo_inmueble,
    (((5)::numeric * LEAST(r.score_cai_raw, n.cai_max)) / NULLIF(n.cai_max, (0)::numeric)) AS cai_norm,
    ((5)::numeric *
        CASE
            WHEN (NULLIF((n.crimen_max - n.crimen_min), (0)::numeric) > (0)::numeric) THEN ((r.score_crimen_raw - n.crimen_min) / (n.crimen_max - n.crimen_min))
            ELSE 0.5
        END) AS crimen_norm,
    ((5)::numeric * r.score_sector_raw) AS sector_norm,
    LEAST((5)::numeric, GREATEST((0)::numeric, (((((n.peso_cai * (5)::numeric) * LEAST(r.score_cai_raw, n.cai_max)) / NULLIF(n.cai_max, (0)::numeric)) + (n.peso_crimen * ((5)::numeric - ((5)::numeric *
        CASE
            WHEN (NULLIF((n.crimen_max - n.crimen_min), (0)::numeric) > (0)::numeric) THEN ((r.score_crimen_raw - n.crimen_min) / (n.crimen_max - n.crimen_min))
            ELSE 0.5
        END)))) + (n.peso_sector * ((5)::numeric - ((5)::numeric * r.score_sector_raw)))))) AS score_seguridad_final,
    r.localidad_nombre,
    r.masa_crimen_localidad,
    r.en_sector_priorizado,
    r.cais_cercanos,
    n.version AS normalizacion_version,
    r.fecha_calculo
   FROM (iug.indicador_seguridad_raw r
     JOIN iug.normalizacion_seguridad n ON (((r.tipo_inmueble)::text = (n.tipo_inmueble)::text)))
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW indicador_seguridad_final; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON MATERIALIZED VIEW iug.indicador_seguridad_final IS 'Score final de seguridad 0-5: CAI suma, crimen y sectores priorizados restan';


--
-- Name: indicador_seguridad_raw_id_indicador_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.indicador_seguridad_raw_id_indicador_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicador_seguridad_raw_id_indicador_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.indicador_seguridad_raw_id_indicador_seq OWNED BY iug.indicador_seguridad_raw.id_indicador;


--
-- Name: indicador_transporte_raw; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.indicador_transporte_raw (
    id_inmueble integer NOT NULL,
    tipo_inmueble character varying(50) NOT NULL,
    score_transmilenio_raw numeric(10,4),
    score_sitp_raw numeric(10,4),
    score_vias_raw numeric(10,4),
    score_parques_raw numeric(10,4),
    fecha_calculo timestamp without time zone DEFAULT now(),
    score_metro_raw numeric DEFAULT 0
);


--
-- Name: TABLE indicador_transporte_raw; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.indicador_transporte_raw IS 'Scores gravity-based para 4 capas de TRANSPORTE: TransMilenio (1000m), SITP (500m), Vias (500m), Metro (1500m)';


--
-- Name: pca_pesos_tipo; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pca_pesos_tipo (
    tipo_inmueble character varying(50) NOT NULL,
    peso_transmilenio numeric(10,6) DEFAULT 0.25,
    peso_sitp numeric(10,6) DEFAULT 0.25,
    peso_vias numeric(10,6) DEFAULT 0.25,
    peso_parques numeric(10,6) DEFAULT 0.25,
    pc1_min numeric(10,6) DEFAULT 0,
    pc1_max numeric(10,6) DEFAULT 1,
    pca_version integer DEFAULT 1,
    total_muestras integer DEFAULT 0,
    varianza_explicada numeric(5,4),
    fecha_actualizacion timestamp without time zone DEFAULT now(),
    peso_metro numeric DEFAULT 0
);


--
-- Name: TABLE pca_pesos_tipo; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pca_pesos_tipo IS 'Pesos de PCA calculados por batch (ej. despu??s de scraping). Se actualizan espor??dicamente usando Python + scikit-learn.';


--
-- Name: indicador_transporte_final; Type: MATERIALIZED VIEW; Schema: iug; Owner: -
--

CREATE MATERIALIZED VIEW iug.indicador_transporte_final AS
 SELECT r.id_inmueble,
    r.tipo_inmueble,
    ((((r.score_transmilenio_raw * p.peso_transmilenio) + (r.score_sitp_raw * p.peso_sitp)) + (r.score_vias_raw * p.peso_vias)) + (r.score_metro_raw * p.peso_metro)) AS pc1_value,
        CASE
            WHEN ((p.pc1_max - p.pc1_min) > (0)::numeric) THEN LEAST((5)::numeric, GREATEST((0)::numeric, (((5)::numeric * (((((r.score_transmilenio_raw * p.peso_transmilenio) + (r.score_sitp_raw * p.peso_sitp)) + (r.score_vias_raw * p.peso_vias)) + (r.score_metro_raw * p.peso_metro)) - p.pc1_min)) / (p.pc1_max - p.pc1_min))))
            ELSE 2.5
        END AS score_transporte_final,
    p.pca_version,
    r.fecha_calculo AS fecha_calculo_gravity,
    p.fecha_actualizacion AS fecha_calculo_pca
   FROM (iug.indicador_transporte_raw r
     JOIN iug.pca_pesos_tipo p ON (((r.tipo_inmueble)::text = (p.tipo_inmueble)::text)))
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW indicador_transporte_final; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON MATERIALIZED VIEW iug.indicador_transporte_final IS 'Score final de transporte (0-5) = raw_scores x pesos_pca. Metro con peso_metro=0 hasta que se carguen estaciones.';


--
-- Name: inmueble_caracteristica; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.inmueble_caracteristica (
    id_inmueble bigint NOT NULL,
    nombre text NOT NULL,
    valor_bool boolean,
    valor_num numeric(14,4),
    valor_text text,
    valor_date date,
    fuente text,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: inmueble_historial; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.inmueble_historial (
    id_historial bigint NOT NULL,
    id_inmueble bigint NOT NULL,
    campo_modificado text NOT NULL,
    valor_anterior text,
    valor_nuevo text,
    fecha_cambio timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE inmueble_historial; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.inmueble_historial IS 'Registro de cambios en inmuebles (precio, estado, etc.)';


--
-- Name: inmueble_historial_id_historial_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.inmueble_historial_id_historial_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inmueble_historial_id_historial_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.inmueble_historial_id_historial_seq OWNED BY iug.inmueble_historial.id_historial;


--
-- Name: inmueble_id_inmueble_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.inmueble_id_inmueble_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inmueble_id_inmueble_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.inmueble_id_inmueble_seq OWNED BY iug.inmueble.id_inmueble;


--
-- Name: inmueble_scrapeo; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.inmueble_scrapeo (
    id_scrapeo bigint NOT NULL,
    id_inmueble bigint,
    pagina text,
    precio_momento numeric(14,2),
    raw_data jsonb,
    fecha_scrapeo timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE inmueble_scrapeo; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.inmueble_scrapeo IS 'Registro de cada scrapeo individual por inmueble';


--
-- Name: inmueble_scrapeo_id_scrapeo_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.inmueble_scrapeo_id_scrapeo_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inmueble_scrapeo_id_scrapeo_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.inmueble_scrapeo_id_scrapeo_seq OWNED BY iug.inmueble_scrapeo.id_scrapeo;


--
-- Name: localidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.localidad (
    id_localidad integer NOT NULL,
    nombre text NOT NULL,
    geom public.geometry(MultiPolygon,4326) NOT NULL
);


--
-- Name: TABLE localidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.localidad IS 'Polígonos de localidades de Bogotá';


--
-- Name: localidad_id_localidad_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.localidad_id_localidad_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: localidad_id_localidad_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.localidad_id_localidad_seq OWNED BY iug.localidad.id_localidad;


--
-- Name: malla_vial; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.malla_vial (
    id_via bigint NOT NULL,
    tipo_via text,
    nombre text,
    props jsonb DEFAULT '{}'::jsonb,
    geom public.geometry(LineString,4326) NOT NULL
);


--
-- Name: TABLE malla_vial; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.malla_vial IS 'Red vial para análisis de conectividad (futuro)';


--
-- Name: malla_vial_id_via_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.malla_vial_id_via_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: malla_vial_id_via_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.malla_vial_id_via_seq OWNED BY iug.malla_vial.id_via;


--
-- Name: modelo_hedonico; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.modelo_hedonico (
    id_modelo integer NOT NULL,
    nombre text DEFAULT 'default'::text NOT NULL,
    tipo_inmueble text,
    coeficientes jsonb DEFAULT '{}'::jsonb NOT NULL,
    r_squared numeric,
    rmse numeric,
    n_observaciones integer,
    created_at timestamp without time zone DEFAULT now(),
    activo boolean DEFAULT true
);


--
-- Name: TABLE modelo_hedonico; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.modelo_hedonico IS 'Coeficientes de regresión hedónica (calculados en Python)';


--
-- Name: modelo_hedonico_id_modelo_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.modelo_hedonico_id_modelo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: modelo_hedonico_id_modelo_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.modelo_hedonico_id_modelo_seq OWNED BY iug.modelo_hedonico.id_modelo;


--
-- Name: osm_main_roads; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.osm_main_roads (
    id integer NOT NULL,
    name text,
    highway text,
    geom public.geometry(LineString,4326)
);


--
-- Name: osm_main_roads_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.osm_main_roads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: osm_main_roads_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.osm_main_roads_id_seq OWNED BY iug.osm_main_roads.id;


--
-- Name: osm_parks; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.osm_parks (
    id integer NOT NULL,
    name text,
    geom public.geometry(Polygon,4326)
);


--
-- Name: osm_parks_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.osm_parks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: osm_parks_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.osm_parks_id_seq OWNED BY iug.osm_parks.id;


--
-- Name: osm_transport; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.osm_transport (
    id integer NOT NULL,
    type text,
    name text,
    geom public.geometry(Point,4326)
);


--
-- Name: osm_transport_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.osm_transport_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: osm_transport_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.osm_transport_id_seq OWNED BY iug.osm_transport.id;


--
-- Name: pesos_dotacion; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pesos_dotacion (
    id integer NOT NULL,
    categoria character varying(50) NOT NULL,
    peso numeric(4,3) DEFAULT 0.200,
    radio_metros integer DEFAULT 1000,
    descripcion text,
    activo boolean DEFAULT true
);


--
-- Name: TABLE pesos_dotacion; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pesos_dotacion IS 'Pesos para suma ponderada de dotaciones. Suma debe = 1.0';


--
-- Name: pesos_dotacion_ahp; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pesos_dotacion_ahp (
    id integer NOT NULL,
    categoria_1 character varying(50),
    categoria_2 character varying(50),
    comparacion numeric(4,2),
    fecha_calculo timestamp without time zone
);


--
-- Name: TABLE pesos_dotacion_ahp; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pesos_dotacion_ahp IS 'Tabla vac??a para futura calibraci??n AHP de pesos de dotaci??n';


--
-- Name: pesos_dotacion_ahp_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pesos_dotacion_ahp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pesos_dotacion_ahp_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pesos_dotacion_ahp_id_seq OWNED BY iug.pesos_dotacion_ahp.id;


--
-- Name: pesos_dotacion_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pesos_dotacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pesos_dotacion_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pesos_dotacion_id_seq OWNED BY iug.pesos_dotacion.id;


--
-- Name: pesos_iug; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pesos_iug (
    id_config integer NOT NULL,
    nombre text DEFAULT 'default'::text NOT NULL,
    w_hed numeric DEFAULT 1.0 NOT NULL,
    w_acc numeric DEFAULT 1.0 NOT NULL,
    w_seg numeric DEFAULT 1.0 NOT NULL,
    w_dot numeric DEFAULT 1.0 NOT NULL,
    w_pnu numeric DEFAULT 1.0 NOT NULL,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: pesos_iug_id_config_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pesos_iug_id_config_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pesos_iug_id_config_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pesos_iug_id_config_seq OWNED BY iug.pesos_iug.id_config;


--
-- Name: poi; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.poi (
    id_poi bigint NOT NULL,
    categoria text NOT NULL,
    subcategoria text,
    nombre text,
    direccion text,
    props jsonb DEFAULT '{}'::jsonb,
    geom public.geometry(Point,4326) NOT NULL
);


--
-- Name: TABLE poi; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.poi IS 'Puntos de Interés para análisis espacial';


--
-- Name: poi_id_poi_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.poi_id_poi_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: poi_id_poi_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.poi_id_poi_seq OWNED BY iug.poi.id_poi;


--
-- Name: pot_area_actividad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pot_area_actividad (
    id_area integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    descripcion text,
    normativa text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE pot_area_actividad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pot_area_actividad IS '??reas de actividad del POT - Define usos permitidos por zona';


--
-- Name: pot_area_actividad_id_area_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pot_area_actividad_id_area_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pot_area_actividad_id_area_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pot_area_actividad_id_area_seq OWNED BY iug.pot_area_actividad.id_area;


--
-- Name: pot_edificabilidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pot_edificabilidad (
    id_edificabilidad integer NOT NULL,
    codigo character varying(50),
    rango character varying(100),
    pisos_min integer,
    pisos_max integer,
    altura_max_m numeric(6,2),
    descripcion text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE pot_edificabilidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pot_edificabilidad IS 'Edificabilidad - Altura y pisos m??ximos permitidos';


--
-- Name: pot_edificabilidad_id_edificabilidad_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pot_edificabilidad_id_edificabilidad_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pot_edificabilidad_id_edificabilidad_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pot_edificabilidad_id_edificabilidad_seq OWNED BY iug.pot_edificabilidad.id_edificabilidad;


--
-- Name: pot_tratamiento; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pot_tratamiento (
    id_tratamiento integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    tipo character varying(100),
    descripcion text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE pot_tratamiento; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pot_tratamiento IS 'Tratamiento urban??stico - Define intervenciones permitidas';


--
-- Name: pot_tratamiento_id_tratamiento_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pot_tratamiento_id_tratamiento_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pot_tratamiento_id_tratamiento_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pot_tratamiento_id_tratamiento_seq OWNED BY iug.pot_tratamiento.id_tratamiento;


--
-- Name: pot_upl; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.pot_upl (
    id_upl integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    localidad character varying(100),
    estado character varying(50),
    descripcion text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE pot_upl; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.pot_upl IS 'Unidades de Planeamiento Local - Normativa espec??fica por UPL';


--
-- Name: pot_upl_id_upl_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.pot_upl_id_upl_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pot_upl_id_upl_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.pot_upl_id_upl_seq OWNED BY iug.pot_upl.id_upl;


--
-- Name: ruta_sitp; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.ruta_sitp (
    id_ruta integer NOT NULL,
    codigo character varying(20),
    nombre character varying(200),
    tipo character varying(50),
    geom public.geometry(MultiLineString,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: ruta_sitp_id_ruta_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.ruta_sitp_id_ruta_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ruta_sitp_id_ruta_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.ruta_sitp_id_ruta_seq OWNED BY iug.ruta_sitp.id_ruta;


--
-- Name: sector; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.sector (
    id_sector integer NOT NULL,
    codigo character varying(20),
    nombre character varying(100),
    localidad character varying(100),
    geom public.geometry(MultiPolygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: sector_catastral; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.sector_catastral (
    id_sector integer NOT NULL,
    codigo character varying(50),
    nombre character varying(300),
    localidad character varying(100),
    geom public.geometry(Geometry,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE sector_catastral; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.sector_catastral IS 'Sectores catastrales de Bogotá';


--
-- Name: sector_catastral_id_sector_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.sector_catastral_id_sector_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_catastral_id_sector_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.sector_catastral_id_sector_seq OWNED BY iug.sector_catastral.id_sector;


--
-- Name: sector_id_sector_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.sector_id_sector_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_id_sector_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.sector_id_sector_seq OWNED BY iug.sector.id_sector;


--
-- Name: sector_priorizado; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.sector_priorizado (
    id_sector integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    descripcion text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE sector_priorizado; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.sector_priorizado IS 'Sectores priorizados para recuperaci??n del espacio p??blico (H??bitat)';


--
-- Name: sector_priorizado_id_sector_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.sector_priorizado_id_sector_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_priorizado_id_sector_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.sector_priorizado_id_sector_seq OWNED BY iug.sector_priorizado.id_sector;


--
-- Name: sector_seguridad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.sector_seguridad (
    id_sector integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200),
    tipo character varying(100),
    descripcion text,
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE sector_seguridad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.sector_seguridad IS 'Sectores priorizados de seguridad - zonas de recuperaci??n del espacio p??blico';


--
-- Name: sector_seguridad_id_sector_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.sector_seguridad_id_sector_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_seguridad_id_sector_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.sector_seguridad_id_sector_seq OWNED BY iug.sector_seguridad.id_sector;


--
-- Name: sitp_paradero; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.sitp_paradero (
    id bigint NOT NULL,
    objectid integer,
    globalid text,
    nombre text,
    codigo text,
    props jsonb DEFAULT '{}'::jsonb NOT NULL,
    geom public.geometry(Point,4326) NOT NULL
);


--
-- Name: sitp_paradero_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.sitp_paradero_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sitp_paradero_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.sitp_paradero_id_seq OWNED BY iug.sitp_paradero.id;


--
-- Name: tm_estacion; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.tm_estacion (
    id bigint NOT NULL,
    objectid integer,
    globalid text,
    nombre text,
    codigo text,
    cod_nodo integer,
    troncal text,
    props jsonb DEFAULT '{}'::jsonb NOT NULL,
    geom public.geometry(Point,4326) NOT NULL
);


--
-- Name: tm_estacion_id_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.tm_estacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tm_estacion_id_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.tm_estacion_id_seq OWNED BY iug.tm_estacion.id;


--
-- Name: tratamiento_urbanistico; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.tratamiento_urbanistico (
    id_tratamiento integer NOT NULL,
    codigo character varying(50),
    nombre character varying(300),
    tipo character varying(200),
    geom public.geometry(Geometry,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: TABLE tratamiento_urbanistico; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TABLE iug.tratamiento_urbanistico IS 'Tratamientos urbanísticos según POT 555';


--
-- Name: tratamiento_urbanistico_id_tratamiento_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.tratamiento_urbanistico_id_tratamiento_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tratamiento_urbanistico_id_tratamiento_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.tratamiento_urbanistico_id_tratamiento_seq OWNED BY iug.tratamiento_urbanistico.id_tratamiento;


--
-- Name: universidad; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.universidad (
    id_universidad integer NOT NULL,
    codigo character varying(50),
    nombre character varying(200) NOT NULL,
    tipo character varying(100),
    localidad character varying(100),
    direccion character varying(200),
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: universidad_id_universidad_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.universidad_id_universidad_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: universidad_id_universidad_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.universidad_id_universidad_seq OWNED BY iug.universidad.id_universidad;


--
-- Name: upl; Type: TABLE; Schema: iug; Owner: -
--

CREATE TABLE iug.upl (
    id_upl integer NOT NULL,
    codigo character varying(20),
    nombre character varying(100),
    localidad character varying(100),
    geom public.geometry(MultiPolygon,4326),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: upl_id_upl_seq; Type: SEQUENCE; Schema: iug; Owner: -
--

CREATE SEQUENCE iug.upl_id_upl_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: upl_id_upl_seq; Type: SEQUENCE OWNED BY; Schema: iug; Owner: -
--

ALTER SEQUENCE iug.upl_id_upl_seq OWNED BY iug.upl.id_upl;


--
-- Name: v_caracteristicas_por_localidad; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_caracteristicas_por_localidad AS
 SELECT l.nombre AS nombre_localidad,
    ic.nombre AS caracteristica,
    count(*) AS inmuebles_con_caracteristica,
    total_loc.total AS total_inmuebles_localidad,
    round(((100.0 * (count(*))::numeric) / (NULLIF(total_loc.total, 0))::numeric), 1) AS pct_con_caracteristica
   FROM (((iug.localidad l
     JOIN iug.inmueble i ON (public.st_contains(l.geom, i.geom)))
     JOIN iug.inmueble_caracteristica ic ON (((i.id_inmueble = ic.id_inmueble) AND (ic.valor_bool = true))))
     JOIN LATERAL ( SELECT count(DISTINCT i2.id_inmueble) AS total
           FROM iug.inmueble i2
          WHERE public.st_contains(l.geom, i2.geom)) total_loc ON (true))
  GROUP BY l.nombre, ic.nombre, total_loc.total
 HAVING (count(*) >= 3);


--
-- Name: VIEW v_caracteristicas_por_localidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_caracteristicas_por_localidad IS 'Distribución de cada amenidad por localidad con conteo y porcentaje.';


--
-- Name: v_catalogo_caracteristicas; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_catalogo_caracteristicas AS
 SELECT nombre AS caracteristica,
    count(*) AS total_inmuebles
   FROM iug.inmueble_caracteristica
  WHERE (valor_bool = true)
  GROUP BY nombre
  ORDER BY (count(*)) DESC;


--
-- Name: VIEW v_catalogo_caracteristicas; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_catalogo_caracteristicas IS 'Catálogo de amenidades disponibles con frecuencia. Usar para saber qué amenidades existen.';


--
-- Name: v_dotaciones_por_zona; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_dotaciones_por_zona AS
 WITH grid AS (
         SELECT (public.st_squaregrid((0.01)::double precision, public.st_setsrid((public.st_makebox2d(public.st_point(('-74.2'::numeric)::double precision, (4.4)::double precision), public.st_point(('-74.0'::numeric)::double precision, (4.9)::double precision)))::public.geometry, 4326))).geom AS geom
        )
 SELECT g.geom,
    public.st_y(public.st_centroid(g.geom)) AS lat_centro,
    public.st_x(public.st_centroid(g.geom)) AS lon_centro,
    count(
        CASE
            WHEN ((d.categoria)::text = ANY ((ARRAY['ips'::character varying, 'farmacia'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) AS total_salud,
    count(
        CASE
            WHEN ((d.categoria)::text = ANY ((ARRAY['colegio'::character varying, 'universidad'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) AS total_educacion,
    count(
        CASE
            WHEN ((d.categoria)::text = ANY ((ARRAY['centro_comercial'::character varying, 'plaza_mercado'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) AS total_comercio,
    count(
        CASE
            WHEN ((d.categoria)::text = ANY ((ARRAY['biblioteca'::character varying, 'teatro'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) AS total_cultura,
    count(
        CASE
            WHEN ((d.categoria)::text = ANY ((ARRAY['parque'::character varying, 'cancha_futbol'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) AS total_recreacion,
    count(d.id) AS total_dotaciones
   FROM (grid g
     LEFT JOIN iug.dotaciones_poi d ON (public.st_contains(g.geom, d.geom)))
  GROUP BY g.geom;


--
-- Name: VIEW v_dotaciones_por_zona; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_dotaciones_por_zona IS 'Grid con conteo de dotaciones por zona (1km x 1km)';


--
-- Name: v_estadisticas_localidad; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_estadisticas_localidad AS
 SELECT l.nombre AS nombre_localidad,
    count(i.id_inmueble) AS total_inmuebles,
    (avg(i.precio))::bigint AS precio_promedio,
    (min(i.precio))::bigint AS precio_minimo,
    (max(i.precio))::bigint AS precio_maximo,
    (avg(i.iurb))::numeric(4,2) AS iurb_promedio,
    (avg(i.iacc))::numeric(4,2) AS iacc_promedio,
    (avg(i.iseg))::numeric(4,2) AS iseg_promedio,
    (avg(i.ihed))::numeric(4,2) AS ihed_promedio,
    (avg(i.ipnu))::numeric(4,2) AS ipnu_promedio,
    (avg(i.precio_por_iurb))::numeric(15,2) AS precio_por_iurb_promedio,
    count(
        CASE
            WHEN (i.tipo_inmueble = 'Apartamento'::text) THEN 1
            ELSE NULL::integer
        END) AS total_apartamentos,
    count(
        CASE
            WHEN (i.tipo_inmueble = 'Casa'::text) THEN 1
            ELSE NULL::integer
        END) AS total_casas,
    l.geom
   FROM (iug.localidad l
     LEFT JOIN iug.inmueble i ON (public.st_contains(l.geom, i.geom)))
  GROUP BY l.nombre, l.geom;


--
-- Name: VIEW v_estadisticas_localidad; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_estadisticas_localidad IS 'Estadísticas agregadas por localidad para consultas LLM';


--
-- Name: v_historial_precios; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_historial_precios AS
 SELECT i.id_inmueble,
    i.codigo_fuente,
    i.pagina,
    i.ubicacion,
    (h.valor_anterior)::numeric AS precio_anterior,
    (h.valor_nuevo)::numeric AS precio_nuevo,
    round(((((h.valor_nuevo)::numeric - (h.valor_anterior)::numeric) / NULLIF((h.valor_anterior)::numeric, (0)::numeric)) * (100)::numeric), 2) AS variacion_pct,
    h.fecha_cambio
   FROM (iug.inmueble_historial h
     JOIN iug.inmueble i ON ((i.id_inmueble = h.id_inmueble)))
  WHERE (h.campo_modificado = 'precio'::text)
  ORDER BY h.fecha_cambio DESC;


--
-- Name: v_inmuebles_caracteristicas; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_inmuebles_caracteristicas AS
 SELECT i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
    l.nombre AS nombre_localidad,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND (ic.nombre ~~* '%piscina%'::text)))) AS tiene_piscina,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND (ic.nombre ~~* '%gimnasio%'::text)))) AS tiene_gimnasio,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%parqueadero%'::text) OR (ic.nombre ~~* '%garaje%'::text))))) AS tiene_parqueadero,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%vigilancia%'::text) OR (ic.nombre ~~* '%porter%'::text) OR (ic.nombre ~~* '%seguridad privada%'::text))))) AS tiene_vigilancia,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND (ic.nombre ~~* '%ascensor%'::text)))) AS tiene_ascensor,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%salon%comunal%'::text) OR (ic.nombre ~~* '%salón%comunal%'::text))))) AS tiene_salon_comunal,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%bbq%'::text) OR (ic.nombre ~~* '%asadero%'::text))))) AS tiene_bbq,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND (ic.nombre ~~* '%cancha%'::text)))) AS tiene_cancha,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%jacuzzi%'::text) OR (ic.nombre ~~* '%sauna%'::text) OR (ic.nombre ~~* '%turco%'::text))))) AS tiene_jacuzzi,
    (EXISTS ( SELECT 1
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true) AND ((ic.nombre ~~* '%depósito%'::text) OR (ic.nombre ~~* '%deposito%'::text))))) AS tiene_deposito,
    ( SELECT count(*) AS count
           FROM iug.inmueble_caracteristica ic
          WHERE ((ic.id_inmueble = i.id_inmueble) AND (ic.valor_bool = true))) AS total_caracteristicas
   FROM (iug.inmueble i
     LEFT JOIN iug.localidad l ON (public.st_contains(l.geom, i.geom)));


--
-- Name: VIEW v_inmuebles_caracteristicas; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_inmuebles_caracteristicas IS 'Inmuebles con 10 amenidades como columnas booleanas (tiene_piscina, tiene_gimnasio, etc). Consultar con WHERE tiene_X = TRUE.';


--
-- Name: v_inmuebles_contexto; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_inmuebles_contexto AS
 SELECT i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
    i.image,
    i.descripcion,
    i.iurb,
    i.iacc,
    i.iseg,
    i.ihed,
    i.ipnu,
    i.precio_por_iurb,
    public.st_y(i.geom) AS latitud,
    public.st_x(i.geom) AS longitud,
    l.nombre AS nombre_localidad,
    ( SELECT count(*) AS count
           FROM iug.dotaciones_poi d
          WHERE (((d.categoria)::text = ANY ((ARRAY['ips'::character varying, 'farmacia'::character varying])::text[])) AND public.st_dwithin((d.geom)::public.geography, (i.geom)::public.geography, (500)::double precision))) AS salud_500m,
    ( SELECT count(*) AS count
           FROM iug.dotaciones_poi d
          WHERE (((d.categoria)::text = ANY ((ARRAY['colegio'::character varying, 'universidad'::character varying])::text[])) AND public.st_dwithin((d.geom)::public.geography, (i.geom)::public.geography, (500)::double precision))) AS educacion_500m,
    ( SELECT count(*) AS count
           FROM iug.dotaciones_poi d
          WHERE (((d.categoria)::text = ANY ((ARRAY['parque'::character varying, 'cancha_futbol'::character varying])::text[])) AND public.st_dwithin((d.geom)::public.geography, (i.geom)::public.geography, (500)::double precision))) AS recreacion_500m,
    ( SELECT count(*) AS count
           FROM iug.estacion_transmilenio e
          WHERE public.st_dwithin((e.geom)::public.geography, (i.geom)::public.geography, (500)::double precision)) AS transmilenio_500m,
    ( SELECT c.hurto_personas_2024
           FROM iug.criminalidad_localidad c
          WHERE ((c.nombre_localidad)::text = l.nombre)
         LIMIT 1) AS tasa_hurto_localidad
   FROM (iug.inmueble i
     LEFT JOIN iug.localidad l ON (public.st_contains(l.geom, i.geom)));


--
-- Name: v_pot_completo; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_pot_completo AS
 SELECT i.id_inmueble,
    i.direccion,
    i.tipo_inmueble,
    i.geom,
    e.pisos_max,
    e.altura_max_m,
    e.rango AS rango_edificabilidad,
    t.tipo AS tipo_tratamiento,
    t.nombre AS tratamiento,
    a.nombre AS area_actividad,
    a.normativa,
    u.nombre AS upl,
    u.estado AS estado_upl
   FROM ((((iug.inmueble i
     LEFT JOIN iug.pot_edificabilidad e ON (public.st_within(i.geom, e.geom)))
     LEFT JOIN iug.pot_tratamiento t ON (public.st_within(i.geom, t.geom)))
     LEFT JOIN iug.pot_area_actividad a ON (public.st_within(i.geom, a.geom)))
     LEFT JOIN iug.pot_upl u ON (public.st_within(i.geom, u.geom)));


--
-- Name: VIEW v_pot_completo; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_pot_completo IS 'Vista consolidada de informaci??n POT por inmueble';


--
-- Name: v_precios_por_tipo; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_precios_por_tipo AS
 SELECT tipo_inmueble,
    count(*) AS total,
    (avg(precio))::bigint AS precio_promedio,
    (percentile_cont((0.25)::double precision) WITHIN GROUP (ORDER BY ((precio)::double precision)))::bigint AS precio_p25,
    (percentile_cont((0.50)::double precision) WITHIN GROUP (ORDER BY ((precio)::double precision)))::bigint AS precio_mediana,
    (percentile_cont((0.75)::double precision) WITHIN GROUP (ORDER BY ((precio)::double precision)))::bigint AS precio_p75,
    (min(precio))::bigint AS precio_min,
    (max(precio))::bigint AS precio_max,
    (avg(area))::numeric(10,2) AS area_promedio,
    (avg((precio / NULLIF(area, (0)::numeric))))::bigint AS precio_m2_promedio
   FROM iug.inmueble
  WHERE ((precio IS NOT NULL) AND (area IS NOT NULL))
  GROUP BY tipo_inmueble;


--
-- Name: VIEW v_precios_por_tipo; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_precios_por_tipo IS 'Estadísticas de precios agrupadas por tipo de inmueble';


--
-- Name: v_ranking_zonas; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_ranking_zonas AS
 SELECT l.nombre AS nombre_localidad,
    (avg(i.iurb))::numeric(4,2) AS iurb_promedio,
    (avg(i.iacc))::numeric(4,2) AS iacc_promedio,
    (avg(i.iseg))::numeric(4,2) AS iseg_promedio,
    (avg(i.ihed))::numeric(4,2) AS ihed_promedio,
    (avg(i.ipnu))::numeric(4,2) AS ipnu_promedio,
    count(i.id_inmueble) AS total_inmuebles,
    rank() OVER (ORDER BY (avg(i.iurb)) DESC) AS ranking_iurb,
    rank() OVER (ORDER BY (avg(i.iacc)) DESC) AS ranking_iacc,
    rank() OVER (ORDER BY (avg(i.iseg)) DESC) AS ranking_iseg,
    rank() OVER (ORDER BY (avg(i.ihed)) DESC) AS ranking_ihed,
    rank() OVER (ORDER BY (avg(i.ipnu)) DESC) AS ranking_ipnu
   FROM (iug.localidad l
     LEFT JOIN iug.inmueble i ON (public.st_contains(l.geom, i.geom)))
  GROUP BY l.nombre
 HAVING (count(i.id_inmueble) > 0);


--
-- Name: VIEW v_ranking_zonas; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_ranking_zonas IS 'Ranking de localidades por cada indicador';


--
-- Name: v_resumen_indicadores; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_resumen_indicadores AS
 SELECT 'Localidades'::text AS nivel,
    count(*) AS total,
    count(*) FILTER (WHERE (indicador_localidad.iug IS NOT NULL)) AS con_iug,
    round(avg(indicador_localidad.iug), 2) AS iug_promedio
   FROM iug.indicador_localidad
UNION ALL
 SELECT 'Barrios'::text AS nivel,
    count(*) AS total,
    count(*) FILTER (WHERE (indicador_barrio.iug IS NOT NULL)) AS con_iug,
    round(avg(indicador_barrio.iug), 2) AS iug_promedio
   FROM iug.indicador_barrio
UNION ALL
 SELECT 'Inmuebles'::text AS nivel,
    count(*) AS total,
    count(*) FILTER (WHERE (inmueble.iug IS NOT NULL)) AS con_iug,
    round(avg(inmueble.iug), 2) AS iug_promedio
   FROM iug.inmueble;


--
-- Name: v_top_oportunidades; Type: VIEW; Schema: iug; Owner: -
--

CREATE VIEW iug.v_top_oportunidades AS
 SELECT id_inmueble,
    tipo_inmueble,
    precio,
    ubicacion,
    area,
    habitaciones,
    banos,
    iurb,
    iacc,
    iseg,
    ihed,
    ipnu,
    precio_por_iurb,
    public.st_y(geom) AS latitud,
    public.st_x(geom) AS longitud,
    percent_rank() OVER (ORDER BY precio_por_iurb) AS percentil_oportunidad
   FROM iug.inmueble i
  WHERE ((iurb IS NOT NULL) AND (precio_por_iurb IS NOT NULL) AND (iurb >= 3.0));


--
-- Name: VIEW v_top_oportunidades; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON VIEW iug.v_top_oportunidades IS 'Ranking de inmuebles por oportunidad (precio/I_URB)';


--
-- Name: ahp_pesos_crimen id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.ahp_pesos_crimen ALTER COLUMN id SET DEFAULT nextval('iug.ahp_pesos_crimen_id_seq'::regclass);


--
-- Name: area_actividad id_area; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.area_actividad ALTER COLUMN id_area SET DEFAULT nextval('iug.area_actividad_id_area_seq'::regclass);


--
-- Name: barrio id_barrio; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.barrio ALTER COLUMN id_barrio SET DEFAULT nextval('iug.barrio_id_barrio_seq'::regclass);


--
-- Name: cai_policia id_cai; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cai_policia ALTER COLUMN id_cai SET DEFAULT nextval('iug.cai_policia_id_cai_seq'::regclass);


--
-- Name: cat_caracteristica id_caracteristica; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cat_caracteristica ALTER COLUMN id_caracteristica SET DEFAULT nextval('iug.cat_caracteristica_id_caracteristica_seq'::regclass);


--
-- Name: centro_comercial id_cc; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.centro_comercial ALTER COLUMN id_cc SET DEFAULT nextval('iug.centro_comercial_id_cc_seq'::regclass);


--
-- Name: centro_salud id_centro; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.centro_salud ALTER COLUMN id_centro SET DEFAULT nextval('iug.centro_salud_id_centro_seq'::regclass);


--
-- Name: colegio id_colegio; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.colegio ALTER COLUMN id_colegio SET DEFAULT nextval('iug.colegio_id_colegio_seq'::regclass);


--
-- Name: criminalidad_localidad id_crim; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.criminalidad_localidad ALTER COLUMN id_crim SET DEFAULT nextval('iug.criminalidad_localidad_id_crim_seq'::regclass);


--
-- Name: cuadrante_policia id_cuadrante; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cuadrante_policia ALTER COLUMN id_cuadrante SET DEFAULT nextval('iug.cuadrante_policia_id_cuadrante_seq'::regclass);


--
-- Name: dotacion_abastecimiento id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_abastecimiento ALTER COLUMN id SET DEFAULT nextval('iug.dotacion_abastecimiento_id_seq'::regclass);


--
-- Name: dotacion_cultura id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_cultura ALTER COLUMN id SET DEFAULT nextval('iug.dotacion_cultura_id_seq'::regclass);


--
-- Name: dotacion_educacion id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_educacion ALTER COLUMN id SET DEFAULT nextval('iug.dotacion_educacion_id_seq'::regclass);


--
-- Name: dotacion_recreacion id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_recreacion ALTER COLUMN id SET DEFAULT nextval('iug.dotacion_recreacion_id_seq'::regclass);


--
-- Name: dotacion_salud id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_salud ALTER COLUMN id SET DEFAULT nextval('iug.dotacion_salud_id_seq'::regclass);


--
-- Name: dotaciones_poi id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotaciones_poi ALTER COLUMN id SET DEFAULT nextval('iug.dotaciones_poi_id_seq'::regclass);


--
-- Name: edificabilidad id_edificabilidad; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.edificabilidad ALTER COLUMN id_edificabilidad SET DEFAULT nextval('iug.edificabilidad_id_edificabilidad_seq'::regclass);


--
-- Name: estacion_metro id_estacion; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.estacion_metro ALTER COLUMN id_estacion SET DEFAULT nextval('iug.estacion_metro_id_estacion_seq'::regclass);


--
-- Name: estacion_transmilenio id_estacion; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.estacion_transmilenio ALTER COLUMN id_estacion SET DEFAULT nextval('iug.estacion_transmilenio_id_estacion_seq'::regclass);


--
-- Name: indicador_amenidades_raw id_indicador; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_amenidades_raw ALTER COLUMN id_indicador SET DEFAULT nextval('iug.indicador_amenidades_raw_id_indicador_seq'::regclass);


--
-- Name: indicador_dotacion_raw id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_dotacion_raw ALTER COLUMN id SET DEFAULT nextval('iug.indicador_dotacion_raw_id_seq'::regclass);


--
-- Name: indicador_seguridad_raw id_indicador; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_seguridad_raw ALTER COLUMN id_indicador SET DEFAULT nextval('iug.indicador_seguridad_raw_id_indicador_seq'::regclass);


--
-- Name: inmueble id_inmueble; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble ALTER COLUMN id_inmueble SET DEFAULT nextval('iug.inmueble_id_inmueble_seq'::regclass);


--
-- Name: inmueble_historial id_historial; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_historial ALTER COLUMN id_historial SET DEFAULT nextval('iug.inmueble_historial_id_historial_seq'::regclass);


--
-- Name: inmueble_scrapeo id_scrapeo; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_scrapeo ALTER COLUMN id_scrapeo SET DEFAULT nextval('iug.inmueble_scrapeo_id_scrapeo_seq'::regclass);


--
-- Name: localidad id_localidad; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.localidad ALTER COLUMN id_localidad SET DEFAULT nextval('iug.localidad_id_localidad_seq'::regclass);


--
-- Name: malla_vial id_via; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.malla_vial ALTER COLUMN id_via SET DEFAULT nextval('iug.malla_vial_id_via_seq'::regclass);


--
-- Name: modelo_hedonico id_modelo; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.modelo_hedonico ALTER COLUMN id_modelo SET DEFAULT nextval('iug.modelo_hedonico_id_modelo_seq'::regclass);


--
-- Name: osm_main_roads id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_main_roads ALTER COLUMN id SET DEFAULT nextval('iug.osm_main_roads_id_seq'::regclass);


--
-- Name: osm_parks id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_parks ALTER COLUMN id SET DEFAULT nextval('iug.osm_parks_id_seq'::regclass);


--
-- Name: osm_transport id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_transport ALTER COLUMN id SET DEFAULT nextval('iug.osm_transport_id_seq'::regclass);


--
-- Name: pesos_dotacion id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion ALTER COLUMN id SET DEFAULT nextval('iug.pesos_dotacion_id_seq'::regclass);


--
-- Name: pesos_dotacion_ahp id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion_ahp ALTER COLUMN id SET DEFAULT nextval('iug.pesos_dotacion_ahp_id_seq'::regclass);


--
-- Name: pesos_iug id_config; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_iug ALTER COLUMN id_config SET DEFAULT nextval('iug.pesos_iug_id_config_seq'::regclass);


--
-- Name: poi id_poi; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.poi ALTER COLUMN id_poi SET DEFAULT nextval('iug.poi_id_poi_seq'::regclass);


--
-- Name: pot_area_actividad id_area; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_area_actividad ALTER COLUMN id_area SET DEFAULT nextval('iug.pot_area_actividad_id_area_seq'::regclass);


--
-- Name: pot_edificabilidad id_edificabilidad; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_edificabilidad ALTER COLUMN id_edificabilidad SET DEFAULT nextval('iug.pot_edificabilidad_id_edificabilidad_seq'::regclass);


--
-- Name: pot_tratamiento id_tratamiento; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_tratamiento ALTER COLUMN id_tratamiento SET DEFAULT nextval('iug.pot_tratamiento_id_tratamiento_seq'::regclass);


--
-- Name: pot_upl id_upl; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_upl ALTER COLUMN id_upl SET DEFAULT nextval('iug.pot_upl_id_upl_seq'::regclass);


--
-- Name: ruta_sitp id_ruta; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.ruta_sitp ALTER COLUMN id_ruta SET DEFAULT nextval('iug.ruta_sitp_id_ruta_seq'::regclass);


--
-- Name: sector id_sector; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector ALTER COLUMN id_sector SET DEFAULT nextval('iug.sector_id_sector_seq'::regclass);


--
-- Name: sector_catastral id_sector; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_catastral ALTER COLUMN id_sector SET DEFAULT nextval('iug.sector_catastral_id_sector_seq'::regclass);


--
-- Name: sector_priorizado id_sector; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_priorizado ALTER COLUMN id_sector SET DEFAULT nextval('iug.sector_priorizado_id_sector_seq'::regclass);


--
-- Name: sector_seguridad id_sector; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_seguridad ALTER COLUMN id_sector SET DEFAULT nextval('iug.sector_seguridad_id_sector_seq'::regclass);


--
-- Name: sitp_paradero id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sitp_paradero ALTER COLUMN id SET DEFAULT nextval('iug.sitp_paradero_id_seq'::regclass);


--
-- Name: tm_estacion id; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.tm_estacion ALTER COLUMN id SET DEFAULT nextval('iug.tm_estacion_id_seq'::regclass);


--
-- Name: tratamiento_urbanistico id_tratamiento; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.tratamiento_urbanistico ALTER COLUMN id_tratamiento SET DEFAULT nextval('iug.tratamiento_urbanistico_id_tratamiento_seq'::regclass);


--
-- Name: universidad id_universidad; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.universidad ALTER COLUMN id_universidad SET DEFAULT nextval('iug.universidad_id_universidad_seq'::regclass);


--
-- Name: upl id_upl; Type: DEFAULT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.upl ALTER COLUMN id_upl SET DEFAULT nextval('iug.upl_id_upl_seq'::regclass);


--
-- Name: ahp_pesos_crimen ahp_pesos_crimen_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.ahp_pesos_crimen
    ADD CONSTRAINT ahp_pesos_crimen_pkey PRIMARY KEY (id);


--
-- Name: ahp_pesos_crimen ahp_pesos_crimen_tipo_delito_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.ahp_pesos_crimen
    ADD CONSTRAINT ahp_pesos_crimen_tipo_delito_key UNIQUE (tipo_delito);


--
-- Name: area_actividad area_actividad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.area_actividad
    ADD CONSTRAINT area_actividad_pkey PRIMARY KEY (id_area);


--
-- Name: barrio barrio_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.barrio
    ADD CONSTRAINT barrio_pkey PRIMARY KEY (id_barrio);


--
-- Name: barrio barrio_unq; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.barrio
    ADD CONSTRAINT barrio_unq UNIQUE (id_localidad, nombre);


--
-- Name: cai_policia cai_policia_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cai_policia
    ADD CONSTRAINT cai_policia_pkey PRIMARY KEY (id_cai);


--
-- Name: cat_caracteristica cat_caracteristica_nombre_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cat_caracteristica
    ADD CONSTRAINT cat_caracteristica_nombre_key UNIQUE (nombre);


--
-- Name: cat_caracteristica cat_caracteristica_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cat_caracteristica
    ADD CONSTRAINT cat_caracteristica_pkey PRIMARY KEY (id_caracteristica);


--
-- Name: cat_estado_inmueble cat_estado_inmueble_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cat_estado_inmueble
    ADD CONSTRAINT cat_estado_inmueble_pkey PRIMARY KEY (estado);


--
-- Name: cat_tipo_inmueble cat_tipo_inmueble_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cat_tipo_inmueble
    ADD CONSTRAINT cat_tipo_inmueble_pkey PRIMARY KEY (tipo_inmueble);


--
-- Name: centro_comercial centro_comercial_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.centro_comercial
    ADD CONSTRAINT centro_comercial_pkey PRIMARY KEY (id_cc);


--
-- Name: centro_salud centro_salud_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.centro_salud
    ADD CONSTRAINT centro_salud_pkey PRIMARY KEY (id_centro);


--
-- Name: colegio colegio_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.colegio
    ADD CONSTRAINT colegio_pkey PRIMARY KEY (id_colegio);


--
-- Name: criminalidad_localidad criminalidad_localidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.criminalidad_localidad
    ADD CONSTRAINT criminalidad_localidad_pkey PRIMARY KEY (id_crim);


--
-- Name: cuadrante_policia cuadrante_policia_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.cuadrante_policia
    ADD CONSTRAINT cuadrante_policia_pkey PRIMARY KEY (id_cuadrante);


--
-- Name: dotacion_abastecimiento dotacion_abastecimiento_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_abastecimiento
    ADD CONSTRAINT dotacion_abastecimiento_pkey PRIMARY KEY (id);


--
-- Name: dotacion_cultura dotacion_cultura_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_cultura
    ADD CONSTRAINT dotacion_cultura_pkey PRIMARY KEY (id);


--
-- Name: dotacion_educacion dotacion_educacion_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_educacion
    ADD CONSTRAINT dotacion_educacion_pkey PRIMARY KEY (id);


--
-- Name: dotacion_recreacion dotacion_recreacion_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_recreacion
    ADD CONSTRAINT dotacion_recreacion_pkey PRIMARY KEY (id);


--
-- Name: dotacion_salud dotacion_salud_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotacion_salud
    ADD CONSTRAINT dotacion_salud_pkey PRIMARY KEY (id);


--
-- Name: dotaciones_poi dotaciones_poi_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.dotaciones_poi
    ADD CONSTRAINT dotaciones_poi_pkey PRIMARY KEY (id);


--
-- Name: edificabilidad edificabilidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.edificabilidad
    ADD CONSTRAINT edificabilidad_pkey PRIMARY KEY (id_edificabilidad);


--
-- Name: estacion_metro estacion_metro_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.estacion_metro
    ADD CONSTRAINT estacion_metro_pkey PRIMARY KEY (id_estacion);


--
-- Name: estacion_transmilenio estacion_transmilenio_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.estacion_transmilenio
    ADD CONSTRAINT estacion_transmilenio_pkey PRIMARY KEY (id_estacion);


--
-- Name: flyway_schema_history flyway_schema_history_pk; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.flyway_schema_history
    ADD CONSTRAINT flyway_schema_history_pk PRIMARY KEY (installed_rank);


--
-- Name: hedonic_model_coefs hedonic_model_coefs_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.hedonic_model_coefs
    ADD CONSTRAINT hedonic_model_coefs_pkey PRIMARY KEY (tipo_inmueble);


--
-- Name: indicador_amenidades_raw indicador_amenidades_raw_id_inmueble_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_amenidades_raw
    ADD CONSTRAINT indicador_amenidades_raw_id_inmueble_key UNIQUE (id_inmueble);


--
-- Name: indicador_amenidades_raw indicador_amenidades_raw_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_amenidades_raw
    ADD CONSTRAINT indicador_amenidades_raw_pkey PRIMARY KEY (id_indicador);


--
-- Name: indicador_barrio indicador_barrio_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_barrio
    ADD CONSTRAINT indicador_barrio_pkey PRIMARY KEY (id_barrio);


--
-- Name: indicador_dotacion_raw indicador_dotacion_raw_id_inmueble_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_dotacion_raw
    ADD CONSTRAINT indicador_dotacion_raw_id_inmueble_key UNIQUE (id_inmueble);


--
-- Name: indicador_dotacion_raw indicador_dotacion_raw_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_dotacion_raw
    ADD CONSTRAINT indicador_dotacion_raw_pkey PRIMARY KEY (id);


--
-- Name: indicador_localidad indicador_localidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_localidad
    ADD CONSTRAINT indicador_localidad_pkey PRIMARY KEY (id_localidad);


--
-- Name: indicador_seguridad_raw indicador_seguridad_raw_id_inmueble_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_seguridad_raw
    ADD CONSTRAINT indicador_seguridad_raw_id_inmueble_key UNIQUE (id_inmueble);


--
-- Name: indicador_seguridad_raw indicador_seguridad_raw_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_seguridad_raw
    ADD CONSTRAINT indicador_seguridad_raw_pkey PRIMARY KEY (id_indicador);


--
-- Name: indicador_transporte_raw indicador_transporte_raw_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_transporte_raw
    ADD CONSTRAINT indicador_transporte_raw_pkey PRIMARY KEY (id_inmueble);


--
-- Name: inmueble_caracteristica inmueble_caracteristica_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_caracteristica
    ADD CONSTRAINT inmueble_caracteristica_pkey PRIMARY KEY (id_inmueble, nombre);


--
-- Name: inmueble_historial inmueble_historial_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_historial
    ADD CONSTRAINT inmueble_historial_pkey PRIMARY KEY (id_historial);


--
-- Name: inmueble inmueble_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT inmueble_pkey PRIMARY KEY (id_inmueble);


--
-- Name: inmueble_scrapeo inmueble_scrapeo_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_scrapeo
    ADD CONSTRAINT inmueble_scrapeo_pkey PRIMARY KEY (id_scrapeo);


--
-- Name: localidad localidad_nombre_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.localidad
    ADD CONSTRAINT localidad_nombre_key UNIQUE (nombre);


--
-- Name: localidad localidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.localidad
    ADD CONSTRAINT localidad_pkey PRIMARY KEY (id_localidad);


--
-- Name: malla_vial malla_vial_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.malla_vial
    ADD CONSTRAINT malla_vial_pkey PRIMARY KEY (id_via);


--
-- Name: modelo_hedonico modelo_hedonico_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.modelo_hedonico
    ADD CONSTRAINT modelo_hedonico_pkey PRIMARY KEY (id_modelo);


--
-- Name: modelo_hedonico modelo_hedonico_uniq; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.modelo_hedonico
    ADD CONSTRAINT modelo_hedonico_uniq UNIQUE (nombre, tipo_inmueble);


--
-- Name: normalizacion_seguridad normalizacion_seguridad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.normalizacion_seguridad
    ADD CONSTRAINT normalizacion_seguridad_pkey PRIMARY KEY (tipo_inmueble);


--
-- Name: osm_main_roads osm_main_roads_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_main_roads
    ADD CONSTRAINT osm_main_roads_pkey PRIMARY KEY (id);


--
-- Name: osm_parks osm_parks_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_parks
    ADD CONSTRAINT osm_parks_pkey PRIMARY KEY (id);


--
-- Name: osm_transport osm_transport_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.osm_transport
    ADD CONSTRAINT osm_transport_pkey PRIMARY KEY (id);


--
-- Name: pca_pesos_amenidades pca_pesos_amenidades_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pca_pesos_amenidades
    ADD CONSTRAINT pca_pesos_amenidades_pkey PRIMARY KEY (tipo_inmueble);


--
-- Name: pca_pesos_tipo pca_pesos_tipo_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pca_pesos_tipo
    ADD CONSTRAINT pca_pesos_tipo_pkey PRIMARY KEY (tipo_inmueble);


--
-- Name: pesos_dotacion_ahp pesos_dotacion_ahp_categoria_1_categoria_2_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion_ahp
    ADD CONSTRAINT pesos_dotacion_ahp_categoria_1_categoria_2_key UNIQUE (categoria_1, categoria_2);


--
-- Name: pesos_dotacion_ahp pesos_dotacion_ahp_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion_ahp
    ADD CONSTRAINT pesos_dotacion_ahp_pkey PRIMARY KEY (id);


--
-- Name: pesos_dotacion pesos_dotacion_categoria_key; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion
    ADD CONSTRAINT pesos_dotacion_categoria_key UNIQUE (categoria);


--
-- Name: pesos_dotacion pesos_dotacion_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_dotacion
    ADD CONSTRAINT pesos_dotacion_pkey PRIMARY KEY (id);


--
-- Name: pesos_iug pesos_iug_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_iug
    ADD CONSTRAINT pesos_iug_pkey PRIMARY KEY (id_config);


--
-- Name: pesos_iug pesos_iug_uniq; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pesos_iug
    ADD CONSTRAINT pesos_iug_uniq UNIQUE (nombre);


--
-- Name: poi poi_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.poi
    ADD CONSTRAINT poi_pkey PRIMARY KEY (id_poi);


--
-- Name: pot_area_actividad pot_area_actividad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_area_actividad
    ADD CONSTRAINT pot_area_actividad_pkey PRIMARY KEY (id_area);


--
-- Name: pot_edificabilidad pot_edificabilidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_edificabilidad
    ADD CONSTRAINT pot_edificabilidad_pkey PRIMARY KEY (id_edificabilidad);


--
-- Name: pot_tratamiento pot_tratamiento_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_tratamiento
    ADD CONSTRAINT pot_tratamiento_pkey PRIMARY KEY (id_tratamiento);


--
-- Name: pot_upl pot_upl_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.pot_upl
    ADD CONSTRAINT pot_upl_pkey PRIMARY KEY (id_upl);


--
-- Name: ruta_sitp ruta_sitp_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.ruta_sitp
    ADD CONSTRAINT ruta_sitp_pkey PRIMARY KEY (id_ruta);


--
-- Name: sector_catastral sector_catastral_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_catastral
    ADD CONSTRAINT sector_catastral_pkey PRIMARY KEY (id_sector);


--
-- Name: sector sector_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector
    ADD CONSTRAINT sector_pkey PRIMARY KEY (id_sector);


--
-- Name: sector_priorizado sector_priorizado_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_priorizado
    ADD CONSTRAINT sector_priorizado_pkey PRIMARY KEY (id_sector);


--
-- Name: sector_seguridad sector_seguridad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sector_seguridad
    ADD CONSTRAINT sector_seguridad_pkey PRIMARY KEY (id_sector);


--
-- Name: sitp_paradero sitp_paradero_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.sitp_paradero
    ADD CONSTRAINT sitp_paradero_pkey PRIMARY KEY (id);


--
-- Name: tm_estacion tm_estacion_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.tm_estacion
    ADD CONSTRAINT tm_estacion_pkey PRIMARY KEY (id);


--
-- Name: tratamiento_urbanistico tratamiento_urbanistico_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.tratamiento_urbanistico
    ADD CONSTRAINT tratamiento_urbanistico_pkey PRIMARY KEY (id_tratamiento);


--
-- Name: inmueble uniq_inmueble_fuente_unidad; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT uniq_inmueble_fuente_unidad UNIQUE (pagina, codigo_fuente, area_construida, habitaciones, banos);


--
-- Name: universidad universidad_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.universidad
    ADD CONSTRAINT universidad_pkey PRIMARY KEY (id_universidad);


--
-- Name: upl upl_pkey; Type: CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.upl
    ADD CONSTRAINT upl_pkey PRIMARY KEY (id_upl);


--
-- Name: flyway_schema_history_s_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX flyway_schema_history_s_idx ON iug.flyway_schema_history USING btree (success);


--
-- Name: idx_amenidades_final_id; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX idx_amenidades_final_id ON iug.indicador_amenidades_final USING btree (id_inmueble);


--
-- Name: idx_amenidades_final_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_amenidades_final_tipo ON iug.indicador_amenidades_final USING btree (tipo_inmueble);


--
-- Name: idx_amenidades_raw_inmueble; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_amenidades_raw_inmueble ON iug.indicador_amenidades_raw USING btree (id_inmueble);


--
-- Name: idx_amenidades_raw_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_amenidades_raw_tipo ON iug.indicador_amenidades_raw USING btree (tipo_inmueble);


--
-- Name: idx_area_actividad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_area_actividad_geom ON iug.area_actividad USING gist (geom);


--
-- Name: idx_barrio_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_barrio_geom ON iug.barrio USING gist (geom);


--
-- Name: idx_cai_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_cai_geom ON iug.cai_policia USING gist (geom);


--
-- Name: idx_cc_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_cc_geom ON iug.centro_comercial USING gist (geom);


--
-- Name: idx_centro_salud_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_centro_salud_geom ON iug.centro_salud USING gist (geom);


--
-- Name: idx_colegio_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_colegio_geom ON iug.colegio USING gist (geom);


--
-- Name: idx_crim_local_codigo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_crim_local_codigo ON iug.criminalidad_localidad USING btree (codigo_localidad);


--
-- Name: idx_crim_local_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_crim_local_geom ON iug.criminalidad_localidad USING gist (geom);


--
-- Name: idx_cuadrante_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_cuadrante_geom ON iug.cuadrante_policia USING gist (geom);


--
-- Name: idx_dotacion_abastecimiento_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotacion_abastecimiento_geom ON iug.dotacion_abastecimiento USING gist (geom);


--
-- Name: idx_dotacion_cultura_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotacion_cultura_geom ON iug.dotacion_cultura USING gist (geom);


--
-- Name: idx_dotacion_educacion_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotacion_educacion_geom ON iug.dotacion_educacion USING gist (geom);


--
-- Name: idx_dotacion_recreacion_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotacion_recreacion_geom ON iug.dotacion_recreacion USING gist (geom);


--
-- Name: idx_dotacion_salud_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotacion_salud_geom ON iug.dotacion_salud USING gist (geom);


--
-- Name: idx_dotaciones_categoria; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotaciones_categoria ON iug.dotaciones_poi USING btree (categoria);


--
-- Name: idx_dotaciones_poi_cat; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotaciones_poi_cat ON iug.dotaciones_poi USING btree (categoria);


--
-- Name: idx_dotaciones_poi_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_dotaciones_poi_geom ON iug.dotaciones_poi USING gist (geom);


--
-- Name: idx_edificabilidad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_edificabilidad_geom ON iug.edificabilidad USING gist (geom);


--
-- Name: idx_estacion_metro_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_estacion_metro_geom ON iug.estacion_metro USING gist (geom);


--
-- Name: idx_estacion_tm_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_estacion_tm_geom ON iug.estacion_transmilenio USING gist (geom);


--
-- Name: idx_final_id; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX idx_final_id ON iug.indicador_transporte_final USING btree (id_inmueble);


--
-- Name: idx_final_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_final_tipo ON iug.indicador_transporte_final USING btree (tipo_inmueble);


--
-- Name: idx_historial_fecha; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_historial_fecha ON iug.inmueble_historial USING btree (fecha_cambio);


--
-- Name: idx_historial_inmueble; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_historial_inmueble ON iug.inmueble_historial USING btree (id_inmueble);


--
-- Name: idx_ind_localidad_iug; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_ind_localidad_iug ON iug.indicador_localidad USING btree (iug);


--
-- Name: idx_indicador_dotacion_final_pk; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX idx_indicador_dotacion_final_pk ON iug.indicador_dotacion_final USING btree (id_inmueble);


--
-- Name: idx_indicador_dotacion_inmueble; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_indicador_dotacion_inmueble ON iug.indicador_dotacion_raw USING btree (id_inmueble);


--
-- Name: idx_inmueble_precio_iurb; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_inmueble_precio_iurb ON iug.inmueble USING btree (precio_por_iurb) WHERE (precio_por_iurb IS NOT NULL);


--
-- Name: idx_inmueble_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_inmueble_tipo ON iug.inmueble USING btree (tipo_inmueble);


--
-- Name: idx_localidad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_localidad_geom ON iug.localidad USING gist (geom);


--
-- Name: idx_oportunidades_categoria; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_oportunidades_categoria ON iug.analisis_oportunidades USING btree (categoria_oportunidad);


--
-- Name: idx_oportunidades_iurb; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_oportunidades_iurb ON iug.analisis_oportunidades USING btree (iurb);


--
-- Name: idx_oportunidades_precio; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_oportunidades_precio ON iug.analisis_oportunidades USING btree (precio);


--
-- Name: idx_oportunidades_ratio; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_oportunidades_ratio ON iug.analisis_oportunidades USING btree (precio_por_iurb);


--
-- Name: idx_oportunidades_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_oportunidades_tipo ON iug.analisis_oportunidades USING btree (tipo_inmueble);


--
-- Name: idx_pot_area_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_area_geom ON iug.pot_area_actividad USING gist (geom);


--
-- Name: idx_pot_edificabilidad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_edificabilidad_geom ON iug.pot_edificabilidad USING gist (geom);


--
-- Name: idx_pot_edificabilidad_pisos; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_edificabilidad_pisos ON iug.pot_edificabilidad USING btree (pisos_max);


--
-- Name: idx_pot_tratamiento_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_tratamiento_geom ON iug.pot_tratamiento USING gist (geom);


--
-- Name: idx_pot_tratamiento_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_tratamiento_tipo ON iug.pot_tratamiento USING btree (tipo);


--
-- Name: idx_pot_upl_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_upl_geom ON iug.pot_upl USING gist (geom);


--
-- Name: idx_pot_upl_localidad; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_pot_upl_localidad ON iug.pot_upl USING btree (localidad);


--
-- Name: idx_raw_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_raw_tipo ON iug.indicador_transporte_raw USING btree (tipo_inmueble);


--
-- Name: idx_ruta_sitp_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_ruta_sitp_geom ON iug.ruta_sitp USING gist (geom);


--
-- Name: idx_scrapeo_fecha; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_scrapeo_fecha ON iug.inmueble_scrapeo USING btree (fecha_scrapeo DESC);


--
-- Name: idx_scrapeo_inmueble; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_scrapeo_inmueble ON iug.inmueble_scrapeo USING btree (id_inmueble);


--
-- Name: idx_scrapeo_pagina; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_scrapeo_pagina ON iug.inmueble_scrapeo USING btree (pagina);


--
-- Name: idx_sector_catastral_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_sector_catastral_geom ON iug.sector_catastral USING gist (geom);


--
-- Name: idx_sector_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_sector_geom ON iug.sector USING gist (geom);


--
-- Name: idx_sector_prior_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_sector_prior_geom ON iug.sector_priorizado USING gist (geom);


--
-- Name: idx_sector_seguridad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_sector_seguridad_geom ON iug.sector_seguridad USING gist (geom);


--
-- Name: idx_seg_final_id; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX idx_seg_final_id ON iug.indicador_seguridad_final USING btree (id_inmueble);


--
-- Name: idx_seg_final_score; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_seg_final_score ON iug.indicador_seguridad_final USING btree (score_seguridad_final DESC);


--
-- Name: idx_seg_final_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_seg_final_tipo ON iug.indicador_seguridad_final USING btree (tipo_inmueble);


--
-- Name: idx_seg_raw_inmueble; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_seg_raw_inmueble ON iug.indicador_seguridad_raw USING btree (id_inmueble);


--
-- Name: idx_seg_raw_tipo; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_seg_raw_tipo ON iug.indicador_seguridad_raw USING btree (tipo_inmueble);


--
-- Name: idx_tratamiento_urbanistico_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_tratamiento_urbanistico_geom ON iug.tratamiento_urbanistico USING gist (geom);


--
-- Name: idx_universidad_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_universidad_geom ON iug.universidad USING gist (geom);


--
-- Name: idx_upl_geom; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX idx_upl_geom ON iug.upl USING gist (geom);


--
-- Name: iug_barrio_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_barrio_gix ON iug.barrio USING gist (geom);


--
-- Name: iug_barrio_loc_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_barrio_loc_idx ON iug.barrio USING btree (id_localidad);


--
-- Name: iug_barrio_upz_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_barrio_upz_idx ON iug.barrio USING btree (codigo_upz);


--
-- Name: iug_idx_ic_nombre; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_idx_ic_nombre ON iug.inmueble_caracteristica USING btree (nombre);


--
-- Name: iug_idx_ic_valor_bool; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_idx_ic_valor_bool ON iug.inmueble_caracteristica USING btree (valor_bool);


--
-- Name: iug_idx_ic_valor_num; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_idx_ic_valor_num ON iug.inmueble_caracteristica USING btree (valor_num);


--
-- Name: iug_idx_ind_barrio_iacc; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_idx_ind_barrio_iacc ON iug.indicador_barrio USING btree (iacc);


--
-- Name: iug_idx_ind_barrio_iseg; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_idx_ind_barrio_iseg ON iug.indicador_barrio USING btree (iseg);


--
-- Name: iug_inmueble_barrio_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_inmueble_barrio_idx ON iug.inmueble USING btree (id_barrio);


--
-- Name: iug_inmueble_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_inmueble_gix ON iug.inmueble USING gist (geom);


--
-- Name: iug_inmueble_localidad_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_inmueble_localidad_idx ON iug.inmueble USING btree (id_localidad);


--
-- Name: iug_inmueble_tipo_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_inmueble_tipo_idx ON iug.inmueble USING btree (tipo_inmueble);


--
-- Name: iug_localidad_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX iug_localidad_gix ON iug.localidad USING gist (geom);


--
-- Name: malla_vial_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX malla_vial_gix ON iug.malla_vial USING gist (geom);


--
-- Name: poi_cat_idx; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX poi_cat_idx ON iug.poi USING btree (categoria);


--
-- Name: poi_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX poi_gix ON iug.poi USING gist (geom);


--
-- Name: sitp_paradero_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX sitp_paradero_gix ON iug.sitp_paradero USING gist (geom);


--
-- Name: sitp_paradero_objectid_uniq; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX sitp_paradero_objectid_uniq ON iug.sitp_paradero USING btree (objectid) WHERE (objectid IS NOT NULL);


--
-- Name: sitp_paradero_props_gin; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX sitp_paradero_props_gin ON iug.sitp_paradero USING gin (props);


--
-- Name: tm_estacion_gix; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX tm_estacion_gix ON iug.tm_estacion USING gist (geom);


--
-- Name: tm_estacion_objectid_uniq; Type: INDEX; Schema: iug; Owner: -
--

CREATE UNIQUE INDEX tm_estacion_objectid_uniq ON iug.tm_estacion USING btree (objectid) WHERE (objectid IS NOT NULL);


--
-- Name: tm_estacion_props_gin; Type: INDEX; Schema: iug; Owner: -
--

CREATE INDEX tm_estacion_props_gin ON iug.tm_estacion USING gin (props);


--
-- Name: barrio trg_barrio_snap_localidad; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_barrio_snap_localidad BEFORE INSERT OR UPDATE OF geom ON iug.barrio FOR EACH ROW EXECUTE FUNCTION iug.f_snap_barrio_localidad();


--
-- Name: inmueble trg_inmueble_audit; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_audit BEFORE UPDATE ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.f_audit_inmueble_changes();


--
-- Name: inmueble trg_inmueble_barrio_change; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_barrio_change BEFORE INSERT OR UPDATE OF id_barrio, ihed, precio_std ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.f_inmueble_on_barrio_change();


--
-- Name: inmueble trg_inmueble_dotacion; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_dotacion AFTER INSERT OR UPDATE OF geom ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.trg_calcular_dotacion();


--
-- Name: TRIGGER trg_inmueble_dotacion ON inmueble; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TRIGGER trg_inmueble_dotacion ON iug.inmueble IS 'Calcula I_DOT autom??ticamente en INSERT/UPDATE. Desactivado hasta cargar datos.';


--
-- Name: inmueble trg_inmueble_iurb; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_iurb BEFORE INSERT OR UPDATE OF iacc, iseg, ihed, ipnu ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.trg_actualizar_iurb();


--
-- Name: TRIGGER trg_inmueble_iurb ON inmueble; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TRIGGER trg_inmueble_iurb ON iug.inmueble IS 'Trigger que mantiene I_URB sincronizado con sus componentes';


--
-- Name: inmueble trg_inmueble_precio_por_iurb; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_precio_por_iurb BEFORE INSERT OR UPDATE OF precio, iurb ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.trg_actualizar_precio_por_iurb();


--
-- Name: TRIGGER trg_inmueble_precio_por_iurb ON inmueble; Type: COMMENT; Schema: iug; Owner: -
--

COMMENT ON TRIGGER trg_inmueble_precio_por_iurb ON iug.inmueble IS 'Actualiza automáticamente precio_por_iurb cuando cambia precio o I_URB';


--
-- Name: inmueble trg_inmueble_seguridad; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_seguridad AFTER INSERT OR UPDATE OF geom, tipo_inmueble ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.trigger_calcular_seguridad();


--
-- Name: inmueble trg_inmueble_snap_geom; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_inmueble_snap_geom BEFORE INSERT OR UPDATE OF geom ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.f_snap_inmueble_barrios();


--
-- Name: inmueble trg_proyecto_tipo; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_proyecto_tipo BEFORE INSERT OR UPDATE ON iug.inmueble FOR EACH ROW EXECUTE FUNCTION iug.enforce_proyecto_apartamento();


--
-- Name: indicador_barrio trg_sync_ind_barrio; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_sync_ind_barrio AFTER INSERT OR UPDATE OF iacc, iseg, idot, ipnu, iug ON iug.indicador_barrio FOR EACH ROW EXECUTE FUNCTION iug.f_sync_indicadores_barrio();


--
-- Name: indicador_localidad trg_sync_ind_localidad; Type: TRIGGER; Schema: iug; Owner: -
--

CREATE TRIGGER trg_sync_ind_localidad AFTER INSERT OR UPDATE OF iacc, iseg, idot, ipnu, iug ON iug.indicador_localidad FOR EACH ROW EXECUTE FUNCTION iug.f_sync_indicadores_localidad();


--
-- Name: barrio barrio_id_localidad_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.barrio
    ADD CONSTRAINT barrio_id_localidad_fkey FOREIGN KEY (id_localidad) REFERENCES iug.localidad(id_localidad) ON DELETE RESTRICT;


--
-- Name: indicador_amenidades_raw indicador_amenidades_raw_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_amenidades_raw
    ADD CONSTRAINT indicador_amenidades_raw_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: indicador_barrio indicador_barrio_id_barrio_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_barrio
    ADD CONSTRAINT indicador_barrio_id_barrio_fkey FOREIGN KEY (id_barrio) REFERENCES iug.barrio(id_barrio) ON DELETE CASCADE;


--
-- Name: indicador_dotacion_raw indicador_dotacion_raw_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_dotacion_raw
    ADD CONSTRAINT indicador_dotacion_raw_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: indicador_localidad indicador_localidad_id_localidad_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_localidad
    ADD CONSTRAINT indicador_localidad_id_localidad_fkey FOREIGN KEY (id_localidad) REFERENCES iug.localidad(id_localidad) ON DELETE CASCADE;


--
-- Name: indicador_seguridad_raw indicador_seguridad_raw_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_seguridad_raw
    ADD CONSTRAINT indicador_seguridad_raw_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: indicador_transporte_raw indicador_transporte_raw_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.indicador_transporte_raw
    ADD CONSTRAINT indicador_transporte_raw_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: inmueble_caracteristica inmueble_caracteristica_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_caracteristica
    ADD CONSTRAINT inmueble_caracteristica_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: inmueble inmueble_estado_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT inmueble_estado_fkey FOREIGN KEY (estado) REFERENCES iug.cat_estado_inmueble(estado);


--
-- Name: inmueble_historial inmueble_historial_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_historial
    ADD CONSTRAINT inmueble_historial_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: inmueble inmueble_id_barrio_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT inmueble_id_barrio_fkey FOREIGN KEY (id_barrio) REFERENCES iug.barrio(id_barrio);


--
-- Name: inmueble inmueble_id_localidad_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT inmueble_id_localidad_fkey FOREIGN KEY (id_localidad) REFERENCES iug.localidad(id_localidad);


--
-- Name: inmueble_scrapeo inmueble_scrapeo_id_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble_scrapeo
    ADD CONSTRAINT inmueble_scrapeo_id_inmueble_fkey FOREIGN KEY (id_inmueble) REFERENCES iug.inmueble(id_inmueble) ON DELETE CASCADE;


--
-- Name: inmueble inmueble_tipo_inmueble_fkey; Type: FK CONSTRAINT; Schema: iug; Owner: -
--

ALTER TABLE ONLY iug.inmueble
    ADD CONSTRAINT inmueble_tipo_inmueble_fkey FOREIGN KEY (tipo_inmueble) REFERENCES iug.cat_tipo_inmueble(tipo_inmueble);


--
-- PostgreSQL database dump complete
--

