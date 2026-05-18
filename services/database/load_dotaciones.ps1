# =====================================================
# Script: Cargar Dotaciones desde GeoJSON/OSM
# =====================================================
# Ejecutar DESPUÉS de aplicar migración V25
# Usa ogr2ogr en Docker para cargar archivos GeoJSON
# =====================================================

$ErrorActionPreference = "Continue"

# Configuración
$DATA_PATH = "C:\Users\neylp\OneDrive\Escritorio\LUPA\Estudio_inmobiliario\services\database\archivos\archivos\dotaciones"
$OSM_PATH = "C:\Users\neylp\OneDrive\Escritorio\LUPA\Estudio_inmobiliario\services\database\archivos\archivos\Bogota.osm.pbf"
$NETWORK = "estudio_inmobiliario_app-network"
$PG_CONN = "PG:host=iug-postgres port=5432 dbname=postgres user=postgres password=xd"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " CARGA DE DOTACIONES - GeoJSON + OSM" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# =====================================================
# 1. SALUD (salud.geojson - IPS)
# =====================================================
Write-Host "[1/8] Cargando Salud (IPS)..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/salud.geojson `
    -nln iug.dotacion_salud_temp `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

# Mover a tabla final con mapeo de columnas
docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_salud (nombre, tipo, direccion, localidad, geom)
SELECT 
    COALESCE(\"Nombre_IPS\", 'Sin nombre'),
    CASE 
        WHEN LOWER(\"Nombre_IPS\") LIKE '%hospital%' THEN 'hospital'
        WHEN LOWER(\"Nombre_IPS\") LIKE '%clinica%' THEN 'clinica'
        ELSE 'ips'
    END,
    \"Direccion\",
    \"LocNombre\",
    geom
FROM iug.dotacion_salud_temp;
DROP TABLE IF EXISTS iug.dotacion_salud_temp;
"

Write-Host "   OK Salud cargado" -ForegroundColor Green

# =====================================================
# 2. FARMACIAS (farmacias.geojson)
# =====================================================
Write-Host "[2/8] Cargando Farmacias..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/farmacias.geojson `
    -nln iug.dotacion_salud_farmacias `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_salud (nombre, tipo, geom)
SELECT COALESCE(name, 'Farmacia'), 'farmacia', geom 
FROM iug.dotacion_salud_farmacias;
DROP TABLE IF EXISTS iug.dotacion_salud_farmacias;
"

Write-Host "   OK Farmacias cargado" -ForegroundColor Green

# =====================================================
# 3. COLEGIOS (colegios12_2024.geojson)
# =====================================================
Write-Host "[3/8] Cargando Colegios..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/colegios12_2024.geojson `
    -nln iug.dotacion_educacion_temp `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_educacion (nombre, tipo, sector, geom)
SELECT 
    COALESCE(nombre, 'Colegio'),
    'colegio',
    CASE WHEN sector ILIKE '%oficial%' THEN 'oficial' ELSE 'privado' END,
    geom
FROM iug.dotacion_educacion_temp
WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.dotacion_educacion_temp;
"

Write-Host "   OK Colegios cargado" -ForegroundColor Green

# =====================================================
# 4. UNIVERSIDADES (ecosistema_educacion_superior.geojson)
# =====================================================
Write-Host "[4/8] Cargando Universidades..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/ecosistema_educacion_superior.geojson `
    -nln iug.dotacion_educacion_univ `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_educacion (nombre, tipo, sector, geom)
SELECT COALESCE(nombre, ies_padre, 'Universidad'), 'universidad', 'privado', geom
FROM iug.dotacion_educacion_univ
WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.dotacion_educacion_univ;
"

Write-Host "   OK Universidades cargado" -ForegroundColor Green

# =====================================================
# 5. CULTURA - Bibliotecas y Teatros
# =====================================================
Write-Host "[5/8] Cargando Cultura (Bibliotecas + Teatros)..." -ForegroundColor Yellow

# Bibliotecas
docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/biblored.geojson `
    -nln iug.dotacion_cultura_biblio `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_cultura (nombre, tipo, geom)
SELECT COALESCE(nombre, 'Biblioteca'), 'biblioteca', geom
FROM iug.dotacion_cultura_biblio WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.dotacion_cultura_biblio;
"

# Teatros
docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/teatroauditorio.json `
    -nln iug.dotacion_cultura_teatro `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_cultura (nombre, tipo, geom)
SELECT COALESCE(nombre, 'Teatro'), 'teatro', geom
FROM iug.dotacion_cultura_teatro WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.dotacion_cultura_teatro;
"

Write-Host "   OK Cultura cargado" -ForegroundColor Green

# =====================================================
# 6. ABASTECIMIENTO - Plazas de Mercado
# =====================================================
Write-Host "[6/8] Cargando Plazas de Mercado..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${DATA_PATH}:/data:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/plaza_mercado.geojson `
    -nln iug.dotacion_abastecimiento_plaza `
    -t_srs EPSG:4326 `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_abastecimiento (nombre, tipo, geom)
