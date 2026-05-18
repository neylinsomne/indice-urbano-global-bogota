"""
Script para cargar archivos GeoJSON a PostGIS.
Uso: python load_geojson.py
"""
import os
import json
import psycopg2
from pathlib import Path

# Configuración
ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

# Conexión PostgreSQL
def get_connection():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

def load_geojson(filepath: Path) -> dict:
    """Carga un archivo GeoJSON."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_any_prop(props: dict, *keys):
    """Busca un valor en cualquiera de las claves proporcionadas."""
    for key in keys:
        for k, v in props.items():
            if key.lower() in k.lower() and v:
                return v
    return None

def insert_localidades(conn, geojson: dict):
    """Inserta localidades."""
    print("📍 Cargando localidades...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.localidad RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            # Buscar nombre en cualquier campo que contenga 'nombre'
            nombre = get_any_prop(props, 'nombre', 'localidad')
            if not nombre:
                # Intentar con el primer valor que parezca un nombre
                for v in props.values():
                    if isinstance(v, str) and len(v) > 2 and v[0].isupper():
                        nombre = v
                        break
            
            if nombre:
                cur.execute("""
                    INSERT INTO iug.localidad (nombre, geom)
                    VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (str(nombre)[:100], geom))
                count += 1
        
        conn.commit()
        print(f"   ✅ {count} localidades cargadas")

def insert_estaciones_tm(conn, geojson: dict):
    """Inserta estaciones de TransMilenio."""
    print("🚌 Cargando estaciones TransMilenio...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.estacion_transmilenio RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'estacion', 'portal')
            if not nombre:
                for v in props.values():
                    if isinstance(v, str) and len(v) > 2:
                        nombre = v
                        break
            
            if nombre:
                cur.execute("""
                    INSERT INTO iug.estacion_transmilenio (nombre, troncal, geom)
                    VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """, (
                    str(nombre)[:200],
                    str(get_any_prop(props, 'troncal', 'linea') or '')[:100],
                    geom
                ))
                count += 1
        
        conn.commit()
        print(f"   ✅ {count} estaciones cargadas")

def insert_colegios(conn, geojson: dict):
    """Inserta colegios."""
    print("🏫 Cargando colegios...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.colegio RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'colegio', 'sede', 'institucion')
            
            if nombre:
                try:
                    cur.execute("""
                        INSERT INTO iug.colegio (nombre, tipo, localidad, direccion, geom)
                        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """, (
                        str(nombre)[:300],
                        str(get_any_prop(props, 'tipo', 'sector', 'naturaleza') or '')[:100],
                        str(get_any_prop(props, 'localidad') or '')[:100],
                        str(get_any_prop(props, 'direccion', 'dir') or '')[:300],
                        geom
                    ))
                    count += 1
                except:
                    pass
        
        conn.commit()
        print(f"   ✅ {count} colegios cargados")

def insert_salud(conn, geojson: dict):
    """Inserta centros de salud."""
    print("🏥 Cargando centros de salud...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.centro_salud RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'razon', 'prestador', 'ips')
            
            if nombre:
                try:
                    cur.execute("""
                        INSERT INTO iug.centro_salud (nombre, tipo, localidad, direccion, geom)
                        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """, (
                        str(nombre)[:300],
                        str(get_any_prop(props, 'tipo', 'nivel') or '')[:100],
                        str(get_any_prop(props, 'localidad') or '')[:100],
                        str(get_any_prop(props, 'direccion', 'dir') or '')[:300],
                        geom
                    ))
                    count += 1
                except:
                    pass
        
        conn.commit()
        print(f"   ✅ {count} centros de salud cargados")

def insert_universidades(conn, geojson: dict):
    """Inserta universidades."""
    print("🎓 Cargando universidades...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.universidad RESTART IDENTITY CASCADE")
        
        count = 0
        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = json.dumps(feature.get('geometry'))
            
            nombre = get_any_prop(props, 'nombre', 'ies', 'universidad', 'institucion')
            
            if nombre:
                try:
                    cur.execute("""
                        INSERT INTO iug.universidad (nombre, tipo, localidad, direccion, geom)
                        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """, (
                        str(nombre)[:300],
                        str(get_any_prop(props, 'tipo', 'caracter', 'naturaleza') or '')[:100],
                        str(get_any_prop(props, 'localidad') or '')[:100],
                        str(get_any_prop(props, 'direccion', 'dir') or '')[:300],
                        geom
                    ))
                    count += 1
                except:
                    pass
        
        conn.commit()
        print(f"   ✅ {count} universidades cargadas")


def main():
    print("=" * 60)
    print("🗺️ CARGA DE DATOS GEOGRÁFICOS A POSTGIS")
    print("=" * 60)
    
    conn = get_connection()
    print("✅ Conectado a PostgreSQL\n")
    
    try:
        # Localidades
        localidades_file = ARCHIVOS_DIR / "poligonos-localidades.geojson"
        if localidades_file.exists():
            insert_localidades(conn, load_geojson(localidades_file))
        
        # Estaciones TransMilenio
        tm_file = ARCHIVOS_DIR / "Estaciones_Troncales_de_TRANSMILENIO.geojson"
        if tm_file.exists():
            insert_estaciones_tm(conn, load_geojson(tm_file))
        
        # Colegios
        colegios_file = ARCHIVOS_DIR / "colegios12_2024.geojson"
        if colegios_file.exists():
            insert_colegios(conn, load_geojson(colegios_file))
        
        # Salud
        salud_file = ARCHIVOS_DIR / "salud.geojson"
        if salud_file.exists():
            insert_salud(conn, load_geojson(salud_file))
        
        # Universidades
        uni_file = ARCHIVOS_DIR / "ecosistema_educacion_superior.geojson"
        if uni_file.exists():
            insert_universidades(conn, load_geojson(uni_file))
        
        print("\n" + "=" * 60)
        print("✅ CARGA COMPLETADA")
        print("=" * 60)
        
        # Resumen
        with conn.cursor() as cur:
            tables = ['localidad', 'estacion_transmilenio', 'colegio', 'centro_salud', 'universidad']
            print("\n📊 RESUMEN:")
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM iug.{table}")
                    count = cur.fetchone()[0]
                    print(f"   {table}: {count} registros")
                except:
                    print(f"   {table}: tabla no existe")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
