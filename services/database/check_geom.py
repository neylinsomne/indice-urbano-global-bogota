"""Check geometry format in POT files."""
import json
from pathlib import Path

files = [
    '/app/archivos/archivos/POT 555/areaactividad.json',
    '/app/archivos/archivos/POT 555/tratamientourbanistico.json'
]

for fpath in files:
    f = Path(fpath)
    print(f"\n=== {f.name} ===")
    
    try:
        with open(f, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except:
        try:
            with open(f, 'r', encoding='latin-1') as file:
                data = json.load(file)
        except Exception as e:
            print(f"Error: {e}")
            continue
    
    features = data.get('features', [])
    print(f"Total features: {len(features)}")
    
    if features:
        for i in range(min(3, len(features))):
            feat = features[i]
            geom = feat.get('geometry')
            print(f"\nFeature {i}:")
            print(f"  geometry is None: {geom is None}")
            if geom:
                print(f"  type(geometry): {type(geom)}")
                if isinstance(geom, dict):
                    gtype = geom.get('type')
                    print(f"  geometry.type: {gtype}")
                    print(f"  geometry keys: {list(geom.keys())}")
                    coords = geom.get('coordinates')
                    if coords:
                        print(f"  coordinates type: {type(coords)}")
                        print(f"  coordinates length: {len(coords) if hasattr(coords, '__len__') else 'N/A'}")
                else:
                    print(f"  geometry value: {str(geom)[:200]}")
