"""
Script simple sin dependencias de GDAL - solo psycopg2 y json.
Carga localidades y parques desde archivos existentes.
SITP se carga con Docker GDAL.
"""
import os
import json
import csv
import psycopg2
from pathlib import Path

ARCHIVOS_DIR = Path(__file__).parent / "archijos" / "archivos"

def get_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

print("=" * 70)
print("Cargando datos espaciales (LocalidadesParques)")
print("=" * 70)

# 1. Mover SITP desde tabla temporal (cargada con Docker GDAL)
print("\n🚌 Moviendo paradas SITP...")
conn = get_conn()
with conn.cursor() as cur:
    try:
        cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
        cur.execute("""
            INSERT INTO iug.osm_transport (type, name, geom)
            SELECT 'bus_stop', 
                   COALESCE(nombre, codigo, 'Parada') as name,
                   geom
            FROM iug.psitp_temp;
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM iug.osm_transport;")
        count = cur.fetchone()[0]
        print(f"   ✅ {count} paradas SITP cargadas")
        
        # Limpiar temporal
        cur.execute("DROP TABLE IF EXISTS iug.psitp_temp;")
        conn.commit()
    except Exception as e:
        print(f"   ⚠️ Error con SITP: {e}")
        print("   (Ejecuta primero el comando Docker para cargar PSITP.shp)")

# 2. Cargar localidades desde GeoJSON
print("\n📍 Cargando localidades...")
localidades_file = ARCHIVOS_DIR / "poligonos-localidades.geojson"

if localidades_file.exists():
    with open(localidades_file, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.localidad RESTART IDENTITY CASCADE;")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom_json = json.dumps(feature.get('geometry'))
            
            # Buscar nombre en diferentes campos posibles
            nombre = (props.get('LocNombre') or props.get('nombre') or 
                     props.get('NOMBRE') or props.get('Nombre') or 
                     props.get('localidad') or f'Localidad {count+1}')
            
            try:
                cur.execute("""
                    INSERT INTO iug.localidad (nombre, geom)
                    VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (str(nombre)[:100], geom_json))
                count += 1
            except Exception as e:
                print(f"   ⚠️ Error en localidad: {e}")
        
        conn.commit()
        print(f"   ✅ {count} localidades cargadas")
else:
    print(f"   ⚠️ No se encontró {localidades_file}")

# 3. Cargar parques desde CSV
print("\n🌳 Cargando parques...")
parques_csv = ARCHIVOS_DIR / "espacios_para_deporte_bogota" / "directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv"

if parques_csv.exists():
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;")
        
        count = 0
        with open(parques_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                nombre = row.get('nombre') or row.get('NOMBRE') or row.get('Nombre')
                lat = row.get('latitud') or row.get('LATITUD')
                lon = row.get('longitud') or row.get('LONGITUD')
                
                if lat and lon and nombre:
                    try:
                        lat_f = float(str(lat).replace(',', '.'))
                        lon_f = float(str(lon).replace(',', '.'))
                        
                        cur.execute("""
                            INSERT INTO iug.osm_parks (name, geom)
                            VALUES (%s, ST_Buffer(
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                                50
                            )::geometry)
                        """, (nombre[:200], lon_f, lat_f))
                        count += 1
                    except (ValueError, TypeError) as e:
                        pass
        
        conn.commit()
        print(f"   ✅ {count} parques cargados")
else:
    print(f"   ⚠️ No se encontró {parques_csv}")

# Resumen
print("\n" + "=" * 70)
print("📊 Datos cargados:")
print("=" * 70)

with conn.cursor() as cur:
    cur.execute("""
        SELECT 
            'TransMilenio' as capa, COUNT(*) as registros 
        FROM iug.estacion_transmilenio
        UNION ALL
        SELECT 'SITP', COUNT(*) FROM iug.osm_transport WHERE type='bus_stop'
        UNION ALL
        SELECT 'Localidades', COUNT(*) FROM iug.localidad
        UNION ALL  
        SELECT 'Parques', COUNT(*) FROM iug.osm_parks
    """)
    
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]}")

conn.close()
print("=" * 70)
