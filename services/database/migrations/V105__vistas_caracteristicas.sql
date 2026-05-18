-- =====================================================
-- V105: Vistas de Características para LLM Agent
-- =====================================================
-- Propósito: Crear las 3 vistas de características que
-- el agente SQL referencia pero no existían.
-- Pivotea el EAV (inmueble_caracteristica) a columnas
-- booleanas consultables por el LLM.

-- Drop vistas existentes (pueden tener columnas distintas)
DROP VIEW IF EXISTS iug.v_catalogo_caracteristicas CASCADE;
DROP VIEW IF EXISTS iug.v_inmuebles_caracteristicas CASCADE;
DROP VIEW IF EXISTS iug.v_caracteristicas_por_localidad CASCADE;

-- ============================================================
-- Vista 1: Catálogo de todas las características con frecuencia
-- ============================================================
CREATE OR REPLACE VIEW iug.v_catalogo_caracteristicas AS
SELECT
    nombre AS caracteristica,
    COUNT(*) AS total_inmuebles
FROM iug.inmueble_caracteristica
WHERE valor_bool = TRUE
GROUP BY nombre
ORDER BY total_inmuebles DESC;

COMMENT ON VIEW iug.v_catalogo_caracteristicas IS
    'Catálogo de amenidades disponibles con frecuencia. Usar para saber qué amenidades existen.';

-- ============================================================
-- Vista 2: Inmuebles con columnas booleanas de amenidades (pivot)
-- ============================================================
-- 10 amenidades más comunes de FincaRaiz, pivoteadas como columnas
-- El LLM puede consultar: WHERE tiene_piscina = TRUE AND tiene_gimnasio = TRUE

CREATE OR REPLACE VIEW iug.v_inmuebles_caracteristicas AS
SELECT
    i.id_inmueble,
    i.tipo_inmueble,
    i.precio,
    i.ubicacion,
    i.area,
    i.habitaciones,
    i.banos,
    l.nombre AS nombre_localidad,

    -- 10 amenidades pivoteadas
    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND ic.nombre ILIKE '%piscina%') AS tiene_piscina,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND ic.nombre ILIKE '%gimnasio%') AS tiene_gimnasio,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%parqueadero%' OR ic.nombre ILIKE '%garaje%')) AS tiene_parqueadero,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%vigilancia%' OR ic.nombre ILIKE '%porter%'
                 OR ic.nombre ILIKE '%seguridad privada%')) AS tiene_vigilancia,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND ic.nombre ILIKE '%ascensor%') AS tiene_ascensor,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%salon%comunal%' OR ic.nombre ILIKE '%salón%comunal%')) AS tiene_salon_comunal,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%bbq%' OR ic.nombre ILIKE '%asadero%')) AS tiene_bbq,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND ic.nombre ILIKE '%cancha%') AS tiene_cancha,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%jacuzzi%' OR ic.nombre ILIKE '%sauna%'
                 OR ic.nombre ILIKE '%turco%')) AS tiene_jacuzzi,

    EXISTS (SELECT 1 FROM iug.inmueble_caracteristica ic
            WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE
            AND (ic.nombre ILIKE '%depósito%' OR ic.nombre ILIKE '%deposito%')) AS tiene_deposito,

    -- Total de características del inmueble
    (SELECT COUNT(*) FROM iug.inmueble_caracteristica ic
     WHERE ic.id_inmueble = i.id_inmueble AND ic.valor_bool = TRUE) AS total_caracteristicas

FROM iug.inmueble i
LEFT JOIN iug.localidad l ON ST_Contains(l.geom, i.geom);

COMMENT ON VIEW iug.v_inmuebles_caracteristicas IS
    'Inmuebles con 10 amenidades como columnas booleanas (tiene_piscina, tiene_gimnasio, etc). Consultar con WHERE tiene_X = TRUE.';

-- ============================================================
-- Vista 3: Distribución de características por localidad
-- ============================================================
CREATE OR REPLACE VIEW iug.v_caracteristicas_por_localidad AS
SELECT
    l.nombre AS nombre_localidad,
    ic.nombre AS caracteristica,
    COUNT(*) AS inmuebles_con_caracteristica,
    total_loc.total AS total_inmuebles_localidad,
    ROUND(100.0 * COUNT(*) / NULLIF(total_loc.total, 0), 1) AS pct_con_caracteristica
FROM iug.localidad l
JOIN iug.inmueble i ON ST_Contains(l.geom, i.geom)
JOIN iug.inmueble_caracteristica ic
    ON i.id_inmueble = ic.id_inmueble
    AND ic.valor_bool = TRUE
JOIN LATERAL (
    SELECT COUNT(DISTINCT i2.id_inmueble) AS total
    FROM iug.inmueble i2
    WHERE ST_Contains(l.geom, i2.geom)
) total_loc ON TRUE
GROUP BY l.nombre, ic.nombre, total_loc.total
HAVING COUNT(*) >= 3;

COMMENT ON VIEW iug.v_caracteristicas_por_localidad IS
    'Distribución de cada amenidad por localidad con conteo y porcentaje.';
