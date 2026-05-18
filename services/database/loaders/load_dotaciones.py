"""
Cargador de Dotaciones (POIs de Amenidades)

Carga datos de 5 categorías de dotaciones a la tabla iug.dotaciones_poi:
1. Salud (IPS, farmacias)
2. Educación (colegios)
3. Cultura (bibliotecas, teatros)
4. Abastecimiento (centros comerciales, plazas de mercado)
5. Recreación (parques, canchas)

Uso:
    python load_dotaciones.py

O como parte del orquestador.
"""
import os
import json
import csv
import sys
import psycopg2
from pathlib import Path

# Directorio base
BASE_DIR = Path(__file__).parent.parent
DOTACIONES_DIR = BASE_DIR / "archivos" / "archivos" / "dotaciones"
DEPORTES_DIR = BASE_DIR / "archivos" / "archivos" / "espacios_para_deporte_bogota"

def get_conn():
    """Conexión a PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

def check_table_empty(conn, table_name):
    """Verifica si una tabla está vacía"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0] == 0

def load_geojson_to_poi(conn, filepath, categoria, fuente):
    """
    Carga un GeoJSON a dotaciones_poi

    Args:
        conn: Conexión PostgreSQL
        filepath: Path al archivo GeoJSON
        categoria: Categoría de la dotación (ips, colegio, biblioteca, etc.)
        fuente: Nombre del archivo fuente para trazabilidad

    Returns:
        Número de registros insertados
    """
    if not filepath.exists():
        print(f"   [WARNING] No encontrado: {filepath.name}")
        return 0

    print(f"   [LOADING] Cargando {filepath.name} como '{categoria}'...")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get('features', [])
    inserted = 0
    errors = 0

    with conn.cursor() as cur:
        for feature in features:
            try:
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})
                geom_type = geom.get('type', '')
                coords = geom.get('coordinates', [])

                if not coords:
                    errors += 1
                    continue

                # Extraer nombre (intentar varios campos comunes)
                nombre = (
                    props.get('nombre') or
                    props.get('NOMBRE') or
                    props.get('name') or
                    props.get('Nombre_IPS') or
                    props.get('NOMBRE_SEDE') or
                    props.get('NOMBRE_BIBLORED') or
                    props.get('NOMBRE_PARQUE') or
                    'Sin nombre'
                )

                # Obtener coordenadas según tipo de geometría
                if geom_type == 'Point':
                    lon, lat = coords[0], coords[1]
                elif geom_type in ['Polygon', 'MultiPolygon']:
                    # Usar centroide con PostGIS
                    geom_json = json.dumps(geom)
                    cur.execute("""
                        INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                        VALUES (%s, %s, %s, ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                    """, (nombre[:200], categoria, fuente, geom_json))
                    inserted += 1
                    continue
                else:
                    errors += 1
                    continue

                # Validar coordenadas dentro de Colombia (rough bounds)
                if not (3 < lat < 6 and -75 < lon < -73):
                    errors += 1
                    continue

                cur.execute("""
                    INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                """, (nombre[:200], categoria, fuente, lon, lat))

                inserted += 1

            except Exception as e:
                errors += 1
                if errors < 5:
                    print(f"      Error: {str(e)[:80]}")

    conn.commit()
    print(f"   [OK] Insertados: {inserted:,} registros")
    if errors > 0:
        print(f"   [WARNING] Errores: {errors}")

    return inserted

def load_csv_to_poi(conn, filepath, categoria, fuente, lat_col='LATITUD', lon_col='LONGITUD', name_col='NAME'):
    """
    Carga un CSV con lat/lon a dotaciones_poi

    Args:
        conn: Conexión PostgreSQL
        filepath: Path al archivo CSV
        categoria: Categoría de la dotación
        fuente: Nombre del archivo fuente
        lat_col: Nombre de columna de latitud
        lon_col: Nombre de columna de longitud
        name_col: Nombre de columna de nombre

    Returns:
        Número de registros insertados
    """
    if not filepath.exists():
        print(f"   [WARNING] No encontrado: {filepath.name}")
        return 0

    print(f"   [LOADING] Cargando {filepath.name} como '{categoria}'...")

    inserted = 0
    errors = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        with conn.cursor() as cur:
            for row in reader:
                try:
                    # Intentar obtener lat/lon de varias columnas posibles
                    lat_str = (row.get(lat_col) or row.get('latitud') or
                              row.get('Latitud') or row.get('LAT') or '0')
                    lon_str = (row.get(lon_col) or row.get('longitud') or
                              row.get('Longitud') or row.get('LON') or '0')

                    lat = float(lat_str.replace(',', '.'))
                    lon = float(lon_str.replace(',', '.'))

                    # Nombre
                    nombre = (row.get(name_col) or row.get('nombre') or
                             row.get('NOMBRE') or row.get('Nombre') or 'Sin nombre')

                    # Validar coordenadas
                    if not (3 < lat < 6 and -75 < lon < -73):
                        errors += 1
                        continue

                    cur.execute("""
                        INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                        VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    """, (nombre[:200], categoria, fuente, lon, lat))

                    inserted += 1

                except (ValueError, TypeError, KeyError) as e:
                    errors += 1

    conn.commit()
    print(f"   [OK] Insertados: {inserted:,} registros")
    if errors > 0:
        print(f"   [WARNING] Errores: {errors}")

    return inserted

