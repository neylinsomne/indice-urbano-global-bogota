"""
Script para cargar TODOS los archivos GeoJSON a PostGIS.
"""
import os
import json
import csv
import psycopg2
from pathlib import Path

ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

def get_connection():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5434'),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

def load_geojson(filepath: Path) -> dict:
    """Load GeoJSON with fallback encoding."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            return json.load(f)

def get_any_prop(props: dict, *keys):
    for key in keys:
        for k, v in props.items():
            if key.lower() in k.lower() and v:
                return v
    return None

def insert_sectores(conn, geojson: dict):
    """Inserta sectores catastrales (archivo grande)."""
    print("🗺️ Cargando sectores catastrales...")
    print("   ⏳ Este archivo es grande, puede tardar unos segundos...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.sector RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'sector')
            codigo = get_any_prop(props, 'codigo', 'sca')
            
            try:
                cur.execute("""
                    INSERT INTO iug.sector (codigo, nombre, localidad, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(codigo)[:50] if codigo else None,
                    str(nombre)[:200] if nombre else f"Sector {count+1}",
                    str(get_any_prop(props, 'localidad') or '')[:100],
                    geom
                ))
                count += 1
            except Exception as e:
                continue
        
        conn.commit()
        print(f"   ✅ {count} sectores cargados")

def insert_cuadrantes(conn, geojson: dict):
    """Inserta cuadrantes de policía."""
    print("👮 Cargando cuadrantes de policía...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.cuadrante_policia RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'cuadrante')
            codigo = get_any_prop(props, 'codigo', 'cua')
            
            try:
                cur.execute("""
                    INSERT INTO iug.cuadrante_policia (codigo, nombre, localidad, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(codigo)[:50] if codigo else None,
                    str(nombre)[:200] if nombre else f"Cuadrante {count+1}",
                    str(get_any_prop(props, 'localidad') or '')[:100],
                    geom
                ))
                count += 1
            except:
                continue
        
        conn.commit()
        print(f"   ✅ {count} cuadrantes cargados")

def insert_upl(conn, geojson: dict):
    """Inserta UPL (Unidades de Planeamiento Local)."""
    print("📐 Cargando UPL...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.upl RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'upl')
            codigo = get_any_prop(props, 'codigo', 'upl')
            
            try:
                cur.execute("""
                    INSERT INTO iug.upl (codigo, nombre, localidad, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(codigo)[:50] if codigo else None,
                    str(nombre)[:200] if nombre else f"UPL {count+1}",
                    str(get_any_prop(props, 'localidad') or '')[:100],
                    geom
                ))
                count += 1
            except:
                continue
        
        conn.commit()
        print(f"   ✅ {count} UPL cargadas")

def insert_centros_comerciales(conn, csv_path: Path):
    """Inserta centros comerciales desde CSV."""
    print("🛒 Cargando centros comerciales...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.centro_comercial RESTART IDENTITY CASCADE")
        
        count = 0
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Buscar lat/lon con diferentes nombres
                lat = None
                lon = None
                nombre = None
                
                for k, v in row.items():
                    kl = k.lower()
                    if 'lat' in kl and v:
                        try: lat = float(v.replace(',', '.'))
                        except: pass
                    elif 'lon' in kl or 'lng' in kl and v:
                        try: lon = float(v.replace(',', '.'))
                        except: pass
                    elif 'nombre' in kl and v:
                        nombre = v
                
                if nombre and lat and lon:
                    try:
                        cur.execute("""
                            INSERT INTO iug.centro_comercial (nombre, direccion, lat, lon, geom)
                            VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                        """, (
                            str(nombre)[:300],
                            str(row.get('direccion', row.get('DIRECCION', '')))[:300],
                            lat, lon, lon, lat
                        ))
                        count += 1
                    except:
                        pass
        
        conn.commit()
        print(f"   ✅ {count} centros comerciales cargados")


def main():
    print("=" * 60)
    print("🗺️ CARGA COMPLETA DE DATOS GEOGRÁFICOS")
    print("=" * 60)
    
    conn = get_connection()
    print("✅ Conectado a PostgreSQL\n")
    
    try:
        # Sectores (archivo grande)
        sectores_file = ARCHIVOS_DIR / "SECTOR.geojson"
        if sectores_file.exists():
            insert_sectores(conn, load_geojson(sectores_file))
        
        # Cuadrantes policía
        cuadrantes_file = ARCHIVOS_DIR / "cuadrantepolicia.geojson"
        if cuadrantes_file.exists():
            insert_cuadrantes(conn, load_geojson(cuadrantes_file))
        
        # UPL
        upl_file = ARCHIVOS_DIR / "unidadplaneamientolocal.json"
        if upl_file.exists():
            insert_upl(conn, load_geojson(upl_file))
        
        # Centros comerciales
        cc_file = ARCHIVOS_DIR / "centro-comercial.csv"
        if cc_file.exists():
            insert_centros_comerciales(conn, cc_file)
        
        print("\n" + "=" * 60)
        print("✅ CARGA ADICIONAL COMPLETADA")
        print("=" * 60)
        
        # Resumen completo
        with conn.cursor() as cur:
            tables = [
                'localidad', 'estacion_transmilenio', 'colegio', 
                'centro_salud', 'universidad', 'sector', 
                'cuadrante_policia', 'upl', 'centro_comercial'
            ]
            print("\n📊 RESUMEN COMPLETO:")
            total = 0
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM iug.{table}")
                    count = cur.fetchone()[0]
                    print(f"   {table}: {count}")
                    total += count
                except:
                    print(f"   {table}: no existe")
            print(f"\n   TOTAL: {total} registros geográficos")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
