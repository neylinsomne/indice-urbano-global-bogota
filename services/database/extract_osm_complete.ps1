# Script PowerShell para extraer datos OSM usando Docker con GDAL
# Extrae: SITP (bus_stop), vías principales, y parques

$OSM_FILE = "C:\Users\neylp\OneDrive\Escritorio\LUPA\Estudio_inmobiliario\services\database\archivos\archivos\Bogota.osm.pbf"
$PG_CONN = "PG:host=iug-postgres port=5432 dbname=postgres user=postgres password=xd"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Extrayendo datos OSM completos desde Bogota.osm.pbf" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. SITP Bus Stops
Write-Host "🚌 Extrayendo paradas SITP..." -ForegroundColor Yellow
docker run --rm `
    --network estudio_inmobiliario_app-network `
    -v "${OSM_FILE}:/data/bogota.osm.pbf":ro `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr `
    -f PostgreSQL `
    "$PG_CONN" `
    /data/bogota.osm.pbf `
    -sql "SELECT * FROM points WHERE amenity='bus_stop'" `
    -nln "iug.osm_sitp_temp" `
    -lco GEOMETRY_NAME=geom `
    -overwrite `
    -progress

Write-Host "   ✅ SITP extraído" -ForegroundColor Green

# 2. Vías Principales
Write-Host "🛣️ Extrayendo vías principales..." -ForegroundColor Yellow
docker run --rm `
    --network estudio_inmobiliario_app-network `
    -v "${OSM_FILE}:/data/bogota.osm.pbf":ro `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr `
    -f PostgreSQL `
    "$PG_CONN" `
    /data/bogota.osm.pbf `
    -sql "SELECT * FROM lines WHERE highway IN ('motorway','trunk','primary','secondary','tertiary')" `
    -nln "iug.osm_roads_temp" `
    -lco GEOMETRY_NAME=geom `
    -overwrite `
    -progress

Write-Host "   ✅ Vías extraídas" -ForegroundColor Green

# 3. Parques
Write-Host "🌳 Extrayendo parques..." -ForegroundColor Yellow
docker run --rm `
    --network estudio_inmobiliario_app-network `
    -v "${OSM_FILE}:/data/bogota.osm.pbf":ro `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr `
    -f PostgreSQL `
    "$PG_CONN" `
    /data/bogota.osm.pbf `
    -sql "SELECT * FROM multipolygons WHERE leisure='park' OR landuse='recreation_ground' OR leisure='playground'" `
    -nln "iug.osm_parks_temp" `
    -lco GEOMETRY_NAME=geom `
    -overwrite `
    -progress

Write-Host "   ✅ Parques extraídos" -ForegroundColor Green

# 4. Mover datos a tablas finales
Write-Host "" 
Write-Host "📦 Moviendo datos a tablas finales..." -ForegroundColor Yellow

docker exec iug-postgres psql -U postgres -c @"
-- SITP
TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;
INSERT INTO iug.osm_transport (type, name, geom)
SELECT 'bus_stop', name, geom FROM iug.osm_sitp_temp;

-- Vías
TRUNCATE iug.osm_main_roads RESTART IDENTITY CASCADE;
INSERT INTO iug.osm_main_roads (name, highway, geom)
SELECT name, highway, geom FROM iug.osm_roads_temp;

-- Parques
TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;
INSERT INTO iug.osm_parks (name, geom)
SELECT name, geom FROM iug.osm_parks_temp;

-- Limpiar temporales
DROP TABLE IF EXISTS iug.osm_sitp_temp;
DROP TABLE IF EXISTS iug.osm_roads_temp;
DROP TABLE IF EXISTS iug.osm_parks_temp;
"@

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "✅ Extracción OSM Completa" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan

# Mostrar estadísticas
docker exec iug-postgres psql -U postgres -c "SELECT 'SITP' as capa, COUNT(*) as registros FROM iug.osm_transport UNION ALL SELECT 'Vías', COUNT(*) FROM iug.osm_main_roads UNION ALL SELECT 'Parques', COUNT(*) FROM iug.osm_parks;"