SELECT COALESCE(nombre, 'Plaza de Mercado'), 'plaza_mercado', geom
FROM iug.dotacion_abastecimiento_plaza WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.dotacion_abastecimiento_plaza;
"

Write-Host "   OK Plazas cargado" -ForegroundColor Green

# =====================================================
# 7. ABASTECIMIENTO - Supermercados/Tiendas desde OSM
# =====================================================
Write-Host "[7/8] Extrayendo Supermercados/Tiendas de OSM..." -ForegroundColor Yellow

docker run --rm --network $NETWORK `
    -v "${OSM_PATH}:/data/bogota.osm.pbf:ro" `
    osgeo/gdal:alpine-small-latest `
    ogr2ogr -f PostgreSQL "$PG_CONN" `
    /data/bogota.osm.pbf `
    -sql "SELECT name, shop, brand FROM points WHERE shop IN ('supermarket', 'convenience', 'department_store', 'mall', 'greengrocer')" `
    -nln iug.osm_shops_temp `
    -lco GEOMETRY_NAME=geom `
    -overwrite

docker exec iug-postgres psql -U postgres -c "
INSERT INTO iug.dotacion_abastecimiento (nombre, tipo, marca, geom)
SELECT 
    COALESCE(name, shop),
    CASE 
        WHEN shop = 'convenience' THEN 'tienda'
        WHEN shop = 'mall' OR shop = 'department_store' THEN 'centro_comercial'
        ELSE 'supermercado'
    END,
    brand,
    geom
FROM iug.osm_shops_temp WHERE geom IS NOT NULL;
DROP TABLE IF EXISTS iug.osm_shops_temp;
"

Write-Host "   OK OSM Shops cargado" -ForegroundColor Green

# =====================================================
# 8. ESTADÍSTICAS FINALES
# =====================================================
Write-Host ""
Write-Host "[8/8] Verificando conteos..." -ForegroundColor Yellow

docker exec iug-postgres psql -U postgres -c "
SELECT 'Salud' as categoria, COUNT(*) as registros FROM iug.dotacion_salud
UNION ALL SELECT 'Educacion', COUNT(*) FROM iug.dotacion_educacion
UNION ALL SELECT 'Abastecimiento', COUNT(*) FROM iug.dotacion_abastecimiento
UNION ALL SELECT 'Cultura', COUNT(*) FROM iug.dotacion_cultura
UNION ALL SELECT 'Recreacion', COUNT(*) FROM iug.dotacion_recreacion
ORDER BY categoria;
"

# =====================================================
# HABILITAR TRIGGER
# =====================================================
Write-Host ""
Write-Host "Habilitando trigger de dotacion..." -ForegroundColor Yellow

docker exec iug-postgres psql -U postgres -c "
ALTER TABLE iug.inmueble ENABLE TRIGGER trg_inmueble_dotacion;
"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " CARGA COMPLETADA" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Próximos pasos:" -ForegroundColor Yellow
Write-Host "  1. Ejecutar cálculo masivo: SELECT iug.recalcular_dotacion_masivo(100);" -ForegroundColor White
Write-Host "  2. Verificar vista: SELECT * FROM iug.indicador_dotacion_final LIMIT 10;" -ForegroundColor White
