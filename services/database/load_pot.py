"""
Script para cargar datos POT 555 y catastrales.
"""
import json
import os
import psycopg2
from pathlib import Path

# Support both Docker (relative) and local (absolute) paths
SCRIPT_DIR = Path(__file__).parent
ARCHIVOS_DIR = SCRIPT_DIR / "archivos" / "archivos"
POT_DIR = ARCHIVOS_DIR / "POT 555"
SECTOR_FILE = ARCHIVOS_DIR / "SECTOR.geojson"

def get_connection():
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=int(os.environ.get('PG_PORT', '5434')),
        database=os.environ.get('PG_DB', 'postgres'),
        user=os.environ.get('PG_USER', 'postgres'),
        password=os.environ.get('PG_PASSWORD', 'xd')
    )

def load_json(filepath: Path) -> dict:
    for enc in ['utf-8', 'latin-1', 'cp1252', 'utf-8-sig']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return json.load(f)
        except:
            continue
    return {'features': []}

def get_any_prop(props: dict, *keys):
    for key in keys:
        for k, v in props.items():
            if key.lower() in k.lower() and v:
                return v
    return None


def insert_sectores(conn):
    """Cargar sectores catastrales desde archivo ZIP extraído."""
    print("🗺️ Cargando sectores catastrales...")
    data = load_json(SECTOR_FILE)
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.sector_catastral RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'sector', 'sca')
            codigo = get_any_prop(props, 'codigo', 'scacodigo')
            
            try:
                cur.execute("""
                    INSERT INTO iug.sector_catastral (codigo, nombre, localidad, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(codigo)[:50] if codigo else None,
                    str(nombre)[:300] if nombre else f"Sector {count+1}",
                    str(get_any_prop(props, 'localidad') or '')[:100],
                    geom
                ))
                count += 1
            except Exception as e:
                continue
        
        conn.commit()
        print(f"   ✅ {count} sectores catastrales cargados")


def insert_barrios(conn):
    """Cargar barrios legalizados."""
    print("🏘️ Cargando barrios...")
    filepath = ARCHIVOS_DIR / "barriolegalizado.json"
    if not filepath.exists():
        print(f"   ⚠️ Archivo no encontrado: {filepath}")
        return
    
    data = load_json(filepath)
    print(f"   📁 Archivo cargado con {len(data.get('features', []))} features")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.barrio RESTART IDENTITY CASCADE")
        
        count = 0
        errors = 0
        skipped = 0
        for idx, feature in enumerate(data.get('features', [])):
            props = feature.get('properties', {})
            geom_obj = feature.get('geometry')
            
            # Skip features with null geometry or null geometry type
            if not geom_obj or not geom_obj.get('type'):
                skipped += 1
                continue
            
            geom = json.dumps(geom_obj)
            
            # Get any available name field
            nombre = None
            for k, v in props.items():
                if v and isinstance(v, str) and len(v) > 0:
                    nombre = v
                    break
            
            try:
                cur.execute("""
                    INSERT INTO iug.barrio (codigo, nombre, localidad, tipo, geom)
                    VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(props.get('codigo', props.get('CODIGO', '')))[:50],
                    str(nombre)[:300] if nombre else f"Barrio {count+1}",
                    str(props.get('localidad', props.get('LOCALIDAD', '')))[:100],
                    str(props.get('tipo', props.get('TIPO', props.get('clase', ''))))[:100],
                    geom
                ))
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"   ⚠️ Error en feature {idx}: {e}")
                continue
        
        conn.commit()
        print(f"   ✅ {count} barrios cargados ({errors} errores, {skipped} omitidos)")


