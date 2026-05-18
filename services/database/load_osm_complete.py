"""
Script para extraer datos OSM completos usando ogr2ogr.
Extrae: SITP (bus_stop), vías principales (highways), y parques (leisure=park).
"""
import subprocess
import os
from pathlib import Path

OSM_FILE = Path(__file__).parent / "archivos" / "archivos" / "Bogota.osm.pbf"
PG_CONN = f"PG:host={os.getenv('PG_HOST', 'localhost')} port={os.getenv('PG_PORT', '5434')} dbname={os.getenv('PG_DB', 'postgres')} user={os.getenv('PG_USER', 'postgres')} password={os.getenv('PG_PASSWORD', 'xd')}"

print("=" * 70)
print("Extrayendo datos OSM completos de Bogota.osm.pbf")
print("=" * 70)

if not OSM_FILE.exists():
    print(f"❌ No se encontró {OSM_FILE}")
    exit(1)

print(f"\n📁 Archivo: {OSM_FILE}")
print(f"📊 Tamaño: {OSM_FILE.stat().st_size / 1024 / 1024:.1f} MB\n")

# 1. Extraer paradas de SITP (bus_stop)
print("🚌 Extrayendo paradas SITP (bus_stop)...")
cmd_sitp = [
    'ogr2ogr',
    '-f', 'PostgreSQL',
    PG_CONN,
    str(OSM_FILE),
    '-sql', "SELECT * FROM points WHERE amenity='bus_stop'",
    '-nln', 'iug.osm_transport_temp',
    '-lco', 'GEOMETRY_NAME=geom',
    '-lco', 'FID=id',
    '-overwrite'
]

try:
    subprocess.run(cmd_sitp, check=True, capture_output=True, text=True)
    print("   ✅ SITP extraído")
except subprocess.CalledProcessError as e:
    print(f"   ❌ Error: {e.stderr}")

# 2. Extraer vías principales (highways)
print("🛣️  Extrayendo vías principales...")
cmd_roads = [
    'ogr2ogr',
    '-f', 'PostgreSQL',
    PG_CONN,
    str(OSM_FILE),
    '-sql', "SELECT * FROM lines WHERE highway IN ('motorway', 'trunk', 'primary', 'secondary')",
    '-nln', 'iug.osm_main_roads_temp',
    '-lco', 'GEOMETRY_NAME=geom',
    '-lco', 'FID=id',
    '-overwrite'
]

try:
    subprocess.run(cmd_roads, check=True, capture_output=True, text=True)
    print("   ✅ Vías extraídas")
except subprocess.CalledProcessError as e:
    print(f"   ❌ Error: {e.stderr}")

# 3. Extraer parques (leisure=park)
print("🌳 Extrayendo parques...")
cmd_parks = [
    'ogr2ogr',
    '-f', 'PostgreSQL',
    PG_CONN,
    str(OSM_FILE),
    '-sql', "SELECT * FROM multipolygons WHERE leisure='park' OR landuse='recreation_ground'",
    '-nln', 'iug.osm_parks_temp',
    '-lco', 'GEOMETRY_NAME=geom',
    '-lco', 'FID=id',
    '-overwrite'
]

try:
    subprocess.run(cmd_parks, check=True, capture_output=True, text=True)
    print("   ✅ Parques extraídos")
except subprocess.CalledProcessError as e:
    print(f"   ❌ Error: {e.stderr}")

# 4. Mover datos a tablas finales
print("\n📦 Moviendo datos a tablas finales...")
import psycopg2

conn = psycopg2.connect(
    host=os.getenv('PG_HOST', 'localhost'),
    port=int(os.getenv('PG_PORT', '5434')),
    database=os.getenv('PG_DB', 'postgres'),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', 'xd')
)

with conn.cursor() as cur:
    # SITP
    cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
    cur.execute("""
        INSERT INTO iug.osm_transport (type, name, geom)
        SELECT 'bus_stop', name, geom FROM iug.osm_transport_temp;
    """)
    cur.execute("SELECT COUNT(*) FROM iug.osm_transport;")
    count_sitp = cur.fetchone()[0]
    print(f"   ✅ SITP: {count_sitp} paradas")
    
    # Vías
    cur.execute("TRUNCATE iug.osm_main_roads RESTART IDENTITY CASCADE;")
    cur.execute("""
        INSERT INTO iug.osm_main_roads (name, highway, geom)
        SELECT name, highway, geom FROM iug.osm_main_roads_temp;
    """)
    cur.execute("SELECT COUNT(*) FROM iug.osm_main_roads;")
    count_roads = cur.fetchone()[0]
    print(f"   ✅ Vías: {count_roads} segmentos")
    
    # Parques
    cur.execute("TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;")
    cur.execute("""
        INSERT INTO iug.osm_parks (name, geom)
        SELECT name, geom FROM iug.osm_parks_temp;
    """)
    cur.execute("SELECT COUNT(*) FROM iug.osm_parks;")
    count_parks = cur.fetchone()[0]
    print(f"   ✅ Parques: {count_parks} áreas")
    
    # Limpiar tablas temporales
    cur.execute("DROP TABLE IF EXISTS iug.osm_transport_temp;")
    cur.execute("DROP TABLE IF EXISTS iug.osm_main_roads_temp;")
    cur.execute("DROP TABLE IF EXISTS iug.osm_parks_temp;")
    
    conn.commit()

conn.close()

print("\n" + "=" * 70)
print("✅ Extracción OSM completa")
print("=" * 70)
print(f"   🚌 SITP: {count_sitp} paradas")
print(f"   🛣️  Vías: {count_roads} segmentos")
print(f"   🌳 Parques: {count_parks} áreas")
print("=" * 70)
