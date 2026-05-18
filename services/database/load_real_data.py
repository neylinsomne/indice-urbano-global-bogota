"""
Cargar datos espaciales completos desde archivos existentes.
- SITP: shapefile psitp/PSITP.shp
- Localidades: poligonos-localidades.geojson  
- TransMilenio: ya cargado (149 estaciones)
- Parques: espacios_para_deporte CSV
"""
import os
import json
import csv
import psycopg2
from pathlib import Path
from osgeo import ogr

ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

def get_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

print("=" * 70)
print("Cargando datos espaciales completos")
print("=" * 70)

# 1. Cargar SITP desde shapefile
print("\n🚌 Cargando paradas SITP desde shapefile...")
sitp_shp = ARCHIVOS_DIR / "psitp" / "PSITP.shp"

if not sitp_shp.exists():
    print(f"   ⚠️ No se encontró {sitp_shp}")
else:
    ds = ogr.Open(str(sitp_shp))
    layer = ds.GetLayer(0)
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
        
        count = 0
        for feature in layer:
            geom = feature.GetGeometryRef()
            if geom:
                wkt = geom.ExportToWkt()
                
                # Obtener nombre de parada
                nombre = feature.GetField('NOMBRE') or feature.GetField('NAME') or f'Parada {count}'
                
                cur.execute("""
                    INSERT INTO iug.osm_transport (type, name, geom)
                    VALUES ('bus_stop', %s, ST_SetSRID(ST_GeomFromText(%s), 4326))
                """, (nombre, wkt))
                count += 1
        
        conn.commit()
        print(f"   ✅ {count} paradas SITP cargadas")
    conn.close()
    ds = None

# 2. Cargar localidades desde GeoJSON
print("\n📍 Cargando localidades...")
localidades_file = ARCHIVOS_DIR / "poligonos-localidades.geojson"

if localidades_file.exists():
    with open(localidades_file, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.localidad RESTART IDENTITY CASCADE;")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            # Buscar nombre de localidad
            nombre = props.get('LocNombre') or props.get('nombre') or props.get('NOMBRE')
            
            if nombre:
                cur.execute("""
                    INSERT INTO iug.localidad (nombre, geom)
                    VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (str(nombre)[:100], geom))
                count += 1
        
        conn.commit()
        print(f"   ✅ {count} localidades cargadas")
    conn.close()
else:
    print(f"   ⚠️ No se encontró {localidades_file}")

# 3. Cargar parques desde CSV
print("\n🌳 Cargando parques...")
parques_csv = ARCHIVOS_DIR / "espacios_para_deporte_bogota" / "directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv"

if parques_csv.exists():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;")
        
        count = 0
        with open(parques_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Buscar coordenadas en el CSV
                lat = row.get('latitud') or row.get('LATITUD') or row.get('lat')
                lon = row.get('longitud') or row.get('LONGITUD') or row.get('lon')
                nombre = row.get('nombre') or row.get('NOMBRE') or f'Parque {count}'
                
                if lat and lon:
                    try:
                        lat_f = float(lat.replace(',', '.'))
                        lon_f = float(lon.replace(',', '.'))
                        
                        # Crear buffer pequeño alrededor del punto para simular polígono
                        cur.execute("""
                            INSERT INTO iug.osm_parks (name, geom)
                            VALUES (%s, ST_Buffer(
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                                50  -- 50 metros de radio
                            )::geometry)
                        """, (nombre[:200], lon_f, lat_f))
                        count += 1
                    except (ValueError, TypeError):
                        pass
        
        conn.commit()
        print(f"   ✅ {count} parques cargados")
    conn.close()
else:
    print(f"   ⚠️ No se encontró {parques_csv}")

# Resumen final
print("\n" + "=" * 70)
print("📊 Resumen de datos cargados:")
print("=" * 70)

conn = get_conn()
with conn.cursor() as cur:
    cur.execute("SELECT 'TransMilenio', COUNT(*) FROM iug.estacion_transmilenio")
    tm_count = cur.fetchone()[1]
    
    cur.execute("SELECT 'SITP', COUNT(*) FROM iug.osm_transport WHERE type='bus_stop'")
    sitp_count = cur.fetchone()[1]
    
    cur.execute("SELECT 'Localidades', COUNT(*) FROM iug.localidad")
    loc_count = cur.fetchone()[1]
    
    cur.execute("SELECT 'Parques', COUNT(*) FROM iug.osm_parks")
    parks_count = cur.fetchone()[1]
    
    print(f"   🚇 TransMilenio: {tm_count} estaciones")
    print(f"   🚌 SITP: {sitp_count} paradas")
    print(f"   📍 Localidades: {loc_count} polígonos")
    print(f"   🌳 Parques: {parks_count} áreas")
    print(f"   🛣️ Vías: (pendiente - extraer de OSM)")
    
conn.close()

print("=" * 70)
print("✅ Carga completa")
print("=" * 70)
