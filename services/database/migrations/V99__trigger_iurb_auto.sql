/*
================================================================================
TRIGGER AUTOMATICO PARA I_URB
================================================================================

Actualiza automáticamente I_URB cuando cambian los indicadores base:
- I_ACC (Accesibilidad)
- I_SEG (Seguridad)
- I_HED (Calidad Hedónica)
- I_PNU (Potencial Normativo)

Formula: I_URB = (0.25×I_ACC + 0.20×I_SEG + 0.25×I_HED + 0.30×I_PNU) / total_pesos
================================================================================
*/

-- Función trigger para actualizar I_URB
CREATE OR REPLACE FUNCTION iug.trg_actualizar_iurb()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

-- Crear trigger en INSERT y UPDATE
DROP TRIGGER IF EXISTS trg_inmueble_iurb ON iug.inmueble;

CREATE TRIGGER trg_inmueble_iurb
    BEFORE INSERT OR UPDATE OF iacc, iseg, ihed, ipnu
    ON iug.inmueble
    FOR EACH ROW
    EXECUTE FUNCTION iug.trg_actualizar_iurb();

-- Comentarios
COMMENT ON FUNCTION iug.trg_actualizar_iurb() IS
'Actualiza automáticamente I_URB cuando cambian los indicadores base (I_ACC, I_SEG, I_HED, I_PNU)';

COMMENT ON TRIGGER trg_inmueble_iurb ON iug.inmueble IS
'Trigger que mantiene I_URB sincronizado con sus componentes';