def insert_area_actividad(conn):
    """Cargar áreas de actividad POT."""
    print("🏭 Cargando áreas de actividad...")
    filepath = POT_DIR / "areaactividad.json"
    if not filepath.exists():
        print(f"   ⚠️ Archivo no encontrado: {filepath}")
        return
    
    data = load_json(filepath)
    print(f"   📁 Archivo cargado con {len(data.get('features', []))} features")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.area_actividad RESTART IDENTITY CASCADE")
        
        count = 0
        errors = 0
        skipped = 0
        for idx, feature in enumerate(data.get('features', [])):
            props = feature.get('properties', {})
            geom_obj = feature.get('geometry')
            
            # Skip features with null geometry or null geometry type
            if not geom_obj or not geom_obj.get('type'):
                skipped += 1
                continue
            
            geom = json.dumps(geom_obj)
            
            # Get any available name field
            nombre = None
            for k, v in props.items():
                if v and isinstance(v, str) and len(v) > 0:
                    nombre = v
                    break
            
            try:
                cur.execute("""
                    INSERT INTO iug.area_actividad (codigo, nombre, tipo_actividad, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(props.get('codigo', props.get('CODIGO', '')))[:50],
                    str(nombre)[:300] if nombre else f"Area {count+1}",
                    str(props.get('tipo', props.get('TIPO', '')))[:200],
                    geom
                ))
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"   ⚠️ Error en feature {idx}: {e}")
                continue
        
        conn.commit()
        print(f"   ✅ {count} áreas de actividad cargadas ({errors} errores, {skipped} omitidos)")


def insert_tratamiento(conn):
    """Cargar tratamientos urbanísticos POT."""
    print("🏢 Cargando tratamientos urbanísticos...")
    filepath = POT_DIR / "tratamientourbanistico.json"
    if not filepath.exists():
        print(f"   ⚠️ Archivo no encontrado: {filepath}")
        return
    
    data = load_json(filepath)
    print(f"   📁 Archivo cargado con {len(data.get('features', []))} features")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.tratamiento_urbanistico RESTART IDENTITY CASCADE")
        
        count = 0
        errors = 0
        skipped = 0
        for idx, feature in enumerate(data.get('features', [])):
            props = feature.get('properties', {})
            geom_obj = feature.get('geometry')
            
            # Skip features with null geometry or null geometry type
            if not geom_obj or not geom_obj.get('type'):
                skipped += 1
                continue
            
            geom = json.dumps(geom_obj)
            
            # Get any available name field
            nombre = None
            for k, v in props.items():
                if v and isinstance(v, str) and len(v) > 0:
                    nombre = v
                    break
            
            try:
                cur.execute("""
                    INSERT INTO iug.tratamiento_urbanistico (codigo, nombre, tipo, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(props.get('codigo', props.get('CODIGO', '')))[:50],
                    str(nombre)[:300] if nombre else f"Tratamiento {count+1}",
                    str(props.get('tipo', props.get('TIPO', '')))[:200],
                    geom
                ))
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"   ⚠️ Error en feature {idx}: {e}")
                continue
        
        conn.commit()
        print(f"   ✅ {count} tratamientos urbanísticos cargados ({errors} errores, {skipped} omitidos)")


def insert_edificabilidad(conn):
    """Cargar rangos de edificabilidad POT."""
    print("📊 Cargando edificabilidad...")
    filepath = POT_DIR / "rango_edificabilidad_desarro.geojson"
    if not filepath.exists():
        print("   ⚠️ Archivo no encontrado")
        return
    
    data = load_json(filepath)
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.edificabilidad RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            # Intentar extraer rangos numéricos
            rango_min = None
            rango_max = None
            for k, v in props.items():
                kl = k.lower()
                if 'min' in kl:
                    try: rango_min = float(v)
                    except: pass
                elif 'max' in kl:
                    try: rango_max = float(v)
                    except: pass
            
            try:
                cur.execute("""
                    INSERT INTO iug.edificabilidad (codigo, rango_min, rango_max, descripcion, geom)
                    VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(get_any_prop(props, 'codigo', 'rango') or '')[:50],
                    rango_min,
                    rango_max,
                    str(get_any_prop(props, 'descripcion', 'nombre', 'rango') or '')[:500],
                    geom
                ))
                count += 1
            except:
                continue
        
        conn.commit()
        print(f"   ✅ {count} zonas de edificabilidad cargadas")


def main():
    print("=" * 60)
    print("🏗️ CARGA DE DATOS POT 555 Y CATASTRALES")
    print("=" * 60)
    
    conn = get_connection()
    print("✅ Conectado a PostgreSQL\n")
    
    try:
        insert_sectores(conn)
        insert_barrios(conn)
        insert_area_actividad(conn)
        insert_tratamiento(conn)
        insert_edificabilidad(conn)
        
        print("\n" + "=" * 60)
        print("✅ CARGA POT COMPLETADA")
        print("=" * 60)
        
        # Resumen
        with conn.cursor() as cur:
            tables = ['sector_catastral', 'barrio', 'area_actividad', 
                      'tratamiento_urbanistico', 'edificabilidad']
            print("\n📊 RESUMEN POT:")
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM iug.{table}")
                    count = cur.fetchone()[0]
                    print(f"   {table}: {count}")
                except:
                    print(f"   {table}: error")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
