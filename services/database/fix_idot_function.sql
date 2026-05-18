-- Actualizar función I_DOT para usar tabla unificada dotaciones_poi
CREATE OR REPLACE FUNCTION iug.calcular_idot_poi(p_geom GEOMETRY)
RETURNS NUMERIC AS $$
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
$$ LANGUAGE plpgsql STABLE;

-- Actualizar trigger para usar nueva función
CREATE OR REPLACE FUNCTION iug.trg_calcular_dotacion()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

-- Función recálculo masivo
CREATE OR REPLACE FUNCTION iug.recalcular_dotacion_poi(p_limit INTEGER DEFAULT NULL)
RETURNS INTEGER AS $$
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
$$ LANGUAGE plpgsql;
