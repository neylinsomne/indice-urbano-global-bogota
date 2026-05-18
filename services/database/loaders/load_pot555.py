"""
Cargador de datos POT 555 (Plan de Ordenamiento Territorial).
Carga 4 capas críticas para análisis de permisos de construcción.
"""
import os
import json
import psycopg2
from pathlib import Path
import sys

POT_DIR = Path(__file__).parent.parent / "archivos" / "archivos" / "POT 555"
# Fallback: buscar en normativa_pot si POT 555 no existe
POT_DIR_ALT = Path(__file__).parent.parent / "archivos" / "normativa_pot"

# CRS CarMAGBOG (usado por archivos POT de Bogotá)
CARMAGBOG_SRID = 900001
CARMAGBOG_PROJ4 = (
    "+proj=tmerc +lat_0=4.680486111 +lon_0=-74.14659167 +k=1.0 "
    "+x_0=92334.879 +y_0=109320.965 +ellps=GRS80 +a=6380687.0 "
    "+rf=298.257222101 +units=m +no_defs"
)
CARMAGBOG_SRTEXT = (
    'PROJCS["PCS_CarMAGBOG",GEOGCS["GCS_CarMAGBOG",'
    'DATUM["CGS_CarMAGBOG",SPHEROID["GRS80_Mod",6380687.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",92334.879],'
    'PARAMETER["False_Northing",109320.965],'
    'PARAMETER["Central_Meridian",-74.14659167],'
    'PARAMETER["Scale_Factor",1.0],'
    'PARAMETER["Latitude_Of_Origin",4.680486111],'
    'UNIT["Meter",1.0]]'
)


def _is_carmagbog(data):
    """Detecta si las coordenadas están en CarMAGBOG (valores grandes >1000)."""
    sr = data.get('spatialReference', {})
    wkt = sr.get('wkt', '')
    if 'CarMAGBOG' in wkt:
        return True
    # Heurística: revisar primera coordenada
    feats = data.get('features', [])
    if feats:
        geom = feats[0].get('geometry', {})
        rings = geom.get('rings', geom.get('coordinates', []))
        if rings and isinstance(rings[0], list):
            coord = rings[0][0] if isinstance(rings[0][0], list) else rings[0]
            if len(coord) >= 2 and abs(coord[0]) > 1000:
                return True
    return False


