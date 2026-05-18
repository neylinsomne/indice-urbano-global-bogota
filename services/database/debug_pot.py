"""Debug script for POT data loading."""
from pathlib import Path
import json
import os
import psycopg2

SCRIPT_DIR = Path(__file__).parent
ARCHIVOS_DIR = SCRIPT_DIR / "archivos" / "archivos"
POT_DIR = ARCHIVOS_DIR / "POT 555"

print("=== PATH DEBUG ===")
print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ARCHIVOS_DIR exists: {ARCHIVOS_DIR.exists()}")
print(f"POT_DIR exists: {POT_DIR.exists()}")

if POT_DIR.exists():
    print(f"Files in POT_DIR: {list(POT_DIR.glob('*'))}")

# Test area_actividad file
aa_file = POT_DIR / "areaactividad.json"
print(f"\nareaactividad.json exists: {aa_file.exists()}")
if aa_file.exists():
    with open(aa_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    features = data.get('features', [])
    print(f"Features count: {len(features)}")
    if features:
        print(f"First feature keys: {list(features[0].get('properties', {}).keys())}")

# Test tratamiento file
tu_file = POT_DIR / "tratamientourbanistico.json"
print(f"\ntratamientourbanistico.json exists: {tu_file.exists()}")
if tu_file.exists():
    with open(tu_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    features = data.get('features', [])
    print(f"Features count: {len(features)}")
    if features:
        print(f"First feature keys: {list(features[0].get('properties', {}).keys())}")

# Test barrio file
barrio_file = ARCHIVOS_DIR / "barriolegalizado.json"
print(f"\nbarriolegalizado.json exists: {barrio_file.exists()}")
if barrio_file.exists():
    with open(barrio_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    features = data.get('features', [])
    print(f"Features count: {len(features)}")
    if features:
        print(f"First feature keys: {list(features[0].get('properties', {}).keys())}")

print("\n=== DB TEST ===")
try:
    conn = psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=int(os.environ.get('PG_PORT', '5434')),
        database=os.environ.get('PG_DB', 'postgres'),
        user=os.environ.get('PG_USER', 'postgres'),
        password=os.environ.get('PG_PASSWORD', 'xd')
    )
    print("Connected to database!")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM iug.area_actividad")
        print(f"area_actividad count: {cur.fetchone()[0]}")
    conn.close()
except Exception as e:
    print(f"DB error: {e}")
