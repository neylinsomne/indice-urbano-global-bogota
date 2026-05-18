-- =============================================================================
-- V8__triggers_propagacion.sql
-- Flyway Migration: Triggers para PROPAGAR indicadores (sin calcular)
-- Los cálculos se hacen en Python, estos triggers solo sincronizan valores
-- =============================================================================

-- 1) Trigger: cuando se actualizan indicadores del barrio → propaga a inmuebles
CREATE OR REPLACE FUNCTION iug.f_sync_indicadores_barrio()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_ind_barrio ON iug.indicador_barrio;
CREATE TRIGGER trg_sync_ind_barrio
AFTER INSERT OR UPDATE OF iacc, iseg, idot, ipnu, iug
ON iug.indicador_barrio
FOR EACH ROW EXECUTE FUNCTION iug.f_sync_indicadores_barrio();

-- 2) Trigger: cuando se actualizan indicadores de localidad → propaga a barrios
CREATE OR REPLACE FUNCTION iug.f_sync_indicadores_localidad()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_ind_localidad ON iug.indicador_localidad;
CREATE TRIGGER trg_sync_ind_localidad
AFTER INSERT OR UPDATE OF iacc, iseg, idot, ipnu, iug
ON iug.indicador_localidad
FOR EACH ROW EXECUTE FUNCTION iug.f_sync_indicadores_localidad();

-- 3) Trigger: al insertar/actualizar inmueble con geom → asigna barrio/localidad
-- (Ya existe en 06_indicadores_y_triggers.sql, pero lo reforzamos)
CREATE OR REPLACE FUNCTION iug.f_snap_inmueble_barrios()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inmueble_snap_geom ON iug.inmueble;
CREATE TRIGGER trg_inmueble_snap_geom
BEFORE INSERT OR UPDATE OF geom
ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.f_snap_inmueble_barrios();

-- Vista resumen para monitoreo
CREATE OR REPLACE VIEW iug.v_resumen_indicadores AS
SELECT 'Localidades' AS nivel, COUNT(*) AS total,
    COUNT(*) FILTER (WHERE iug IS NOT NULL) AS con_iug,
    ROUND(AVG(iug), 2) AS iug_promedio
FROM iug.indicador_localidad
UNION ALL
SELECT 'Barrios', COUNT(*), COUNT(*) FILTER (WHERE iug IS NOT NULL), ROUND(AVG(iug), 2)
FROM iug.indicador_barrio
UNION ALL
SELECT 'Inmuebles', COUNT(*), COUNT(*) FILTER (WHERE iug IS NOT NULL), ROUND(AVG(iug), 2)
FROM iug.inmueble;

-- Comentarios
COMMENT ON FUNCTION iug.f_sync_indicadores_barrio IS 
'Propaga indicadores de barrio a inmuebles cuando se actualizan. NO calcula, solo sincroniza.';
COMMENT ON FUNCTION iug.f_sync_indicadores_localidad IS 
'Propaga indicadores de localidad a barrios (como fallback). NO calcula, solo sincroniza.';
