"""
⚠️ DEPRECADO: Este script ha sido reemplazado por orquestador_carga.py

Script SOLO para cargar datos desde archivos.
No calcula scores, solo carga los vectores espaciales.

USAR EN SU LUGAR:
    python orquestador_carga.py

El nuevo orquestador integra:
- Verificación de tablas vacías
- Carga de dotaciones (5 categorías)
- Mejor manejo de errores
- Integración con GitHub Actions
"""
import os
import json
import csv
import warnings
import psycopg2
from pathlib import Path

# Advertencia de deprecación
warnings.warn(
    "cargar_datos.py está deprecado. Usar orquestador_carga.py en su lugar.",
    DeprecationWarning,
    stacklevel=2
)

ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

def get_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

print("=" * 80)
print("CARGANDO DATOS ESPACIALES DESDE ARCHIVOS")
print("=" * 80)

conn = get_conn()

# 1. SITP - desde tabla temporal cargada con ogr2ogr
print("\n🚌 SITP (desde shapefile PSITP.shp)...")
with conn.cursor() as cur:
    try:
        # Verificar que existe la tabla temporal
        cur.execute("SELECT COUNT(*) FROM iug.psitp_temp;")
        temp_count = cur.fetchone()[0]
        print(f"   Tabla temporal: {temp_count:,} registros")
        
        # Limpiar y mover
        cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
        cur.execute("""
            INSERT INTO iug.osm_transport (type, name, geom)
            SELECT 
                'bus_stop',
                COALESCE(nombre, codigo, 'Paradatgid::text),
                geom
            FROM iug.psitp_temp;
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM iug.osm_transport;")
        final_count = cur.fetchone()[0]
        print(f"   ✅ Cargadas: {final_count:,} paradas SITP")
        
        # Limpiar temporal
        cur.execute("DROP TABLE IF EXISTS iug.psitp_temp CASCADE;")
        conn.commit()
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
        print("   Asegúrate de ejecutar primero el comando Docker con ogr2ogr")
        conn.rollback()

# 2. Localidades - desde poligonos-localidades.geojson
print("\n📍 Localidades (desde poligonos-localidades.geojson)...")
localidades_file = ARCHIVOS_DIR / "poligonos-localidades.geojson"

if localidades_file.exists():
    print(f"   Archivo: {localidades_file}")
    print(f"   Tamaño: {localidades_file.stat().st_size / 1024:.1f} KB")
    
    with open(localidades_file, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    
    total_features = len(geojson.get('features', []))
    print(f"   Features en GeoJSON: {total_features}")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.localidad RESTART IDENTITY CASCADE;")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom_json = json.dumps(feature.get('geometry'))
            
            # Buscar nombre
            nombre = None
            for key in ['LocNombre', 'nombre', 'NOMBRE', 'Nombre', 'localidad']:
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
                print(f"   Error en feature: {e}")
        
        conn.commit()
        print(f"   ✅ Cargadas: {count} localidades")
else:
    print(f"   ❌ No encontrado: {localidades_file}")

# 3. Parques - desde CSV
print("\n🌳 Parques (desde CSV)...")
parques_csv = ARCHIVOS_DIR / "espacios_para_deporte_bogota" / "directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv"

if parques_csv.exists():
    print(f"   Archivo: {parques_csv}")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.osm_parks RESTART IDENTITY CASCADE;")
        
        count = 0
        errors = 0
        with open(parques_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for i, row in enumerate(reader):
                nombre = row.get('nombre') or row.get('NOMBRE')
                lat = row.get('latitud') or row.get('LATITUD')
                lon = row.get('longitud') or row.get('LONGITUD')
                
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
                    except (ValueError, TypeError) as e:
                        errors += 1
        
        conn.commit()
        print(f"   ✅ Cargados: {count} parques")
        if errors > 0:
            print(f"   ⚠️ Errores: {errors}")
else:
    print(f"   ❌ No encontrado: {parques_csv}")

# RESUMEN FINAL
print("\n" + "=" * 80)
print("📊 DATOS CARGADOS EN LA BASE DE DATOS")
print("=" * 80)

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
    
    results = cur.fetchall()
    for row in results:
        icon = {
            'TransMilenio': '🚇',
            'SITP': '🚌', 
            'Localidades': '📍',
            'Parques': '🌳',
            'Vías': '🛣️'
        }.get(row[0], '📁')
        print(f"   {icon} {row[0]}: {row[1]:,} registros")

conn.close()

print("=" * 80)
print("✅ Carga de datos completada")
print("=" * 80)
