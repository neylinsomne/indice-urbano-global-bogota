#!/usr/bin/env python3
"""
Carga de Localidades y Barrios de Bogotá desde archivos GeoJSON/ESRI JSON.

Este script:
1. Carga/actualiza las 20 localidades de Bogotá desde poligonos-localidades.geojson
2. Carga los barrios legalizados desde barriolegalizado.json (convirtiendo coordenadas)

Los barrios usan el sistema de coordenadas CarMAGBOG (proyectado), por lo que
se convierten a WGS84 (EPSG:4326) para compatibilidad con PostGIS.
"""

import os
import json
import psycopg2
from pathlib import Path
from pyproj import CRS, Transformer

# Directorio de archivos
ARCHIVOS_DIR = Path(__file__).parent / "archivos" / "archivos"

# Transformador CarMAGBOG → WGS84 (transformación exacta vía pyproj)
# CarMAGBOG: Transversa de Mercator local de Bogotá con elipsoide modificado
_CARMAG_CRS = CRS.from_proj4(
    "+proj=tmerc +lat_0=4.680486111 +lon_0=-74.14659167 "
    "+k=1.0 +x_0=92334.879 +y_0=109320.965 "
    "+a=6380687.0 +rf=298.257222101 +units=m +no_defs"
)
_WGS84 = CRS.from_epsg(4326)
_transformer = Transformer.from_crs(_CARMAG_CRS, _WGS84, always_xy=True)