def _ensure_carmagbog_srid(conn):
    """Registra el CRS CarMAGBOG en spatial_ref_sys si no existe."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (CARMAGBOG_SRID,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext) "
            "VALUES (%s, 'CUSTOM', %s, %s, %s)",
            (CARMAGBOG_SRID, CARMAGBOG_SRID, CARMAGBOG_PROJ4, CARMAGBOG_SRTEXT)
        )
        print("   [CRS] CarMAGBOG (SRID 900001) registrado")
    cur.close()


def get_conn():
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn

def esri_to_geojson_geometry(esri_geom):
    """Convierte geometría Esri a GeoJSON estándar."""
    if not esri_geom:
        return None

    # Si ya es GeoJSON estándar (tiene 'type'), retornar tal cual
    if 'type' in esri_geom:
        return esri_geom

    # Convertir Esri Polygon a GeoJSON Polygon
    if 'rings' in esri_geom:
        return {
            'type': 'Polygon',
            'coordinates': esri_geom['rings']
        }

    # Convertir Esri Point a GeoJSON Point
    if 'x' in esri_geom and 'y' in esri_geom:
        return {
            'type': 'Point',
            'coordinates': [esri_geom['x'], esri_geom['y']]
        }

    # Otros tipos Esri
    if 'paths' in esri_geom:
        return {
            'type': 'LineString' if len(esri_geom['paths']) == 1 else 'MultiLineString',
            'coordinates': esri_geom['paths'][0] if len(esri_geom['paths']) == 1 else esri_geom['paths']
        }

    return esri_geom

def load_json_layer(filename, table_name, geom_field='geometry', name_field='nombre'):
    """Carga un archivo JSON/GeoJSON a PostgreSQL con detección automática de CRS."""
    filepath = POT_DIR / filename

    if not filepath.exists():
        filepath = POT_DIR_ALT / filename
        if not filepath.exists():
            print(f"   [WARNING] No encontrado: {filename}")
            return 0

    print(f"   [LOADING] Cargando {filename} ({filepath.stat().st_size / 1024 / 1024:.1f} MB)...")

    with open(filepath, 'r', encoding='utf-8') as fi:
        data = json.load(fi)

    # Detectar formato
    if 'features' in data:  # GeoJSON o Esri FeatureSet
        features = data['features']
    elif 'rows' in data:  # Formato Esri alternativo
        features = data['rows']
    else:
        features = data if isinstance(data, list) else [data]

    print(f"   [INFO] Features encontradas: {len(features)}")

    conn = get_conn()
    cur = conn.cursor()

    # Detectar si los datos están en CarMAGBOG
    is_carmagbog = _is_carmagbog(data)
    if is_carmagbog:
        _ensure_carmagbog_srid(conn)
        print(f"   [CRS] Detectado CarMAGBOG → se transformará a WGS84")
        # SQL para insertar con transformación
        geom_sql = f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), {CARMAGBOG_SRID}), 4326)"
    else:
        geom_sql = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"

    try:
        cur.execute(f"TRUNCATE iug.{table_name} RESTART IDENTITY CASCADE;")

        count = 0
        errors = 0

        for feat in features:
            try:
                # Extraer propiedades y geometría (soportar formato Esri y GeoJSON)
                if 'attributes' in feat:  # Formato Esri FeatureSet
                    props = feat.get('attributes', {})
                    esri_geom = feat.get('geometry')
                    geom = esri_to_geojson_geometry(esri_geom)
                elif 'properties' in feat:  # GeoJSON estándar
                    props = feat.get('properties', {})
                    geom = feat.get('geometry')
                elif 'value' in feat:  # Formato Esri antiguo
                    props = feat.get('value', {})
                    geom = props.get(geom_field) or props.get('shape')
                else:
                    props = feat
                    geom = feat.get(geom_field) or feat.get('geometry')

                if not geom:
                    errors += 1
                    continue
                
                # Convertir geometría a GeoJSON string
                geom_json = json.dumps(geom) if isinstance(geom, dict) else geom

                # Insertar según tabla con campos específicos de formato Esri
                if table_name == 'pot_area_actividad':
                    codigo = props.get('CODIGO_AREA_ACTIVIDAD') or props.get('codigo') or ''
                    nombre = props.get('NOMBRE_AREA_ACTIVIDAD') or props.get('nombre') or codigo
                    normativa = props.get('NORMATIVA') or ''
                    descripcion = props.get('OBSERVACION') or ''
                    cur.execute(f"""
                        INSERT INTO iug.pot_area_actividad (codigo, nombre, descripcion, normativa, geom)
                        VALUES (%s, %s, %s, %s, {geom_sql})
                    """, (str(codigo)[:50], str(nombre)[:200], str(descripcion)[:500],
                          str(normativa)[:500], geom_json))

                elif table_name == 'pot_tratamiento':
                    codigo = props.get('CODIGO_TRATAMIENTO') or props.get('codigo') or ''
                    nombre = props.get('NOMBRE_TRATAMIENTO') or props.get('nombre') or codigo
                    tipo = props.get('TIPOLOGIA') or props.get('tipo') or ''
                    descripcion = props.get('NORMATIVA') or props.get('descripcion') or ''
                    cur.execute(f"""
                        INSERT INTO iug.pot_tratamiento (codigo, nombre, tipo, descripcion, geom)
                        VALUES (%s, %s, %s, %s, {geom_sql})
                    """, (str(codigo)[:50], str(nombre)[:200], str(tipo)[:100],
                          str(descripcion)[:500], geom_json))

                elif table_name == 'pot_edificabilidad':
                    codigo = props.get('codigo') or props.get('CODIGO') or ''
                    rango = props.get('rango') or props.get('RANGO') or props.get('edificabilidad') or ''
                    descripcion = props.get('descripcion') or props.get('DESCRIPCION') or ''
                    pisos_min, pisos_max = None, None
                    cur.execute(f"""
                        INSERT INTO iug.pot_edificabilidad (codigo, rango, pisos_min, pisos_max, descripcion, geom)
                        VALUES (%s, %s, %s, %s, %s, {geom_sql})
                    """, (str(codigo)[:50], str(rango)[:100], pisos_min, pisos_max,
                          str(descripcion)[:500], geom_json))

                elif table_name == 'pot_upl':
                    codigo = props.get('CODIGO_UPL') or props.get('codigo') or ''
                    nombre = props.get('NOMBRE') or props.get('nombre') or codigo
                    localidad = props.get('SECTOR') or props.get('localidad') or ''
                    estado = props.get('VOCACION') or props.get('estado') or ''
                    descripcion = props.get('NORMATIVA') or ''
                    cur.execute(f"""
                        INSERT INTO iug.pot_upl (codigo, nombre, localidad, estado, descripcion, geom)
                        VALUES (%s, %s, %s, %s, %s, {geom_sql})
                    """, (str(codigo)[:50], str(nombre)[:200], str(localidad)[:100],
                          str(estado)[:50], str(descripcion)[:500], geom_json))
                
                count += 1
                if count % 1000 == 0:
                    print(f"     Procesados: {count:,}...")
                    
            except Exception as e:
                errors += 1
                if errors < 5:
                    print(f"     Error: {str(e)[:100]}")
        
        print(f"   [OK] Cargados: {count:,} registros")
        if errors > 0:
            print(f"   [WARNING] Errores: {errors}")
    
    finally:
        cur.close()
        conn.close()
    
    return count

def load_all_pot():
    """Carga todas las capas POT 555."""
    print("=" * 80)
    print("CARGANDO DATOS POT 555 (Plan de Ordenamiento Territorial)")
    print("=" * 80)
    
    if not POT_DIR.exists() and not POT_DIR_ALT.exists():
        print(f"[ERROR] Directorio no encontrado: {POT_DIR} ni {POT_DIR_ALT}")
        return False

    results = {}

    print("\n[1/4] Area de Actividad (Zonificacion)...")
    results['area_actividad'] = load_json_layer('areaactividad.json', 'pot_area_actividad')

    print("\n[2/4] Tratamiento Urbanistico...")
    results['tratamiento'] = load_json_layer('tratamientourbanistico.json', 'pot_tratamiento', name_field='TRATAMIENTO')

    print("\n[3/4] Edificabilidad (Pisos Maximos)...")
    results['edificabilidad'] = load_json_layer('rango_edificabilidad_desarro.geojson', 'pot_edificabilidad')

    print("\n[4/4] Unidades de Planeamiento Local...")
    results['upl'] = load_json_layer('unidadplaneamientolocal.json', 'pot_upl')

    # Resumen
    print("\n" + "=" * 80)
    print("[RESUMEN] RESUMEN POT 555")
    print("=" * 80)
    for key, count in results.items():
        print(f"   {key}: {count:,} registros")
    
    total = sum(results.values())
    print(f"\n   Total: {total:,} registros POT cargados")
    print("=" * 80)
    
    return total > 0

if __name__ == '__main__':
    success = load_all_pot()
    sys.exit(0 if success else 1)
