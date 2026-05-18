"""Analyze barrio GeoJSON structure."""
import json
from pathlib import Path

filepath = Path('/app/archivos/archivos/barriolegalizado.json')
print(f"File exists: {filepath.exists()}")

with open(filepath, 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])
print(f"Total features: {len(features)}")

# Check feature structure
for i, feat in enumerate(features[:5]):
    print(f"\n--- Feature {i} ---")
    print(f"Keys: {list(feat.keys())}")
    if 'geometry' in feat and feat['geometry']:
        print(f"Geometry type: {feat['geometry'].get('type')}")
        print(f"Geometry keys: {list(feat['geometry'].keys())}")
    else:
        print("Geometry: None or empty")
    if 'properties' in feat:
        print(f"Properties keys: {list(feat['properties'].keys())[:10]}")
        print(f"Sample properties: {dict(list(feat['properties'].items())[:5])}")

# Count features with vs without geometry
with_geom = sum(1 for f in features if f.get('geometry'))
without_geom = sum(1 for f in features if not f.get('geometry'))
print(f"\n\nWith geometry: {with_geom}")
print(f"Without geometry: {without_geom}")
