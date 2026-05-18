"""Analyze geometry structure in GeoJSON files."""
import json
from pathlib import Path

files_to_check = [
    "/app/archivos/archivos/barriolegalizado.json",
    "/app/archivos/archivos/POT 555/areaactividad.json",
    "/app/archivos/archivos/POT 555/tratamientourbanistico.json",
    "/app/archivos/archivos/SECTOR.geojson"
]

for file_path in files_to_check:
    p = Path(file_path)
    if not p.exists():
        print(f"\n{p.name}: NOT FOUND")
        continue
    
    print(f"\n=== {p.name} ===")
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        try:
            with open(p, 'r', encoding='latin-1') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading: {e}")
            continue
    
    features = data.get('features', [])
    print(f"Total features: {len(features)}")
    
    if features:
        # Check first 3 features
        for i, feat in enumerate(features[:3]):
            geom = feat.get('geometry')
            print(f"\nFeature {i}:")
            print(f"  geometry exists: {geom is not None}")
            if geom:
                print(f"  geometry type: {type(geom)}")
                print(f"  geometry keys: {list(geom.keys()) if isinstance(geom, dict) else 'N/A'}")
                if isinstance(geom, dict):
                    print(f"  'type' value: {geom.get('type')}")
                    coords = geom.get('coordinates')
                    print(f"  'coordinates' exists: {coords is not None}")
                    if coords:
                        print(f"  'coordinates' type: {type(coords)}")
                        print(f"  'coordinates' length: {len(coords) if hasattr(coords, '__len__') else 'N/A'}")
            else:
                print("  geometry is None")
        
        # Count geometry types
        types = {}
        nulls = 0
        empty_types = 0
        empty_coords = 0
        for feat in features:
            geom = feat.get('geometry')
            if geom is None:
                nulls += 1
            elif not isinstance(geom, dict):
                types[str(type(geom))] = types.get(str(type(geom)), 0) + 1
            else:
                t = geom.get('type')
                c = geom.get('coordinates')
                if not t:
                    empty_types += 1
                elif not c:
                    empty_coords += 1
                else:
                    types[t] = types.get(t, 0) + 1
        
        print(f"\nSummary:")
        print(f"  Null geometries: {nulls}")
        print(f"  Empty type: {empty_types}")
        print(f"  Empty coordinates: {empty_coords}")
        print(f"  Valid by type: {types}")
