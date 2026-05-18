"""
Cargar universidades desde ecosistema_educacion_superior.geojson
"""
import os
import json
import psycopg2
from pathlib import Path

ARCHIVO = Path(__file__).parent.parent / "archivos" / "archivos" / "dotaciones" / "ecosistema_educacion_superior.geojson"

def get_conn():
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn

print("=" * 80)
print("CARGANDO UNIVERSIDADES")
print("=" * 80)

if not ARCHIVO.exists():
    print(f"[ERROR] No encontrado: {ARCHIVO}")
    exit(1)

print(f"\n[FILE] Archivo: {ARCHIVO}")
print(f"[INFO] Tamaño: {ARCHIVO.stat().st_size / 1024 / 1024:.1f} MB")

with open(ARCHIVO, 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])
print(f"[INFO] Features encontradas: {len(features)}")

conn = get_conn()
cur = conn.cursor()

cur.execute("TRUNCATE iug.universidad RESTART IDENTITY CASCADE;")

loaded = 0
errors = 0

for feat in features:
    try:
        props = feat.get('properties', {})
        geom = feat.get('geometry')
        
        if not geom:
            errors += 1
            continue
        
        nombre = (props.get('nombre') or props.get('NOMBRE') or 
                 props.get('name') or props.get('institucion') or f'Universidad_{loaded}')
        tipo = props.get('tipo') or props.get('TIPO') or 'Universidad'
        
        geom_json = json.dumps(geom)
        
        cur.execute("""
            INSERT INTO iug.universidad (nombre, tipo, geom)
            VALUES (%s, %s, ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
        """, (nombre[:200], tipo[:100], geom_json))
        
        loaded += 1
        
    except Exception as e:
        errors += 1
        if errors < 5:
            print(f"   Error: {e}")

cur.close()
conn.close()

print(f"\n[OK] Cargadas: {loaded} universidades")
if errors > 0:
    print(f"[WARNING] Errores: {errors}")

print("=" * 80)
