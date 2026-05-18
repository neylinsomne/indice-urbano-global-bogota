"""
Extraer vías principales del archivo Bogota.osm.pbf.
Usa ogr2ogr dentro de Docker para filtrar highways principales.
"""
import os
import subprocess
from pathlib import Path

OSM_FILE = Path(__file__).parent.parent / "archivos" / "archivos" / "Bogota.osm.pbf"

print("=" * 80)
print("EXTRAYENDO VÍAS PRINCIPALES DE BOGOTA.OSM.PBF")
print("=" * 80)

if not OSM_FILE.exists():
    print(f"[ERROR] No encontrado: {OSM_FILE}")
    exit(1)

print(f"\n[FILE] Archivo OSM: {OSM_FILE}")
print(f"[INFO] Tamano: {OSM_FILE.stat().st_size / 1024 / 1024:.1f} MB")

# Comando Docker con ogr2ogr
print("\n[VIAS] Extrayendo vias (motorway, trunk, primary, secondary, tertiary)...")

cmd = [
    'docker', 'run', '--rm',
    '--network', 'estudio_inmobiliario_app-network',
    '-v', f'{OSM_FILE.parent.absolute()}:/data',
    'osgeo/gdal:ubuntu-small-latest',  # Imagen más estable
    'ogr2ogr',
    '-f', 'PostgreSQL',
    'PG:host=iug-postgres port=5432 dbname=postgres user=postgres password=xd',
    '/data/Bogota.osm.pbf',
    'lines',  # Capa de líneas en OSM
    '-nln', 'iug.osm_roads_temp',
    '-lco', 'GEOMETRY_NAME=geom',
    '-where', "highway IN ('motorway','trunk','primary','secondary','tertiary','motorway_link','trunk_link','primary_link')",
    '-overwrite',
    '-progress'
]

print(f"\n[RUNNING] Ejecutando ogr2ogr...")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("[OK] Extraccion completada")

    # Mover a tabla final
    print("\n[PROCESSING] Moviendo datos a tabla final...")
    import psycopg2
    
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_main_roads RESTART IDENTITY CASCADE;")
        cur.execute("""
            INSERT INTO iug.osm_main_roads (name, highway, geom)
            SELECT 
                COALESCE(name, 'Via_' || osm_id::text),
                highway,
                geom
            FROM iug.osm_roads_temp;
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM iug.osm_main_roads;")
        count = cur.fetchone()[0]
        print(f"[OK] Cargadas: {count:,} vías principales")
        
        # Limpiar temporal
        cur.execute("DROP TABLE IF EXISTS iug.osm_roads_temp CASCADE;")
        conn.commit()
    
    conn.close()
    
else:
    print(f"[ERROR] Error en ogr2ogr:")
    print(result.stderr)
    print("\n[INFO] Si falla, verifica que Docker tenga acceso al archivo OSM")
    exit(1)

print("\n" + "=" * 80)
print("[OK] Vías principales cargadas desde OSM")
print("=" * 80)
