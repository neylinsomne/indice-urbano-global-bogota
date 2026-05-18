-- Create views to simplify access to OSM features

-- 1. Education View
CREATE OR REPLACE VIEW iug.osm_education AS
SELECT osm_id, name, amenity as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_point
WHERE amenity IN ('school', 'university', 'college', 'kindergarten')
UNION ALL
SELECT osm_id, name, amenity as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_polygon
WHERE amenity IN ('school', 'university', 'college', 'kindergarten');

-- 2. Health View
CREATE OR REPLACE VIEW iug.osm_health AS
SELECT osm_id, name, amenity as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_point
WHERE amenity IN ('hospital', 'clinic', 'doctors', 'pharmacy', 'dentist')
UNION ALL
SELECT osm_id, name, amenity as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_polygon
WHERE amenity IN ('hospital', 'clinic', 'doctors', 'pharmacy', 'dentist');

-- 3. Transport View (Bus stops, Stations)
CREATE OR REPLACE VIEW iug.osm_transport AS
SELECT osm_id, name, highway as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_point
WHERE highway = 'bus_stop' OR railway IN ('station', 'subway_entrance') OR amenity = 'bus_station'
UNION ALL
SELECT osm_id, name, highway as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_polygon
WHERE amenity = 'bus_station' OR railway IN ('station');

-- 4. Parks and Leisure View
CREATE OR REPLACE VIEW iug.osm_parks AS
SELECT osm_id, name, leisure as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_polygon
WHERE leisure IN ('park', 'garden', 'pitch', 'playground', 'sports_centre', 'stadium')
OR landuse IN ('grass', 'recreation_ground');

-- 5. Commercial View (Malls, Supermarkets)
CREATE OR REPLACE VIEW iug.osm_commercial AS
SELECT osm_id, name, shop as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_point
WHERE shop IN ('supermarket', 'mall', 'department_store') OR amenity = 'marketplace'
UNION ALL
SELECT osm_id, name, shop as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_polygon
WHERE shop IN ('supermarket', 'mall', 'department_store') OR amenity = 'marketplace';

-- 6. Main Roads View
CREATE OR REPLACE VIEW iug.osm_main_roads AS
SELECT osm_id, name, highway as type, ST_Transform(way, 4326) as geom
FROM public.planet_osm_line
WHERE highway IN ('motorway', 'trunk', 'primary', 'secondary', 'tertiary');

-- 7. Materialized View for Property Indicators
-- Calculates nearest distance to key amenities for each property
-- (Assuming `iug.inmueble` has a geometry column named `geom` or `ubicacion`)
-- WARNING: This can be slow on large datasets, hence Materialized View.

-- 7. Materialized View for Property Indicators
-- Calculates nearest distance to key amenities for each property

CREATE MATERIALIZED VIEW IF NOT EXISTS iug.mv_inmueble_osm_indicators AS
SELECT 
    i.id_inmueble as inmueble_id,
    -- Distance to nearest Park
    (SELECT ROUND(ST_Distance(i.geom::geography, p.geom::geography)::numeric, 2)
        FROM iug.osm_parks p ORDER BY i.geom <-> p.geom LIMIT 1) as dist_park_m,
        
    -- Distance to nearest School
    (SELECT ROUND(ST_Distance(i.geom::geography, e.geom::geography)::numeric, 2)
        FROM iug.osm_education e ORDER BY i.geom <-> e.geom LIMIT 1) as dist_education_m,
        
    -- Distance to nearest Health facility
    (SELECT ROUND(ST_Distance(i.geom::geography, h.geom::geography)::numeric, 2)
        FROM iug.osm_health h ORDER BY i.geom <-> h.geom LIMIT 1) as dist_health_m,
        
    -- Distance to nearest Transport stop
    (SELECT ROUND(ST_Distance(i.geom::geography, t.geom::geography)::numeric, 2)
        FROM iug.osm_transport t ORDER BY i.geom <-> t.geom LIMIT 1) as dist_transport_m,
        
    -- Distance to nearest Main Road
    (SELECT ROUND(ST_Distance(i.geom::geography, r.geom::geography)::numeric, 2)
        FROM iug.osm_main_roads r ORDER BY i.geom <-> r.geom LIMIT 1) as dist_main_road_m
        
FROM iug.inmueble i;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_inmueble_osm_indicators_id ON iug.mv_inmueble_osm_indicators(inmueble_id);
