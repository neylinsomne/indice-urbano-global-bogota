"""
Cargador completo de datos de seguridad.
Carga DAILoc, sectores priorizados y CAI a PostgreSQL.
"""
import os
import json
import psycopg2
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "archivos" / "archivos"

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

print("=" * 80)
print("CARGANDO DATOS DE SEGURIDAD")
print("=" * 80)

conn = get_conn()

# ===== 1. DAILoc - Delitos por Localidad =====
print("\n1/3 Cargando DAILoc.geojson (Criminalidad por Localidad)...")
dailoc_file = BASE_DIR / "Seguridad" / "DAILoc.geojson"

if dailoc_file.exists():
    with open(dailoc_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"   Features encontradas: {len(features)}")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.criminalidad_localidad RESTART IDENTITY CASCADE;")
        
        loaded = 0
        for feat in features:
            try:
                props = feat.get('properties', {})
                geom = feat.get('geometry')
                
                # Extraer datos
                codigo = props.get('CMIULOCAL', '')
                nombre = props.get('CMNOMLOCAL', '').replace('Ã³', 'ó').replace('Ã±', 'ñ')
                
                # Delitos 2024
                hom = int(props.get('CMH24CONT') or 0)
                sex = int(props.get('CMDS24CONT') or 0)
                hurto = int(props.get('CMHP24CONT') or 0)
                otros = int(props.get('CMVI24CONT') or 0)  # Violencia intrafamiliar como "otros"
                
                if geom and codigo != '99':  # Excluir "Sin Localización"
                    geom_json = json.dumps(geom)
                    
                    cur.execute("""
                        INSERT INTO iug.criminalidad_localidad 
                        (codigo_localidad, nombre_localidad, homicidios_2024, delitos_sexuales_2024, 
                         hurto_personas_2024, otros_delitos_2024, geom)
                        VALUES (%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """, (codigo, nombre, hom, sex, hurto, otros, geom_json))
                    
                    loaded += 1
            except Exception as e:
                print(f"   Error: {e}")
        
        # Calcular masa_crimen con pesos AHP
        cur.execute("""
            UPDATE iug.criminalidad_localidad
            SET masa_crimen = 
                (homicidios_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='homicidios')) +
                (delitos_sexuales_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='delitos_sexuales')) +
                (hurto_personas_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='hurto_personas')) +
                (otros_delitos_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='otros_delitos'))
        """)
        
        print(f"   Cargadas: {loaded} localidades")
        print(f"   Masa de crimen calculada para todas")
else:
    print(f"   No encontrado: {dailoc_file}")

# ===== 2. Sectores Priorizados =====
print("\n2/3 Cargando Sectores Priorizados...")
sector_file = BASE_DIR / "Seguridad" / "sector-priorizado-recuperacion-del-espacio-publico-para-el-cuidado.json"

if sector_file.exists():
    with open(sector_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Detectar estructura (puede ser GeoJSON o formato Esri)
    if 'features' in data:
        features = data['features']
    elif 'rows' in data:
        features = data['rows']
    else:
        features = []
    
    print(f"   Features encontradas: {len(features)}")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.sector_priorizado RESTART IDENTITY CASCADE;")
        
        loaded = 0
        for feat in features:
            try:
                if 'properties' in feat:
                    props = feat['properties']
                    geom = feat.get('geometry')
                elif 'value' in feat:
                    props = feat['value']
                    geom = props.get('shape') or props.get('geometry')
                else:
                    continue
                
                if geom:
                    codigo = str(props.get('codigo') or props.get('CODIGO') or loaded)
                    nombre = str(props.get('nombre') or props.get('NOMBRE') or f'Sector_{loaded}')
                    desc = str(props.get('descripcion') or props.get('DESCRIPCION') or '')
                    
                    geom_json = json.dumps(geom) if isinstance(geom, dict) else geom
                    
                    cur.execute("""
                        INSERT INTO iug.sector_priorizado (codigo, nombre, descripcion, geom)
                        VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """, (codigo[:50], nombre[:200], desc[:500], geom_json))
                    
                    loaded += 1
            except Exception as e:
                if loaded < 5:
                    print(f"   Error: {e}")
        
        print(f"   Cargados: {loaded} sectores priorizados")
else:
    print(f"   No encontrado: {sector_file}")

# =====  3. CAI - Cuadrantes Policía =====
print("\n3/3 Cargando CAI (Cuadrantes de Policía)...")
cai_file = BASE_DIR / "Seguridad" / "cuadrantepolicia.geojson"

if cai_file.exists():
    with open(cai_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])
    print(f"   Features encontradas: {len(features)}")
    
    with conn.cursor() as cur:
        cur.execute("TRUNCATE iug.cai_policia RESTART IDENTITY CASCADE;")
        
        loaded = 0
        for feat in features:
            try:
                props = feat.get('properties', {})
                geom = feat.get('geometry')
                
                # Los cuadrantes son MultiPolygon, extraemos centroide
                if geom and geom.get('type') in ['Polygon', 'MultiPolygon']:
                    codigo = str(props.get('codigo') or props.get('CODIGO') or props.get('COD_CUAD') or '')
                    nombre = str(props.get('nombre') or props.get('NOMBRE') or props.get('NOM_CUAD') or f'CAI_{loaded}')
                    cuadrante = str(props.get('cuadrante') or props.get('CUADRANTE') or props.get('CUAD') or '')
                    direccion = str(props.get('direccion') or props.get('DIRECCION') or props.get('DIR') or '')
                    
                    geom_json = json.dumps(geom)
                    
                    # Insertamos el polígono y luego extraemos el centroide para geom del CAI
                    cur.execute("""
                        INSERT INTO iug.cai_policia (codigo, nombre, cuadrante, direccion, geom)
                        VALUES (%s, %s, %s, %s, ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                    """, (codigo[:50], nombre[:200], cuadrante[:100], direccion, geom_json))
                    
                    loaded += 1
            except Exception as e:
                if loaded < 5:
                    print(f"   Error: {e}")
        
        print(f"   Cargados: {loaded} CAI (centroides de cuadrantes)")
else:
    print(f"   No encontrado: {cai_file}")

# Resumen final
print("\n" + "=" * 80)
print("RESUMEN DE DATOS CARGADOS")
print("=" * 80)

with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM iug.criminalidad_localidad")
    localidades = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM iug.sector_priorizado")
    sectores = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM iug.cai_policia")
    cais = cur.fetchone()[0]
    
    print(f"   Localidades: {localidades}")
    print(f"   Sectores Priorizados: {sectores}")
    print(f"   CAI: {cais}")

conn.close()

print("=" * 80)
print("CARGA COMPLETADA")
print("=" * 80)
