"""
Loader incremental, robusto, para las categorías de dotaciones que NO se
cargaron en la primera corrida. Cada archivo viene en un formato distinto:
GeoJSON 3857, ESRI {attributes,geometry}, CSV latin-1 con coord_x/coord_y…
así que parseamos caso por caso y reproyectamos a EPSG:4326 server-side
con PostGIS.

Uso (desde data-loader container):
    docker compose --profile data run --rm --entrypoint sh data-loader \\
        -c "python /app/loaders/load_dotaciones_faltantes.py"
"""
import csv
import json
import os
import sys
from pathlib import Path

import psycopg2

BASE = Path('/app/archivos/dotaciones')
DEPORTES_CSV = BASE / 'espacios_para_deporte_bogota' / 'directorio-parques-y-escenarios-2023-datos-abiertos-v1.0.csv'


def get_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', ''),
    )


def existe_categoria(conn, categoria: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM iug.dotaciones_poi WHERE categoria = %s)",
            (categoria,),
        )
        return cur.fetchone()[0]


# ── 1. Colegios (GeoJSON EPSG:3857) ─────────────────────────────
def load_colegios(conn) -> int:
    if existe_categoria(conn, 'colegio'):
        print("   [SKIP] colegio ya cargado")
        return 0
    src = BASE / 'colegios12_2024.geojson'
    print(f"   [LOAD] {src.name} (EPSG:3857 → 4326)")
    with open(src) as f:
        d = json.load(f)
    inserted = 0
    with conn.cursor() as cur:
        for feat in d.get('features', []):
            geom = feat.get('geometry')
            props = feat.get('properties', {})
            if not geom:
                continue
            nombre = (props.get('NOMBRE_EST') or props.get('NOMBRE_SED')
                      or props.get('nombre') or 'Colegio sin nombre')[:200]
            try:
                cur.execute("""
                    INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                    VALUES (%s, 'colegio', 'colegios12_2024.geojson',
                            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 3857), 4326))
                """, (nombre, json.dumps(geom)))
                inserted += 1
            except Exception:
                continue
    conn.commit()
    print(f"   [OK] colegios insertados: {inserted}")
    return inserted


# ── 2. Teatros (ESRI JSON EPSG:3857) ────────────────────────────
def load_teatros(conn) -> int:
    if existe_categoria(conn, 'teatro'):
        print("   [SKIP] teatro ya cargado")
        return 0
    src = BASE / 'teatroauditorio.json'
    print(f"   [LOAD] {src.name} (ESRI JSON · EPSG:3857)")
    with open(src) as f:
        d = json.load(f)
    inserted = 0
    with conn.cursor() as cur:
        for feat in d.get('features', []):
            attrs = feat.get('attributes', {})
            geom = feat.get('geometry', {})
            x, y = geom.get('x'), geom.get('y')
            if x is None or y is None:
                continue
            nombre = (attrs.get('LECNOMBRE') or attrs.get('LECCODIGO')
                      or 'Teatro/auditorio')[:200]
            try:
                cur.execute("""
                    INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                    VALUES (%s, 'teatro', 'teatroauditorio.json',
                            ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 3857), 4326))
                """, (nombre, x, y))
                inserted += 1
            except Exception:
                continue
    conn.commit()
    print(f"   [OK] teatros insertados: {inserted}")
    return inserted


# ── 3. Plazas de mercado (GeoJSON EPSG:3116 — Magna-Sirgas Bogotá) ─
# El archivo trae coordenadas tipo (100567, 101206) — sistema cartesiano
# local. Probamos varios CRS hasta hallar el que cae dentro de Bogotá.
def load_plazas(conn) -> int:
    if existe_categoria(conn, 'plaza_mercado'):
        print("   [SKIP] plaza_mercado ya cargado")
        return 0
    src = BASE / 'plaza_mercado.geojson'
    with open(src) as f:
        d = json.load(f)

    # CRSs candidatos para Bogotá (orden de prioridad):
    # 3116 = Magna-Sirgas Origen Bogotá (más probable)
    # 21897 = Bogotá Bogota (legacy)
    # 4326 = WGS84 (improbable porque valores son enteros grandes)
    crs_candidates = [3116, 21897, 4326, 3857]

    sample = next((f for f in d['features'] if f.get('geometry')), None)
    if not sample:
        print("   [ERROR] No hay features con geometría")
        return 0

    chosen_crs = None
    with conn.cursor() as cur:
        for crs in crs_candidates:
            try:
                cur.execute("""
                    SELECT ST_X(p), ST_Y(p) FROM (
                        SELECT ST_Centroid(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), %s), 4326)) AS p
                    ) q
                """, (json.dumps(sample['geometry']), crs))
                lon, lat = cur.fetchone()
                if -75 < lon < -73 and 3 < lat < 6:
                    chosen_crs = crs
                    print(f"   [INFO] CRS detectado: EPSG:{crs} (lon={lon:.3f}, lat={lat:.3f})")
                    break
            except Exception:
                continue
            finally:
                conn.rollback()

    if chosen_crs is None:
        print("   [ERROR] Ningún CRS candidato produce coordenadas en Bogotá")
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for feat in d.get('features', []):
            geom = feat.get('geometry')
            props = feat.get('properties', {})
            if not geom:
                continue
            nombre = (props.get('PLAZA') or props.get('NOMBRE')
                      or props.get('nombre') or 'Plaza de mercado')[:200]
            try:
                cur.execute("""
                    INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                    VALUES (%s, 'plaza_mercado', 'plaza_mercado.geojson',
                            ST_Centroid(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), %s), 4326)))
                """, (nombre, json.dumps(geom), chosen_crs))
                inserted += 1
            except Exception:
                continue
    conn.commit()
    print(f"   [OK] plazas insertadas: {inserted}")
    return inserted