def load_osm_parks(conn):
    """Copia centroides de osm_parks a dotaciones_poi"""
    print("   [LOADING] Copiando parques de osm_parks...")

    with conn.cursor() as cur:
        # Verificar que osm_parks existe y tiene datos
        cur.execute("SELECT COUNT(*) FROM iug.osm_parks")
        count = cur.fetchone()[0]

        if count == 0:
            print("   [WARNING] Tabla osm_parks está vacía, omitiendo...")
            return 0

        cur.execute("""
            INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
            SELECT
                COALESCE(name, 'Parque'),
                'parque',
                'osm_parks',
                ST_Centroid(geom)
            FROM iug.osm_parks
            WHERE name IS NOT NULL
        """)
        inserted = cur.rowcount

    conn.commit()
    print(f"   [OK] Insertados: {inserted:,} parques")
    return inserted

def load_all_dotaciones():
    """
    Función principal: carga todas las categorías de dotaciones

    Returns:
        True si la carga fue exitosa, False en caso contrario
    """
    print("=" * 80)
    print("CARGANDO DATOS DE DOTACIONES")
    print("=" * 80)

    try:
        conn = get_conn()

        # Verificar si tabla está vacía
        if not check_table_empty(conn, 'iug.dotaciones_poi'):
            print("[OK] Tabla dotaciones_poi ya tiene datos, omitiendo carga...")
            conn.close()
            return True

        print("\n[INFO] Tabla dotaciones_poi vacía, iniciando carga...")
        print("=" * 80)

        total = 0

        # ===== 1. SALUD =====
        print("\n[SALUD]")
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'salud.geojson', 'ips', 'salud.geojson')
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'farmacias.geojson', 'farmacia', 'farmacias.geojson')

        # ===== 2. EDUCACIÓN =====
        print("\n[EDUCACION]")
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'colegios12_2024.geojson', 'colegio', 'colegios.geojson')

        # ===== 3. CULTURA =====
        print("\n[CULTURA]")
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'biblored.geojson', 'biblioteca', 'biblored.geojson')
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'teatroauditorio.json', 'teatro', 'teatroauditorio.json')

        # ===== 4. ABASTECIMIENTO =====
        print("\n[ABASTECIMIENTO]")
        total += load_csv_to_poi(
            conn,
            DOTACIONES_DIR / 'centros_comerciales_bogota.csv',
            'centro_comercial',
            'cc_bogota.csv',
            lat_col='LATITUD',
            lon_col='LONGITUD',
            name_col='NAME'
        )
        total += load_csv_to_poi(
            conn,
            DOTACIONES_DIR / 'centro-comercial.csv',
            'centro_comercial',
            'centro-comercial.csv',
            lat_col='LATITUD',
            lon_col='LONGITUD',
            name_col='NAME'
        )
        total += load_geojson_to_poi(conn, DOTACIONES_DIR / 'plaza_mercado.geojson', 'plaza_mercado', 'plaza_mercado.geojson')

        # ===== 5. RECREACIÓN =====
        print("\n[RECREACION]")
        total += load_csv_to_poi(
            conn,
            DEPORTES_DIR / '1.-canchas_futbol.csv',
            'cancha_futbol',
            'canchas_futbol.csv',
            lat_col='LATITUD',
            lon_col='LONGITUD',
            name_col='NAME'
        )
        total += load_csv_to_poi(
            conn,
            DEPORTES_DIR / '5.-parques-idrd.csv',
            'parque_idrd',
            'parques-idrd.csv',
            lat_col='LATITUD',
            lon_col='LONGITUD',
            name_col='NAME'
        )

        # Parques desde OSM (si existe)
        try:
            total += load_osm_parks(conn)
        except Exception as e:
            print(f"   [WARNING] Error copiando osm_parks: {e}")

        # Resumen final
        print("\n" + "=" * 80)
        print(f"[OK] CARGA COMPLETADA: {total:,} POIs insertados")
        print("=" * 80)

        # Verificación
        with conn.cursor() as cur:
            cur.execute("""
                SELECT categoria, COUNT(*)
                FROM iug.dotaciones_poi
                GROUP BY categoria
                ORDER BY categoria
            """)
            print("\n[RESUMEN] RESUMEN POR CATEGORIA:")
            for row in cur.fetchall():
                print(f"   {row[0]:.<30} {row[1]:>8,} POIs")

        conn.close()
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n[ERROR] Error cargando dotaciones: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = load_all_dotaciones()
    sys.exit(0 if success else 1)
