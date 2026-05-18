"""
Cargar shapefile PS ITP usando pyshp (shapefile) - librería Python pura.
"""
import os
import sys
import psycopg2
from pathlib import Path

# Instalar shapefile si no está
try:
    import shapefile
except ImportError:
    print("Instalando pyshp...")
    os.system("pip install pyshp -q")
    import shapefile

PSITP_SHP = Path(__file__).parent / "archivos" / "archivos" / "psitp" / "PSITP.shp"

print("=" * 80)
print("Cargando SITP desde shapefile con pyshp")
print("=" * 80)

if not PSITP_SHP.exists():
    print(f"❌ No encontrado: {PSITP_SHP}")
    sys.exit(1)

print(f"\n📁 Archivo: {PSITP_SHP}")

# Leer shapefile
sf = shapefile.Reader(str(PSITP_SHP))

print(f"📊 Registros en shapefile: {len(sf.shapeRecords()):,}")
print(f"📋 Campos: {[f[0] for f in sf.fields[1:]]}")

# Conectar a PostgreSQL
conn = psycopg2.connect(
    host=os.getenv('PG_HOST', 'localhost'),
    port=int(os.getenv('PG_PORT', '5434')),
    database=os.getenv('PG_DB', 'postgres'),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', 'xd')
)

with conn.cursor() as cur:
    cur.execute("TRUNCATE iug.osm_transport RESTART IDENTITY CASCADE;")
    
    count = 0
    errors = 0
    
    for shaperec in sf.shapeRecords():
        try:
            # Geometría
            shape = shaperec.shape
            if shape.shapeType == 1:  # Point
                lon, lat = shape.points[0]
                
                # Atributos
                record = shaperec.record.as_dict()
                nombre = record.get('NOMBRE') or record.get('nombre') or record.get('codigo') or f'Parada_{count}'
                
                cur.execute("""
                    INSERT INTO iug.osm_transport (type, name, geom)
                    VALUES ('bus_stop', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                """, (nombre[:200], lon, lat))
                count += 1
                
                if count % 1000 == 0:
                    print(f"   Procesadas: {count:,}...")
        except Exception as e:
            errors += 1
            if errors < 10:
                print(f"   Error: {e}")
    
    conn.commit()
    print(f"\n✅ Cargadas: {count:,} paradas SITP")
    if errors > 0:
        print(f"⚠️ Errores: {errors}")

conn.close()

# Verificar
conn = psycopg2.connect(
    host=os.getenv('PG_HOST', 'localhost'),
    port=int(os.getenv('PG_PORT', '5434')),
    database=os.getenv('PG_DB', 'postgres'),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', 'xd')
)

with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM iug.osm_transport WHERE type='bus_stop';")
    final_count =cur.fetchone()[0]
    print(f"\n📊 Total en BD: {final_count:,} paradas SITP")

conn.close()

print("=" * 80)
