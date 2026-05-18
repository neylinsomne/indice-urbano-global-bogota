-- =====================================================
-- PostgreSQL NOTIFY Triggers para Individual Inserts
-- =====================================================
-- Emite eventos cuando se inserta/actualiza inmueble individual
-- Capturado por Python listener en orchestrator/individual_insert.py

-- =====================================================
-- 1. Función NOTIFY para Creación
-- =====================================================
CREATE OR REPLACE FUNCTION iug.notify_inmueble_created()
RETURNS trigger AS $$
BEGIN
    -- Emitir notificación con datos del inmueble
    PERFORM pg_notify('inmueble_created', 
        json_build_object(
            'id_inmueble', NEW.id_inmueble,
            'tipo_inmueble', NEW.tipo_inmueble,
            'has_coordinates', (NEW.geom IS NOT NULL),
            'area_construida', NEW.area_construida,
            'precio', NEW.precio
        )::text
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 2. Función NOTIFY para Actualización
-- =====================================================
CREATE OR REPLACE FUNCTION iug.notify_inmueble_updated()
RETURNS trigger AS $$
DECLARE
    campos_modificados text[];
BEGIN
    -- Detectar qué campos cambiaron
    campos_modificados := ARRAY[]::text[];
    
    IF OLD.precio IS DISTINCT FROM NEW.precio THEN
        campos_modificados := array_append(campos_modificados, 'precio');
    END IF;
    
    IF OLD.area_construida IS DISTINCT FROM NEW.area_construida THEN
        campos_modificados := array_append(campos_modificados, 'area_construida');
    END IF;
    
    IF OLD.habitaciones IS DISTINCT FROM NEW.habitaciones THEN
        campos_modificados := array_append(campos_modificados, 'habitaciones');
    END IF;
    
    IF OLD.geom IS DISTINCT FROM NEW.geom THEN
        campos_modificados := array_append(campos_modificados, 'ubicacion');
    END IF;
    
    -- Solo notificar si hubo cambios significativos
    IF array_length(campos_modificados, 1) > 0 THEN
        PERFORM pg_notify('inmueble_updated',
            json_build_object(
                'id_inmueble', NEW.id_inmueble,
                'campos_modificados', campos_modificados
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 3. Triggers NOTIFY
-- =====================================================

-- Trigger para INSERT (después de triggers de indicadores)
DROP TRIGGER IF EXISTS trg_notify_inmueble_created ON iug.inmueble;
CREATE TRIGGER trg_notify_inmueble_created
AFTER INSERT ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.notify_inmueble_created();

-- Trigger para UPDATE (después de triggers de indicadores)
DROP TRIGGER IF EXISTS trg_notify_inmueble_updated ON iug.inmueble;
CREATE TRIGGER trg_notify_inmueble_updated
AFTER UPDATE ON iug.inmueble
FOR EACH ROW
EXECUTE FUNCTION iug.notify_inmueble_updated();

COMMENT ON TRIGGER trg_notify_inmueble_created ON iug.inmueble IS 'Emite evento para orquestador Python cuando se crea inmueble';
COMMENT ON TRIGGER trg_notify_inmueble_updated ON iug.inmueble IS 'Emite evento para orquestador Python cuando se actualiza inmueble';
