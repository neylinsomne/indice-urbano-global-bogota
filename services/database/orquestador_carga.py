#!/usr/bin/env python3
"""
Orquestador de carga de datos - Ejecuta después del scraping.
Verifica si las tablas están vacías y ejecuta los scripts de carga correspondientes.
"""
import os
import sys
import psycopg2
import subprocess
from pathlib import Path
from datetime import datetime

# Directorio base
BASE_DIR = Path(__file__).parent

def get_conn():
    """Conexión a PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )

def tabla_esta_vacia(tabla_name, schema='iug'):
    """Verifica si una tabla está vacía"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{tabla_name};")
            count = cur.fetchone()[0]
        conn.close()
        return count == 0
    except Exception as e:
        print(f"   [WARNING] Error verificando tabla {tabla_name}: {e}")
        return True  # Asumir vacía si hay error

def ejecutar_script(script_path, descripcion):
    """Ejecuta un script de Python y retorna su código de salida"""
    print(f"\n[RUNNING] Ejecutando: {descripcion}")
    print(f"   Script: {script_path.name}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutos máximo por script
        )

        if result.stdout:
            print(result.stdout)

        if result.returncode == 0:
            print(f"   [OK] {descripcion} completado exitosamente")
            return True
        else:
            print(f"   [ERROR] Error en {descripcion}")
            if result.stderr:
                print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"   [TIMEOUT] Timeout ejecutando {descripcion}")
        return False
    except Exception as e:
        print(f"   [ERROR] Excepción: {e}")
        return False

def cargar_localidades_barrios():
    """Carga localidades y barrios de Bogotá desde archivos GeoJSON"""
    script = BASE_DIR / "cargar_localidades_barrios.py"

    # Verificar si barrio está vacío (localidad ya tiene datos genéricos)
    barrios_vacios = tabla_esta_vacia('barrio')

    # Verificar si las localidades tienen nombres genéricos
    localidades_genericas = False
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT nombre FROM iug.localidad LIMIT 1;")
            row = cur.fetchone()
            if row and row[0].startswith('Localidad_'):
                localidades_genericas = True
        conn.close()
    except:
        localidades_genericas = True

    if barrios_vacios or localidades_genericas:
        print("\n[LOCALIDADES/BARRIOS] Carga de divisiones administrativas")
        print("=" * 80)
        return ejecutar_script(script, "Carga de localidades y barrios de Bogotá")
    else:
        print("\n[LOCALIDADES/BARRIOS] Ya cargadas, omitiendo...")
        return True

def cargar_tablas_espaciales():
    """Carga tablas espaciales básicas (parques, SITP)"""
    tablas = ['osm_parks', 'osm_transport']
    script = BASE_DIR / "cargar_datos.py"

    # Verificar si alguna está vacía
    alguna_vacia = any(tabla_esta_vacia(t) for t in tablas)

    if alguna_vacia:
        print("\n[ESPACIALES] TABLAS ESPACIALES BASICAS")
        print("=" * 80)
        return ejecutar_script(script, "Carga de parques y SITP")
    else:
        print("\n[ESPACIALES] TABLAS ESPACIALES BASICAS: Ya cargadas, omitiendo...")
        return True

def cargar_pot():
    """Carga datos del Plan de Ordenamiento Territorial"""
    tablas = ['pot_area_actividad', 'pot_tratamiento', 'pot_edificabilidad', 'pot_upl']
    script = BASE_DIR / "loaders" / "load_pot555.py"

    alguna_vacia = any(tabla_esta_vacia(t) for t in tablas)

    if alguna_vacia:
        print("\n[POT] Plan de Ordenamiento Territorial")
        print("=" * 80)
        return ejecutar_script(script, "Carga de datos POT 555")
    else:
        print("\n[POT] Ya cargado, omitiendo...")
        return True

def cargar_vias():
    """Carga vías principales desde OSM"""
    script = BASE_DIR / "loaders" / "load_osm_roads.py"

    if tabla_esta_vacia('osm_main_roads'):
        print("\n[VIAS] VIAS PRINCIPALES")
        print("=" * 80)
        return ejecutar_script(script, "Carga de vias principales desde OSM")
    else:
        print("\n[VIAS] Ya cargadas, omitiendo...")
        return True

def cargar_universidades():
    """Carga universidades"""
    script = BASE_DIR / "loaders" / "load_universidades.py"

    if tabla_esta_vacia('universidad'):
        print("\n[UNIVERSIDADES] Carga de universidades")
        print("=" * 80)
        return ejecutar_script(script, "Carga de universidades")
    else:
        print("\n[UNIVERSIDADES] Ya cargadas, omitiendo...")
        return True

