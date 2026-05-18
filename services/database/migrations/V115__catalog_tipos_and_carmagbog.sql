-- =====================================================
-- V115: Agregar tipos faltantes al catálogo y CRS CarMAGBOG
-- =====================================================

-- Tipos de inmueble que faltaban en el catálogo
INSERT INTO iug.cat_tipo_inmueble (tipo_inmueble) VALUES
    ('Apartamento'), ('Casa'), ('Lote'), ('Inmueble')
ON CONFLICT DO NOTHING;

-- CRS CarMAGBOG para transformación de datos POT de Bogotá
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext)
VALUES (
    900001, 'CUSTOM', 900001,
    '+proj=tmerc +lat_0=4.680486111 +lon_0=-74.14659167 +k=1.0 +x_0=92334.879 +y_0=109320.965 +ellps=GRS80 +a=6380687.0 +rf=298.257222101 +units=m +no_defs',
    'PROJCS["PCS_CarMAGBOG",GEOGCS["GCS_CarMAGBOG",DATUM["CGS_CarMAGBOG",SPHEROID["GRS80_Mod",6380687.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",92334.879],PARAMETER["False_Northing",109320.965],PARAMETER["Central_Meridian",-74.14659167],PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",4.680486111],UNIT["Meter",1.0]]'
) ON CONFLICT (srid) DO NOTHING;

-- Función para asignar barrio y localidad por cruce espacial
CREATE OR REPLACE FUNCTION iug.f_asignar_barrio_localidad()
RETURNS TABLE(total_asignados INT, total_por_cercania INT) AS $$
DECLARE
    n_intersect INT := 0;
    n_nearest INT := 0;
BEGIN
    -- 1. Asignar por intersección directa
    UPDATE iug.inmueble i
    SET id_barrio = (
        SELECT b.id_barrio FROM iug.barrio b
        WHERE ST_Intersects(i.geom, b.geom) LIMIT 1
    )
    WHERE i.geom IS NOT NULL AND i.id_barrio IS NULL;
    GET DIAGNOSTICS n_intersect = ROW_COUNT;

    -- 2. Asignar por vecino más cercano (los que no cayeron dentro)
    UPDATE iug.inmueble i
    SET id_barrio = (
        SELECT b.id_barrio FROM iug.barrio b
        ORDER BY i.geom <-> b.geom LIMIT 1
    )
    WHERE i.geom IS NOT NULL AND i.id_barrio IS NULL;
    GET DIAGNOSTICS n_nearest = ROW_COUNT;

    -- 3. Asignar localidad desde barrio donde falta
    UPDATE iug.inmueble i
    SET id_localidad = b.id_localidad
    FROM iug.barrio b
    WHERE i.id_barrio = b.id_barrio AND i.id_localidad IS NULL;

    RETURN QUERY SELECT n_intersect, n_nearest;
END;
$$ LANGUAGE plpgsql;

-- Función para recalcular todos los indicadores
CREATE OR REPLACE FUNCTION iug.f_recalcular_indicadores()
RETURNS TABLE(inmuebles_actualizados INT) AS $$
DECLARE
    n INT := 0;
BEGIN
    -- Desactivar triggers para batch rápido
    ALTER TABLE iug.inmueble DISABLE TRIGGER ALL;

    -- iacc: accesibilidad (distancia a TransMilenio)
    UPDATE iug.inmueble i SET iacc = sub.score FROM (
        SELECT i2.id_inmueble,
            LEAST(5, GREATEST(0, 5 - (MIN(ST_Distance(i2.geom::geography, t.geom::geography)) / 500.0)))::numeric(4,2) as score
        FROM iug.inmueble i2
        CROSS JOIN LATERAL (
            SELECT geom FROM iug.estacion_transmilenio ORDER BY i2.geom <-> geom LIMIT 1
        ) t
        WHERE i2.geom IS NOT NULL
        GROUP BY i2.id_inmueble
    ) sub WHERE i.id_inmueble = sub.id_inmueble;

    -- iseg: seguridad (masa crimen de localidad)
    UPDATE iug.inmueble i SET iseg = sub.score FROM (
        SELECT i2.id_inmueble,
            LEAST(5, GREATEST(0, 5 * (1 - COALESCE(c.masa_crimen, 0.5))))::numeric(4,2) as score
        FROM iug.inmueble i2
        LEFT JOIN iug.localidad l ON i2.id_localidad = l.id_localidad
        LEFT JOIN iug.criminalidad_localidad c ON l.nombre ILIKE c.nombre_localidad
        WHERE i2.geom IS NOT NULL
    ) sub WHERE i.id_inmueble = sub.id_inmueble;

    -- idot: dotaciones (POIs cercanos 1km)
    UPDATE iug.inmueble i SET idot = sub.score FROM (
        SELECT i2.id_inmueble,
            LEAST(5, COUNT(d.*) * 0.05)::numeric(4,2) as score
        FROM iug.inmueble i2
        LEFT JOIN iug.dotaciones_poi d ON ST_DWithin(i2.geom::geography, d.geom::geography, 1000)
        WHERE i2.geom IS NOT NULL
        GROUP BY i2.id_inmueble
    ) sub WHERE i.id_inmueble = sub.id_inmueble;

    -- ihed: hedónico (área, habitaciones, baños)
    UPDATE iug.inmueble SET ihed = LEAST(5, GREATEST(0,
        COALESCE(habitaciones, 0) * 0.4 + COALESCE(banos, 0) * 0.5 + LEAST(COALESCE(area_construida, 0) / 50.0, 3)
    ))::numeric(4,2)
    WHERE geom IS NOT NULL;

    -- ipnu: potencial normativo (cruce con POT)
    WITH scores AS (
        SELECT i.id_inmueble,
            COALESCE(MAX(iug.score_tratamiento(t.nombre)), 2.5) as s_trat,
            COALESCE(MAX(iug.score_edificabilidad(e.rango)), 2.5) as s_alt,
            COALESCE(MAX(iug.score_area_actividad(a.codigo)), 3.0) as s_uso
        FROM iug.inmueble i
        LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
        LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
        LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
        WHERE i.geom IS NOT NULL
        GROUP BY i.id_inmueble
    )
    UPDATE iug.inmueble i SET ipnu = LEAST(5.0, GREATEST(0.0,
        (0.4 * s.s_trat) + (0.4 * s.s_alt) + (0.2 * s.s_uso)
    ))
    FROM scores s WHERE i.id_inmueble = s.id_inmueble;

    -- iug/iurb: promedio ponderado de los 5 indicadores
    UPDATE iug.inmueble SET
        iug = ROUND((COALESCE(iacc,0)*0.20 + COALESCE(iseg,0)*0.20 + COALESCE(idot,0)*0.20 + COALESCE(ihed,0)*0.20 + COALESCE(ipnu,0)*0.20)::numeric, 2),
        iurb = ROUND((COALESCE(iacc,0)*0.20 + COALESCE(iseg,0)*0.20 + COALESCE(idot,0)*0.20 + COALESCE(ihed,0)*0.20 + COALESCE(ipnu,0)*0.20)::numeric, 2)
    WHERE geom IS NOT NULL;

    GET DIAGNOSTICS n = ROW_COUNT;

    -- Reactivar triggers
    ALTER TABLE iug.inmueble ENABLE TRIGGER ALL;

    RETURN QUERY SELECT n;
END;
$$ LANGUAGE plpgsql;