# ── 4. CC adicionales (CSV latin-1 con ;) ───────────────────────
def load_centros_comerciales(conn) -> int:
    src = BASE / 'centro-comercial.csv'
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM iug.dotaciones_poi WHERE fuente = 'centro-comercial.csv')")
        if cur.fetchone()[0]:
            print("   [SKIP] centro-comercial.csv ya cargado")
            return 0
    print(f"   [LOAD] {src.name} (latin-1, separador ;)")
    inserted = 0
    with open(src, encoding='latin-1') as f:
        # El archivo tiene una sola "columna" porque sniff falla; parseamos manual
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        # Localizamos índices de columnas relevantes
        try:
            idx_nombre = header.index('Nombre')
            idx_x = header.index('coord_x')
            idx_y = header.index('coord_y')
        except ValueError:
            print(f"   [ERROR] Cabecera inesperada: {header}")
            return 0

        with conn.cursor() as cur:
            for row in reader:
                if len(row) <= max(idx_nombre, idx_x, idx_y):
                    continue
                try:
                    nombre = (row[idx_nombre] or 'Centro comercial')[:200]
                    x = float(str(row[idx_x]).replace(',', '.'))
                    y = float(str(row[idx_y]).replace(',', '.'))
                    # Detectamos si es 4326 (lat/lon) o 3857 (mercator)
                    if abs(x) < 180:  # parecen ya lat/lon
                        cur.execute("""
                            INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                            VALUES (%s, 'centro_comercial', 'centro-comercial.csv',
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                        """, (nombre, x, y))
                    else:
                        cur.execute("""
                            INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                            VALUES (%s, 'centro_comercial', 'centro-comercial.csv',
                                    ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 3857), 4326))
                        """, (nombre, x, y))
                    inserted += 1
                except Exception:
                    continue
    conn.commit()
    print(f"   [OK] CC adicionales: {inserted}")
    return inserted


# ── 5. Parques + canchas (CSV utf-8 con LAT/LON) ────────────────
def load_parques(conn) -> int:
    if existe_categoria(conn, 'parque'):
        print("   [SKIP] parque ya cargado")
        return 0
    if not DEPORTES_CSV.exists():
        print(f"   [ERROR] No encontrado: {DEPORTES_CSV}")
        return 0
    print(f"   [LOAD] {DEPORTES_CSV.name} (parques IDRD + escenarios)")
    inserted = 0
    with open(DEPORTES_CSV, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        with conn.cursor() as cur:
            for row in reader:
                try:
                    lat = float(str(row.get('LATITUD', '0')).replace(',', '.'))
                    lon = float(str(row.get('LONGITUD', '0')).replace(',', '.'))
                    if not (3 < lat < 6 and -75 < lon < -73):
                        continue
                    nombre = (row.get('NOMBRE DEL PARQUE O ESCENARIO')
                              or 'Parque IDRD')[:200]
                    tipo = (row.get('TIPO DE PARQUE') or '').lower()
                    # Si el tipo contiene "escenario" o "deportivo", lo categorizamos
                    # como cancha/escenario; lo demás como parque.
                    if 'escenario' in tipo or 'deportivo' in tipo:
                        categoria = 'escenario_deportivo'
                    else:
                        categoria = 'parque'
                    cur.execute("""
                        INSERT INTO iug.dotaciones_poi (nombre, categoria, fuente, geom)
                        VALUES (%s, %s, 'parques_idrd_2023.csv',
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    """, (nombre, categoria, lon, lat))
                    inserted += 1
                except Exception:
                    continue
    conn.commit()
    print(f"   [OK] parques + escenarios insertados: {inserted}")
    return inserted


def main() -> None:
    print("=" * 80)
    print("CARGA INCREMENTAL DE DOTACIONES FALTANTES")
    print("=" * 80)
    conn = get_conn()
    total = 0

    print("\n[EDUCACION] Colegios SED");           total += load_colegios(conn)
    print("\n[CULTURA]    Teatros / Auditorios");  total += load_teatros(conn)
    print("\n[ABASTEC.]   Plazas de mercado");     total += load_plazas(conn)
    print("\n[ABASTEC.]   CC adicionales");        total += load_centros_comerciales(conn)
    print("\n[RECREACION] Parques IDRD + escenarios"); total += load_parques(conn)

    conn.close()
    print("\n" + "=" * 80)
    print(f"TOTAL INSERTADOS EN ESTA CORRIDA: {total:,}")
    print("=" * 80)


if __name__ == "__main__":
    main()