def get_conn():
    """Conexión a PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD')
    )

def carmag_to_wgs84(x, y):
    """Convierte coordenadas CarMAGBOG → WGS84 usando pyproj (transformación exacta)."""
    lon, lat = _transformer.transform(x, y)
    return lon, lat

def convert_esri_geometry_to_wgs84(geometry):
    """
    Convierte una geometría ESRI (rings) a GeoJSON polygon en WGS84.
    """
    rings = geometry.get('rings', [])
    if not rings:
        return None

    converted_rings = []
    for ring in rings:
        converted_ring = []
        for point in ring:
            x, y = point[0], point[1]
            lon, lat = carmag_to_wgs84(x, y)
            converted_ring.append([lon, lat])
        converted_rings.append(converted_ring)

    return {
        "type": "Polygon",
        "coordinates": converted_rings
    }

def cargar_localidades():
    """
    Carga las localidades desde el archivo GeoJSON.
    Actualiza los nombres y geometrías de los registros existentes.
    """
    archivo = ARCHIVOS_DIR / "poligonos-localidades.geojson"

    if not archivo.exists():
        print(f"[ERROR] Archivo no encontrado: {archivo}")
        return False

    print(f"\n[LOCALIDADES] Cargando desde {archivo.name}")
    print("=" * 60)

    with open(archivo, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"   Total features encontradas: {len(features)}")

    conn = get_conn()
    cur = conn.cursor()

    # Usar UPSERT para respetar foreign keys existentes
    insertados = 0
    actualizados = 0
    errores = 0

    for feature in features:
        try:
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})

            # Obtener nombre (puede tener diferentes claves)
            nombre = (
                props.get('Nombre de la localidad') or
                props.get('LocNombre') or
                props.get('nombre') or
                props.get('NOMBRE') or
                f"Localidad_{insertados + actualizados + 1}"
            )

            # Obtener ID si existe
            id_localidad = props.get('Identificador unico de la localidad')
            if id_localidad:
                try:
                    id_localidad = int(id_localidad)
                except:
                    id_localidad = insertados + actualizados + 1
            else:
                id_localidad = insertados + actualizados + 1

            # Convertir geometría a GeoJSON string
            geom_json = json.dumps(geom)

            # Verificar si el ID ya existe
            cur.execute("SELECT id_localidad FROM iug.localidad WHERE id_localidad = %s", (id_localidad,))
            exists = cur.fetchone()

            if exists:
                # Actualizar registro existente
                cur.execute("""
                    UPDATE iug.localidad
                    SET nombre = %s, geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    WHERE id_localidad = %s;
                """, (nombre.strip(), geom_json, id_localidad))
                actualizados += 1
                print(f"   [UPDATE] {id_localidad}: {nombre}")
            else:
                # Insertar nuevo registro
                cur.execute("""
                    INSERT INTO iug.localidad (id_localidad, nombre, geom)
                    VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326));
                """, (id_localidad, nombre.strip(), geom_json))
                insertados += 1
                print(f"   [INSERT] {id_localidad}: {nombre}")

        except Exception as e:
            errores += 1
            print(f"   [ERROR] Feature: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n   Resumen: {insertados} nuevas, {actualizados} actualizadas, {errores} errores")
    return errores == 0

def cargar_barrios():
    """
    Carga los barrios desde el archivo ESRI JSON.
    Convierte las coordenadas de CarMAGBOG a WGS84.
    """
    archivo = ARCHIVOS_DIR / "barriolegalizado.json"

    if not archivo.exists():
        print(f"[ERROR] Archivo no encontrado: {archivo}")
        return False

    print(f"\n[BARRIOS] Cargando desde {archivo.name}")
    print("=" * 60)

    with open(archivo, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"   Total features encontradas: {len(features)}")

    conn = get_conn()
    cur = conn.cursor()

    # Obtener mapeo de localidades existentes
    cur.execute("SELECT id_localidad, nombre FROM iug.localidad;")
    localidades_map = {row[0]: row[1] for row in cur.fetchall()}
    print(f"   Localidades disponibles: {len(localidades_map)}")

    # Limpiar tabla de barrios
    cur.execute("DELETE FROM iug.barrio;")

    insertados = 0
    errores = 0
    batch_size = 100

    for i, feature in enumerate(features):
        try:
            attrs = feature.get('attributes', {})
            geom_esri = feature.get('geometry', {})

            # Extraer atributos
            nombre = attrs.get('NOMBRE', f'Barrio_{i+1}')
            codigo_id = attrs.get('CODIGO_ID', str(i+1))
            estado = attrs.get('ESTADO', 1)
            codigo_upz = attrs.get('CODIGO_UPZ')
            codigo_localidad = attrs.get('CODIGO_LOCALIDAD')
            area_total = attrs.get('AREA_TOTAL')
            poblacion = attrs.get('POBLACION_ESTIMADA')

            # Convertir código de localidad a int si es posible
            id_localidad = None
            if codigo_localidad:
                try:
                    id_localidad = int(codigo_localidad)
                    if id_localidad not in localidades_map:
                        id_localidad = None
                except:
                    pass

            # Convertir UPZ
            if codigo_upz:
                try:
                    codigo_upz = int(codigo_upz)
                except:
                    codigo_upz = None

            # Convertir geometría
            geom_wgs84 = convert_esri_geometry_to_wgs84(geom_esri)

            if not geom_wgs84:
                errores += 1
                continue

            geom_json = json.dumps(geom_wgs84)

            # Usar UPSERT para manejar duplicados por (id_localidad, nombre)
            nombre_barrio = nombre.strip() if nombre else f'Barrio_{i+1}'
            id_barrio = int(codigo_id) if codigo_id and str(codigo_id).isdigit() else i + 1

            # Intentar insertar, si ya existe actualizar
            cur.execute("""
                INSERT INTO iug.barrio (
                    id_barrio, nombre, id_localidad, descripcion,
                    area_total, poblacion_estimada, codigo_upz, estado, geom
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (id_barrio) DO UPDATE SET
                    nombre = EXCLUDED.nombre,
                    id_localidad = EXCLUDED.id_localidad,
                    area_total = EXCLUDED.area_total,
                    poblacion_estimada = EXCLUDED.poblacion_estimada,
                    codigo_upz = EXCLUDED.codigo_upz,
                    estado = EXCLUDED.estado,
                    geom = EXCLUDED.geom;
            """, (
                id_barrio,
                nombre_barrio,
                id_localidad,
                None,  # descripcion
                area_total,
                poblacion,
                codigo_upz,
                estado,
                geom_json
            ))

            insertados += 1

            # Commit por lotes
            if insertados % batch_size == 0:
                conn.commit()
                print(f"   ... {insertados} barrios insertados")

        except Exception as e:
            # Rollback para limpiar la transacción abortada
            conn.rollback()
            errores += 1
            if errores <= 5:  # Solo mostrar primeros 5 errores
                print(f"   [ERROR] Barrio {i}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n   Resumen: {insertados} barrios cargados, {errores} errores")
    return errores < len(features) * 0.1  # Menos del 10% de errores

def verificar_carga():
    """Verifica que los datos se cargaron correctamente"""
    print("\n[VERIFICACION] Comprobando datos cargados")
    print("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    # Contar localidades
    cur.execute("SELECT COUNT(*) FROM iug.localidad;")
    total_loc = cur.fetchone()[0]

    # Contar barrios
    cur.execute("SELECT COUNT(*) FROM iug.barrio;")
    total_bar = cur.fetchone()[0]

    # Verificar geometrías válidas
    cur.execute("SELECT COUNT(*) FROM iug.localidad WHERE ST_IsValid(geom);")
    valid_loc = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM iug.barrio WHERE ST_IsValid(geom);")
    valid_bar = cur.fetchone()[0]

    # Mostrar algunas localidades
    cur.execute("SELECT id_localidad, nombre FROM iug.localidad ORDER BY id_localidad LIMIT 5;")
    print("\n   Primeras 5 localidades:")
    for row in cur.fetchall():
        print(f"     {row[0]}: {row[1]}")

    # Mostrar algunos barrios
    cur.execute("""
        SELECT b.id_barrio, b.nombre, l.nombre as localidad
        FROM iug.barrio b
        LEFT JOIN iug.localidad l ON b.id_localidad = l.id_localidad
        LIMIT 5;
    """)
    print("\n   Primeros 5 barrios:")
    for row in cur.fetchall():
        print(f"     {row[0]}: {row[1]} ({row[2] or 'Sin localidad'})")

    cur.close()
    conn.close()

    print(f"\n   Total localidades: {total_loc} ({valid_loc} con geometría válida)")
    print(f"   Total barrios: {total_bar} ({valid_bar} con geometría válida)")

    return total_loc > 0 and total_bar > 0

def reasignar_inmuebles():
    """
    Reasigna TODOS los inmuebles a los barrios corregidos usando ST_Contains.
    Necesario después de recargar barrios con geometrías nuevas.

    Pasos:
    1. Bulk update id_barrio + id_localidad (triggers deshabilitados para rendimiento)
    2. Propagar indicadores desde indicador_barrio a cada inmueble
    3. Recalcular IUG compuesto y ratio
    """
    print("\n[REASIGNACION] Reasignando inmuebles a barrios corregidos")
    print("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    # Diagnóstico antes
    cur.execute("SELECT COUNT(*) FROM iug.inmueble WHERE geom IS NOT NULL;")
    total_con_geom = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM iug.inmueble WHERE id_barrio IS NOT NULL;")
    antes_con_barrio = cur.fetchone()[0]
    print(f"   Inmuebles con geom: {total_con_geom}")
    print(f"   Con id_barrio ANTES: {antes_con_barrio}")

    # Paso 1: Reasignar barrio/localidad (triggers disabled para perf)
    print("\n   [1/3] Reasignando barrio + localidad via ST_Contains...")
    cur.execute("SET session_replication_role = 'replica';")

    cur.execute("""
        UPDATE iug.inmueble i
        SET id_barrio = sub.id_barrio,
            id_localidad = sub.id_localidad
        FROM (
            SELECT DISTINCT ON (i2.id_inmueble)
                i2.id_inmueble, b.id_barrio, b.id_localidad
            FROM iug.inmueble i2
            JOIN iug.barrio b ON ST_Contains(
                ST_MakeValid(b.geom), i2.geom
            )
            WHERE i2.geom IS NOT NULL
              AND b.geom IS NOT NULL
            ORDER BY i2.id_inmueble
        ) sub
        WHERE i.id_inmueble = sub.id_inmueble;
    """)
    reasignados = cur.rowcount
    print(f"         {reasignados} inmuebles reasignados")

    cur.execute("SET session_replication_role = 'origin';")
    conn.commit()

    # Paso 2: Propagar indicadores de indicador_barrio a inmuebles
    print("   [2/3] Propagando indicadores de barrio a inmuebles...")
    cur.execute("""
        UPDATE iug.inmueble i
        SET iacc = ib.iacc,
            iseg = ib.iseg,
            idot = ib.idot,
            ipnu = ib.ipnu
        FROM iug.indicador_barrio ib
        WHERE i.id_barrio = ib.id_barrio
          AND i.id_barrio IS NOT NULL;
    """)
    print(f"         {cur.rowcount} inmuebles actualizados con indicadores")
    conn.commit()

    # Paso 3: Recalcular IUG compuesto
    print("   [3/3] Recalculando IUG compuesto y ratio...")
    cur.execute("""
        UPDATE iug.inmueble
        SET iug = ROUND((
                COALESCE(ihed,0) + COALESCE(iacc,0) + COALESCE(iseg,0)
              + COALESCE(idot,0) + COALESCE(ipnu,0)
            ) / 5.0, 3),
            ratio = CASE
                WHEN precio_std IS NULL OR precio_std = 0 THEN NULL
                ELSE ROUND((
                    (COALESCE(ihed,0) + COALESCE(iacc,0) + COALESCE(iseg,0)
                   + COALESCE(idot,0) + COALESCE(ipnu,0)) / 5.0
                ) / precio_std, 4)
            END
        WHERE id_barrio IS NOT NULL;
    """)
    print(f"         {cur.rowcount} inmuebles con IUG recalculado")
    conn.commit()

    # Diagnóstico después
    cur.execute("SELECT COUNT(*) FROM iug.inmueble WHERE id_barrio IS NOT NULL;")
    despues_con_barrio = cur.fetchone()[0]

    cur.close()
    conn.close()

    ganados = despues_con_barrio - antes_con_barrio
    print(f"\n   Con id_barrio DESPUES: {despues_con_barrio} ({'+' if ganados >= 0 else ''}{ganados})")
    print(f"   Sin barrio (fuera de polígonos): {total_con_geom - despues_con_barrio}")


def main():
    """Función principal"""
    print("\n" + "=" * 60)
    print("CARGA DE LOCALIDADES Y BARRIOS DE BOGOTA")
    print("=" * 60)

    # 1. Cargar localidades
    if not cargar_localidades():
        print("\n[WARNING] Problemas cargando localidades")

    # 2. Cargar barrios
    if not cargar_barrios():
        print("\n[WARNING] Problemas cargando barrios")

    # 3. Verificar
    verificar_carga()

    # 4. Reasignar inmuebles a barrios corregidos
    reasignar_inmuebles()

    print("\n[DONE] Proceso completado")
    print("=" * 60)
    print("\nNOTA: Reinicia el contenedor API para limpiar cache Redis:")
    print("  docker compose restart api")

if __name__ == "__main__":
    main()
