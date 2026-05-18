"""Test single barrio insert to debug issue."""
from pathlib import Path
import json
import os
import psycopg2

SCRIPT_DIR = Path(__file__).parent
ARCHIVOS_DIR = SCRIPT_DIR / "archivos" / "archivos"

filepath = ARCHIVOS_DIR / "barriolegalizado.json"
print(f"File exists: {filepath.exists()}")

if filepath.exists():
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"Total features: {len(features)}")
    
    if features:
        # Show first feature structure
        first = features[0]
        print(f"\nFirst feature keys: {list(first.keys())}")
        print(f"Properties: {first.get('properties', {})}")
        print(f"Geometry type: {first.get('geometry', {}).get('type')}")
        
        # Try to insert just the first one
        conn = psycopg2.connect(
            host=os.environ.get('PG_HOST', 'localhost'),
            port=int(os.environ.get('PG_PORT', '5434')),
            database='postgres',
            user='postgres',
            password=os.environ.get('PG_PASSWORD', 'xd')
        )
        print("\nConnected to database!")
        
        props = first.get('properties', {})
        geom = json.dumps(first.get('geometry'))
        
        nombre = None
        for k, v in props.items():
            if v and isinstance(v, str) and len(v) > 0:
                nombre = v
                break
        
        print(f"Using nombre: {nombre}")
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO iug.barrio (codigo, nombre, localidad, tipo, geom)
                    VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(props.get('codigo', props.get('CODIGO', '')))[:50],
                    str(nombre)[:300] if nombre else "Barrio 1",
                    str(props.get('localidad', props.get('LOCALIDAD', '')))[:100],
                    str(props.get('tipo', props.get('TIPO', props.get('clase', ''))))[:100],
                    geom
                ))
                conn.commit()
                print("INSERT SUCCESSFUL!")
        except Exception as e:
            print(f"INSERT FAILED: {e}")
        
        conn.close()