def cargar_seguridad():
    """Carga datos de seguridad"""
    tablas = ['criminalidad_localidad', 'sector_priorizado', 'cai_policia']
    script = BASE_DIR / "loaders" / "load_seguridad_completo.py"

    alguna_vacia = any(tabla_esta_vacia(t) for t in tablas)

    if alguna_vacia:
        print("\n[SEGURIDAD] Datos de seguridad")
        print("=" * 80)
        return ejecutar_script(script, "Carga de datos de seguridad")
    else:
        print("\n[SEGURIDAD] Ya cargada, omitiendo...")
        return True

def cargar_dotaciones():
    """Carga datos de dotaciones (5 categorías: salud, educación, cultura, abastecimiento, recreación)"""
    script = BASE_DIR / "loaders" / "load_dotaciones.py"

    if tabla_esta_vacia('dotaciones_poi'):
        print("\n[DOTACIONES] Salud, Educacion, Cultura, etc.")
        print("=" * 80)
        return ejecutar_script(script, "Carga de dotaciones")
    else:
        print("\n[DOTACIONES] Ya cargadas, omitiendo...")
        return True

def calcular_indicadores():
    """Calcula indicadores urbanísticos (iacc, iseg, idot, ihed, ipnu, iug) para todos los inmuebles."""
    script = BASE_DIR / "loaders" / "calcular_indicadores.py"

    print("\n[INDICADORES] Calculando indicadores urbanisticos")
    print("=" * 80)
    return ejecutar_script(script, "Calculo de indicadores urbanisticos")


def resumen_final():
    """Muestra un resumen de todas las tablas cargadas"""
    print("\n" + "=" * 80)
    print("RESUMEN FINAL - ESTADO DE TABLAS")
    print("=" * 80)

    tablas_a_verificar = [
        ('Localidades', 'localidad'),
        ('Barrios', 'barrio'),
        ('Parques', 'osm_parks'),
        ('SITP', 'osm_transport'),
        ('TransMilenio', 'estacion_transmilenio'),
        ('Vías principales', 'osm_main_roads'),
        ('Universidades', 'universidad'),
        ('POT - Área Actividad', 'pot_area_actividad'),
        ('POT - Tratamiento', 'pot_tratamiento'),
        ('POT - Edificabilidad', 'pot_edificabilidad'),
        ('POT - UPL', 'pot_upl'),
        ('Criminalidad Localidad', 'criminalidad_localidad'),
        ('Sectores Priorizados', 'sector_priorizado'),
        ('CAI Policía', 'cai_policia'),
        ('Dotaciones POI', 'dotaciones_poi'),
    ]

    conn = get_conn()
    todas_ok = True

    for nombre, tabla in tablas_a_verificar:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM iug.{tabla};")
                count = cur.fetchone()[0]

                if count > 0:
                    print(f"   [OK] {nombre:.<35} {count:>8,} registros")
                else:
                    print(f"   [WARNING] {nombre:.<35} {'VACÍA':>8}")
                    todas_ok = False
        except Exception as e:
            print(f"   [ERROR] {nombre:.<35} {'ERROR':>8}")
            todas_ok = False

    conn.close()

    print("=" * 80)
    return todas_ok

def main():
    """Función principal del orquestador"""
    print("=" * 80)
    print("ORQUESTADOR DE CARGA DE DATOS")
    print("=" * 80)
    print(f"Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    resultados = {}

    # Ejecutar cada carga
    resultados['localidades_barrios'] = cargar_localidades_barrios()
    resultados['espaciales'] = cargar_tablas_espaciales()
    resultados['pot'] = cargar_pot()
    resultados['vias'] = cargar_vias()
    resultados['universidades'] = cargar_universidades()
    resultados['seguridad'] = cargar_seguridad()
    resultados['dotaciones'] = cargar_dotaciones()
    resultados['indicadores'] = calcular_indicadores()

    # Resumen final
    tablas_ok = resumen_final()

    # Resumen de ejecución
    print("\n" + "=" * 80)
    print("RESUMEN DE EJECUCION")
    print("=" * 80)

    for nombre, exitoso in resultados.items():
        estado = "[OK] EXITOSO" if exitoso else "[ERROR] FALLO"
        print(f"   {nombre:.<30} {estado}")

    total_exitosos = sum(1 for r in resultados.values() if r)
    total_scripts = len(resultados)

    print(f"\n   Total: {total_exitosos}/{total_scripts} scripts ejecutados correctamente")
    print("=" * 80)
    print(f"Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Determinar código de salida
    if total_exitosos == total_scripts and tablas_ok:
        print("\n[OK] CARGA COMPLETADA EXITOSAMENTE")
        return 0
    elif total_exitosos > 0:
        print("\n[WARNING] CARGA PARCIALMENTE EXITOSA")
        return 1
    else:
        print("\n[ERROR] CARGA FALLO")
        return 2

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
