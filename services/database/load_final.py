"""
Script final para mover datos desde tablas temporales y cargar localidades/parques.
"""
import os
import json
import csv
import psycopg2
from pathlib import Path

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
print("Cargando datos espaciales finales")
print("=" * 70)

conn = get_conn()

# 1. SITP - Mover desde tabla temporal 
print("\n🚌 Procesando SITP...")
with conn.cursor() as cur:
    try:
        cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
        cur.execute("""
            INSERT INTO iug.osm_transport (type, name, geom)
            SELECT 
                'bus_stop',
                COALESCE(nombre, codigo, 'Parada_' || gid::text),
                geom
            FROM iug.psitp_temp;
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM iug.osm_transport;")
        print(f"   ✅ {cur.fetchone()[0]} paradas SITP")
        
        cur.execute("DROP TABLE IF EXISTS iug.psitp_temp CASCADE;")
        conn.commit()
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
        conn.rollback()

# 2. Localidades
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
            
            nombre = None
            for key in ['LocNombre', 'nombre', 'NOMBRE', 'Nombre', 'localidad', 'LOCALIDAD']:
                if key in props and props[key]:
                    nombre = props[key]
                    break
            
            if not nombre:
                nombre = f'Localidad_{count+1}'
            
            try:
                cur.execute("""
                    INSERT INTO iug.localidad (nombre, geom)
                    VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (str(nombre)[:100], geom_json))
                count += 1
            except Exception as e:
                print(f"   Error: {e}")
        
        conn.commit()
        print(f"   ✅ {count} localidades")
else:
    print(f"   ⚠️ No encontrado: {localidades_file}")

# 3. Parques
print("\n🌳 Cargando parques...")
parques_csv = ARCHIVOS_DIR / "espacios_para_deporte_bogota" / "directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv"

if parques_csv.exists():
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;")
        
        count = 0
        with open(parques_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                nombre = None
                for key in ['nombre', 'NOMBRE', 'Nombre']:
                    if key in row and row[key]:
                        nombre = row[key]
                        break
                
                lat = row.get('latitud') or row.get('LATITUD') or row.get('Latitud')
                lon = row.get('longitud') or row.get('LONGITUD') or row.get('Longitud')
                
                if lat and lon:
                    try:
                        lat_f = float(str(lat).replace(',', '.'))
                        lon_f = float(str(lon).replace(',', '.'))
                        
                        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                            cur.execute("""
                                INSERT INTO iug.osm_parks (name, geom)
                                VALUES (%s, ST_Buffer(
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                                    50
                                )::geometry)
                            """, (nombre[:200] if nombre else f'Parque_{count}', lon_f, lat_f))
                            count += 1
                    except (ValueError, TypeError):
                        pass
        
        conn.commit()
        print(f"   ✅ {count} parques")
else:
    print(f"   ⚠️ No encontrado: {parques_csv}")

# Resumen final
print("\n" + "=" * 70)
print("📊 RESUMEN FINAL")
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
        UNION ALL
        SELECT 'Vías', COUNT(*) FROM iug.osm_main_roads
    """)
    
    for row in cur.fetchall():
        icon = {'TransMilenio': '🚇', 'SITP': '🚌', 'Localidades': '📍', 'Parques': '🌳', 'Vías': '🛣️'}.get(row[0], '📁')
        print(f"   {icon} {row[0]}: {row[1]:,} registros")

conn.close()

print("=" * 70)
print("✅ Carga completa")
print("=" * 70)
