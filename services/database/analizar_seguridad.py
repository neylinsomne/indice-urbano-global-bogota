"""
Analizar archivos de seguridad para entender su estructura.
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "archivos" / "archivos"

print("=" * 80)
print("ANÁLISIS DE ARCHIVOS DE SEGURIDAD")
print("=" * 80)

# 1. DAILoc - Delitos por Localidad
dai_file = BASE / "Seguridad" / "DAILoc.geojson"
if dai_file.exists():
    print("\n📊 1. DAILoc.geojson (Delitos por Localidad)")
    print(f"   Tamaño: {dai_file.stat().st_size / 1024:.1f} KB")
    
    with open(dai_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"   Features: {len(features)}")
    
    if features:
        first_props = features[0].get('properties', {})
        print(f"\n   Campos disponibles:")
        for key in sorted(first_props.keys()):
            value = first_props[key]
            print(f"      • {key}: {value} (tipo: {type(value).__name__})")

# 2. Sector Priorizado
sector_file = BASE / "Seguridad" / "sector-priorizado-recuperacion-del-espacio-publico-para-el-cuidado.json"
if sector_file.exists():
    print("\n\n🚨 2. Sectores Priorizados")
    print(f"   Tamaño: {sector_file.stat().st_size / 1024:.1f} KB")
    
    with open(sector_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Detectar estructura
    if 'features' in data:
        features = data['features']
    elif 'rows' in data:
        features = data['rows']
    else:
        features = []
    
    print(f"   Features: {len(features)}")
    
    if features:
        first = features[0]
        if 'properties' in first:
            props = first['properties']
        elif 'value' in first:
            props = first.get('value', {})
        else:
            props = first
            
        print(f"\n   Campos disponibles:")
        for key in sorted(props.keys())[:15]:  # Primeros 15
            value = props.get(key)
            print(f"      • {key}: {str(value)[:50]}")

# 3. Cuadrantes Policía
cuad_file = BASE / "cuadrantepolicia.geojson"
if cuad_file.exists():
    print("\n\n👮 3. Cuadrantes Policía (CAI)")
    print(f"   Tamaño: {cuad_file.stat().st_size / 1024:.1f} KB")
    
    with open(cuad_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"   Features: {len(features)}")
    
    if features:
        first_props = features[0].get('properties', {})
        print(f"\n   Campos disponibles:")
        for key in sorted(first_props.keys()):
            value = first_props[key]
            print(f"      • {key}: {str(value)[:50]}")

print("\n" + "=" * 80)
