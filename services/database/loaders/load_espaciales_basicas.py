"""
Cargador de Capas Espaciales Básicas

Carga datos geográficos fundamentales:
1. Localidades de Bogotá (20 polígonos)
2. Paradas SITP (shapefile)
3. Parques IDRD (CSV)

Uso:
    python load_espaciales_basicas.py

O como parte del orquestador.
"""
import os
import json
import csv
import sys
import psycopg2
from pathlib import Path

# Directorios base
BASE_DIR = Path(__file__).parent.parent
ARCHIVOS_DIR = BASE_DIR / "archivos" / "archivos"

def get_conn():
    """Conexión a PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

def check_table_empty(conn, table_name, schema='iug'):
    """Verifica si una tabla está vacía"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table_name}")
        return cur.fetchone()[0] == 0

def load_localidades(conn):
    """Carga localidades desde poligonos-localidades.geojson"""
    print("\n[LOCALIDADES] Localidades (desde poligonos-localidades.geojson)...")
    localidades_file = ARCHIVOS_DIR / "poligonos-localidades.geojson"

    if not localidades_file.exists():
        print(f"   [ERROR] No encontrado: {localidades_file}")
        return 0

    print(f"   Archivo: {localidades_file.name}")
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

            # Buscar nombre en varios campos posibles
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
        print(f"   [OK] Cargadas: {count} localidades")

    return count

def load_sitp(conn):
    """Carga paradas SITP desde shapefile"""
    print("\n[SITP] SITP (desde shapefile PSITP.shp)...")

    # Intentar usar pyshp
    try:
        import shapefile
    except ImportError:
        print("   [WARNING] pyshp no instalado, intentando instalar...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "pyshp", "-q"], check=False)
        try:
            import shapefile
        except ImportError:
            print("   [ERROR] No se pudo instalar pyshp, omitiendo carga de SITP")
            return 0

    psitp_shp = ARCHIVOS_DIR / "psitp" / "PSITP.shp"

    if not psitp_shp.exists():
        print(f"   [WARNING] No encontrado: {psitp_shp}")
        return 0

    print(f"   [FILE] Archivo: {psitp_shp.name}")

    # Leer shapefile
    sf = shapefile.Reader(str(psitp_shp))
    print(f"   [INFO] Registros en shapefile: {len(sf.shapeRecords()):,}")
    print(f"   [INFO] Campos: {[f[0] for f in sf.fields[1:]]}")

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
                    nombre = (record.get('NOMBRE') or record.get('nombre') or
                             record.get('codigo') or f'Parada_{count}')

                    cur.execute("""
                        INSERT INTO iug.osm_transport (type, name, geom)
                        VALUES ('bus_stop', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    """, (nombre[:200], lon, lat))
                    count += 1

                    if count % 1000 == 0:
                        print(f"      Procesadas: {count:,}...")

            except Exception as e:
                errors += 1
                if errors < 10:
                    print(f"      Error: {e}")

        conn.commit()
        print(f"   [OK] Cargadas: {count:,} paradas SITP")
        if errors > 0:
            print(f"   [WARNING] Errores: {errors}")

    return count

def load_parques_csv(conn):
    """Carga parques desde CSV IDRD"""
    print("\n[PARQUES] Parques (desde CSV)...")
    parques_csv = ARCHIVOS_DIR / "espacios_para_deporte_bogota" / "directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv"

    if not parques_csv.exists():
        print(f"   [WARNING] No encontrado: {parques_csv}")
        return 0

    print(f"   Archivo: {parques_csv.name}")

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
        print(f"   [OK] Cargados: {count} parques")
        if errors > 0:
            print(f"   [WARNING] Errores: {errors}")

    return count

def load_all_espaciales():
    """
    Función principal: carga todas las capas espaciales básicas

    Returns:
        True si la carga fue exitosa, False en caso contrario
    """
    print("=" * 80)
    print("CARGANDO CAPAS ESPACIALES BÁSICAS")
    print("=" * 80)

    try:
        conn = get_conn()

        # Verificar qué tablas están vacías
        tablas_status = {
            'localidad': check_table_empty(conn, 'localidad'),
            'osm_transport': check_table_empty(conn, 'osm_transport'),
            'osm_parks': check_table_empty(conn, 'osm_parks')
        }

        # Si todas tienen datos, omitir
        if not any(tablas_status.values()):
            print("[OK] Todas las tablas ya tienen datos, omitiendo carga...")
            conn.close()
            return True

        print("\n[INFO] Estado de tablas:")
        for tabla, vacia in tablas_status.items():
            estado = "VACÍA" if vacia else "CON DATOS"
            print(f"   {tabla:.<30} {estado}")

        total = 0

        # Cargar solo las que están vacías
        if tablas_status['localidad']:
            total += load_localidades(conn)

        if tablas_status['osm_transport']:
            total += load_sitp(conn)

        if tablas_status['osm_parks']:
            total += load_parques_csv(conn)

        # Resumen final
        print("\n" + "=" * 80)
        print("[RESUMEN] DATOS CARGADOS EN LA BASE DE DATOS")
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
                print(f"   {row[0]:.<30} {row[1]:>8,} registros")

        conn.close()

        print("=" * 80)
        print("[OK] Carga de capas espaciales completada")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n[ERROR] Error cargando capas espaciales: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = load_all_espaciales()
    sys.exit(0 if success else 1)
