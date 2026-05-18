"""
Script para analizar y listar todos los archivos espaciales disponibles.
Genera un inventario con nombres, tamaños y estado de carga.
"""
import os
from pathlib import Path
import json

ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

print("=" * 90)
print("INVENTARIO DE ARCHIVOS ESPACIALES")
print("=" * 90)

# Archivos esperados y su estado
archivos = {
    "CARGADOS": [],
    "PENDIENTES": [],
    "OTROS": []
}

# Recorrer directorio
for item in sorted(ARCHIVOS_DIR.iterdir()):
    if item.is_file():
        size_mb = item.stat().st_size / (1024 * 1024)
        ext = item.suffix.lower()
        
        # Clasificar
        if item.name in [
            'Estaciones_Troncales_de_TRANSMILENIO.geojson',
            'poligonos-localidades.geojson'
        ]:
            archivos["CARGADOS"].append((item.name, size_mb, ext))
        elif ext in ['.geojson', '.json', '.csv', '.pbf', '.gdb']:
            archivos["PENDIENTES"].append((item.name, size_mb, ext))
        else:
            archivos["OTROS"].append((item.name, size_mb, ext))
    else:
        # Es directorio
        if item.name == 'psitp':
            archivos["CARGADOS"].append((f"📁 {item.name}/", "-", "shp"))
        elif item.name == 'POT 555':
            archivos["PENDIENTES"].append((f"📁 {item.name}/", "-", "json/geojson"))
        else:
            archivos["OTROS"].append((f"📁 {item.name}/", "-", "dir"))

# Mostrar inventario
print("\n✅ ARCHIVOS CARGADOS")
print("-" * 90)
for nombre, size, ext in archivos["CARGADOS"]:
    size_str = f"{size:.1f} MB" if size != "-" else size
    print(f"  {nombre:<60} {size_str:>10} {ext:>10}")

print("\n⏳ ARCHIVOS PENDIENTES")
print("-" * 90)
for nombre, size, ext in archivos["PENDIENTES"]:
    size_str = f"{size:.1f} MB" if size != "-" else size
    print(f"  {nombre:<60} {size_str:>10} {ext:>10}")

print("\n📦 OTROS ARCHIVOS")
print("-" * 90)
for nombre, size, ext in archivos["OTROS"]:
    size_str = f"{size:.1f} MB" if size != "-" else size  
    print(f"  {nombre:<60} {size_str:>10} {ext:>10}")

print("\n" + "=" * 90)
print("RESUMEN")
print("=" * 90)
print(f"  ✅ Cargados:   {len(archivos['CARGADOS'])}")
print(f"  ⏳ Pendientes: {len(archivos['PENDIENTES'])}")
print(f"  📦 Otros:      {len(archivos['OTROS'])}")
print(f"  📊 Total:      {len(archivos['CARGADOS']) + len(archivos['PENDIENTES']) + len(archivos['OTROS'])}")
print("=" * 90)

# Analizar archivos POT 555
print("\n📋 DETALLE: POT 555")
print("-" * 90)
pot_dir = ARCHIVOS_DIR / "POT 555"
if pot_dir.exists():
    for f in sorted(pot_dir.iterdir()):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name:<50} {size_mb:>8.1f} MB")
