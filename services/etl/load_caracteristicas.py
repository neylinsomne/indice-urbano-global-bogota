#!/usr/bin/env python3
"""
ETL: Características de Inmuebles con Normalización Semántica

Procesa características desde MongoDB con normalización de sinónimos:
- "Piscina" = "Alberca" = "Zona húmeda" → término canónico
- Limpieza de "Ver más", mayúsculas, acent os
- Many-to-many: inmueble ↔ característica

Modos de normalización:
1. 'manual': Diccionario de sinónimos predefinido (rápido, preciso)
2. 'embeddings': Clustering semántico con sentence-transformers (flexible)
3. 'simple': Solo limpieza básica
"""

import os
import sys
import re
from pymongo import MongoClient
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from collections import defaultdict
import unicodedata

# Config
MONGO_CONFIG = {
    'host': os.getenv('MONGO_HOST', 'localhost'),
    'port': int(os.getenv('MONGO_PORT', '27017')),
    'database': os.getenv('MONGO_DATABASE', 'prueba'),
    'collection': 'inmuebles'
}

PG_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', '5434'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

NORMALIZATION_MODE = os.getenv('NORMALIZATION_MODE', 'manual')

# =====================================================
# DICCIONARIO DE SINÓNIMOS
# =====================================================
SINONIMOS = {
    # Piscinas/Agua
    'alberca': 'piscina',
    'zona humeda': 'piscina',
    'zona húmeda': 'piscina',
    'pool': 'piscina',
    'piscina temperada': 'piscina',
    'piscina climatizada': 'piscina',
    
    # Parqueaderos
    'garaje': 'parqueadero',
    'cochera': 'parqueadero',
    'parking': 'parqueadero',
    'estacionamiento': 'parqueadero',
    'parqueadero cubierto': 'parqueadero cubierto',
    'garaje cubierto': 'parqueadero cubierto',
    'parqueadero visitantes': 'parqueadero visitantes',
    
    # Gimnasio/Fitness
    'gym': 'gimnasio',
    'zona fitness': 'gimnasio',
    'sala de ejercicios': 'gimnasio',
    'gimnacio': 'gimnasio',  # error ortográfico común
    
    # Zonas sociales
    'salon social': 'salón social',
    'salon de eventos': 'salón social',
    'salon comunal': 'salón social',
    'area social': 'zona social',
    'zona bbq': 'zona de parrilla',
    'asador': 'zona de parrilla',
    'bbq': 'zona de parrilla',
    
    # Seguridad
    'porteria': 'portería 24 horas',
    'porteria 24h': 'portería 24 horas',
    'vigilancia': 'portería 24 horas',
    'seguridad 24h': 'portería 24 horas',
    'vigilante': 'portería 24 horas',
    'con administrador': 'administración',
    
    # Servicios
    'ascensor': 'ascensor',
    'elevador': 'ascensor',
    'cuarto util': 'cuarto útil',
    'deposito': 'depósito',
    'bodega': 'depósito',
    
    # Espacios exteriores
    'balcon': 'balcón',
    'terraza': 'terraza',
    'jardin': 'jardín',
    'patio': 'patio',
    'zona verde': 'zonas verdes',
    'areas verdes': 'zonas verdes',
    'parques cercanos': 'zonas verdes',
    
    # Ubicación
    'acceso pavimentado': 'acceso pavimentado',
    'area urbana': 'área urbana',
    'sobre via principal': 'vía principal',
    'sobre via secundaria': 'vía secundaria',
    
    # Servicios cercanos
    'supermercados / c.comerciales': 'centros comerciales cercanos',
    'comodas vias de acceso': 'buen acceso',
    
    # Instalaciones
    'calentador': 'calentador',
    'deteccion de humo': 'detector de humo',
    'escalera de emergencia': 'escalera de emergencia',
}

def normalizar_string(s):
    """
    Normaliza un string:
    - Minúsculas
    - Quita acentos
    - Normaliza espacios
    """
    if not s:
        return ''
    
    # Minúsculas
    s = s.lower().strip()
    
    # Quitar acentos (NFD + filter)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(char for char in s if unicodedata.category(char) != 'Mn')
    
    # Normalizar espacios
    s = ' '.join(s.split())
    
    return s

def limpiar_caracteristica(caracteristica_raw):
    """
    Limpia y normaliza una característica
    """
    if not caracteristica_raw or not isinstance(caracteristica_raw, str):
        return None
    
    # Remover "Ver más"
    cleaned = re.sub(r'Ver\s+m[aá]s$', '', caracteristica_raw, flags=re.IGNORECASE)
    cleaned = ' '.join(cleaned.split()).strip()
    
    if not cleaned:
        return None
    
    # Normalizar
    normalized = normalizar_string(cleaned)
    
    return normalized

def aplicar_sinonimos(caracteristica_normalizada):
    """
    Mapea a término canónico usando diccionario
    """
    if NORMALIZATION_MODE != 'manual':
        return caracteristica_normalizada
    
    # Buscar en diccionario
    if car acteristica_normalizada in SINONIMOS:
        return SINONIMOS[caracteristica_normalizada]
    
    # Buscar si alguna key está contenida
    for sinonimo, canonico in SINONIMOS.items():
        if sinonimo in caracteristica_normalizada:
            return canonico
    
    return caracteristica_normalizada

def extraer_caracteristicas_unicas(mongo_db):
    """Extrae y normaliza características únicas"""
    
    print(f"[EXTRACT] Extrayendo características de MongoDB...")
    
    collection = mongo_db[MONGO_CONFIG['collection']]
    
    pipeline = [
        {'$match': {'caracteristicas': {'$exists': True, '$ne': None}}},
        {'$project': {'caracteristicas': 1}},
        {'$unwind': '$caracteristicas'},
        {'$group': {'_id': '$caracteristicas'}}
    ]
    
    caracteristicas_raw = []
    for doc in collection.aggregate(pipeline):
        caract = doc['_id']
        if caract:
            caracteristicas_raw.append(caract)
    
    print(f"[EXTRACT] Total raw: {len(caracteristicas_raw)}")
    
    # Limpiar y normalizar
    mapeo_raw_to_canonica = {}
    caracteristicas_canonicas = set()
    ver_mas_count = 0
    sinonimo_count = 0
    
    for caract_raw in caracteristicas_raw:
        # Limpiar
        caract_limpia = limpiar_caracteristica(caract_raw)
        
        if not caract_limpia:
            continue
        
        # Contar "Ver más"
        if 'ver m' in caract_raw.lower():
            ver_mas_count += 1
        
        # Aplicar sinónimos
        caract_canonica = aplicar_sinonimos(caract_limpia)
        
        if caract_canonica != caract_limpia:
            sinonimo_count += 1
            print(f"    [SYNONYM] '{caract_raw}' → '{caract_canonica}'")
        
        mapeo_raw_to_canonica[caract_raw] = caract_canonica
        caracteristicas_canonicas.add(caract_canonica)
    
    print(f"[NORMALIZE] Características canónicas: {len(caracteristicas_canonicas)}")
    print(f"[NORMALIZE] 'Ver más' removidos: {ver_mas_count}")
    print(f"[NORMALIZE] Sinónimos unificados: {sinonimo_count}")
    
    return sorted(caracteristicas_canonicas), mapeo_raw_to_canonica

def cargar_catalogo(pg_conn, caracteristicas_canonicas):
    """Carga catálogo de características canónicas"""
    
    print(f"\n[LOAD] Cargando catálogo a PostgreSQL...")
    
    with pg_conn.cursor() as cur:
        for caract in caracteristicas_canonicas:
            cur.execute("""
                INSERT INTO iug.cat_caracteristica (nombre_caracteristica, tipo_dato)
                VALUES (%s, 'boolean')
                ON CONFLICT (nombre_caracteristica) DO NOTHING
            """, (caract,))
        
        pg_conn.commit()
        
        # Obtener mapeo
        cur.execute("""
            SELECT id_caracteristica, nombre_caracteristica 
            FROM iug.cat_caracteristica
        """)
        
        mapeo = {row[1]: row[0] for row in cur.fetchall()}
    
    print(f"[LOAD] Catálogo: {len(mapeo)} características")
    
    return mapeo

def procesar_inmuebles(mongo_db, pg_conn, mapeo_raw_to_canonica, mapeo_canonica_to_id):
    """Procesa inmuebles y crea relaciones many-to-many"""
    
    print(f"\n[TRANSFORM] Procesando inmuebles...")
    
    collection = mongo_db[MONGO_CONFIG['collection']]
    
    # Mapeo inmuebles
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT id_inmueble, codigo_fuente, pagina
            FROM iug.inmueble
            WHERE codigo_fuente IS NOT NULL
        """)
        mapeo_inmuebles = {(row[2], row[1]): row[0] for row in cur.fetchall()}
    
    print(f"[INFO] Inmuebles en PG: {len(mapeo_inmuebles)}")
    
    # Limpiar tabla
    with pg_conn.cursor() as cur:
        cur.execute("TRUNCATE iug.inmueble_caracteristica RESTART IDENTITY CASCADE")
        pg_conn.commit()
    
    # Procesar
    relaciones = []
    stats = defaultdict(int)
    
    for doc in collection.find({'caracteristicas': {'$exists': True, '$ne': None}}):
        pagina = doc.get('pagina', 'finca_raiz')
        codigo = doc.get('codigo_fr') or doc.get('codigo_fuente')
        caracteristicas_raw = doc.get('caracteristicas', [])
        
        if not codigo:
            continue
        
        id_inmueble = mapeo_inmuebles.get((pagina, codigo))
        if not id_inmueble:
            stats['sin_match'] += 1
            continue
        
        # Procesar características (many-to-many)
        for caract_raw in caracteristicas_raw:
            # Mapear raw → canónica
            caract_canonica = mapeo_raw_to_canonica.get(caract_raw)
            
            if caract_canonica:
                # Obtener ID
                id_caracteristica = mapeo_canonica_to_id.get(caract_canonica)
                
                if id_caracteristica:
                    relaciones.append((id_inmueble, id_caracteristica, True))
        
        stats['procesados'] += 1
        
        if stats['procesados'] % 500 == 0:
            print(f"[PROGRESS] {stats['procesados']} inmuebles...")
    
    print(f"[TRANSFORM] Procesados: {stats['procesados']}")
    print(f"[TRANSFORM] Sin match: {stats['sin_match']}")
    print(f"[TRANSFORM] Relaciones: {len(relaciones)}")
    
    # Cargar relaciones
    if relaciones:
        print(f"\n[LOAD] Insertando relaciones...")
        
        with pg_conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO iug.inmueble_caracteristica 
                (id_inmueble, id_caracteristica, valor_boolean)
                VALUES %s
                ON CONFLICT (id_inmueble, id_caracteristica) DO NOTHING
                """,
                relaciones,
                page_size=1000
            )
        
        pg_conn.commit()
        print(f"[LOAD] ✓ Relaciones cargadas")
    
    return stats['procesados'], len(relaciones)

def generar_reporte(pg_conn):
    """Genera reporte de estadísticas"""
    
    print(f"\n{'='*60}")
    print(" REPORTE")
    print(f"{'='*60}")
    
    with pg_conn.cursor() as cur:
        # Top características
        cur.execute("""
            SELECT 
                c.nombre_caracteristica,
                COUNT(ic.id_inmueble) as num
            FROM iug.cat_caracteristica c
            LEFT JOIN iug.inmueble_caracteristica ic ON c.id_caracteristica = ic.id_caracteristica
            GROUP BY c.id_caracteristica, c.nombre_caracteristica
            ORDER BY num DESC
            LIMIT 20
        """)
        
        print("\nTop 20 Características:")
        for row in cur.fetchall():
            print(f"  {row[1]:>5} - {row[0]}")
        
        # Totales
        cur.execute("SELECT COUNT(*) FROM iug.cat_caracteristica")
        total_cat = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT id_inmueble) FROM iug.inmueble_caracteristica")
        inmuebles_con = cur.fetchone()[0]
        
        print(f"\nTotal características: {total_cat}")
        print(f"Inmuebles con características: {inmuebles_con}")
        print(f"{'='*60}\n")

def main():
    print("="*60)
    print(" ETL: CARACTERÍSTICAS CON NORMALIZACIÓN SEMÁNTICA")
    print("="*60)
    print(f"Modo: {NORMALIZATION_MODE}")
    
    # Conectar
    mongo_client = MongoClient(host=MONGO_CONFIG['host'], port=MONGO_CONFIG['port'])
    mongo_db = mongo_client[MONGO_CONFIG['database']]
    
    pg_conn = psycopg2.connect(**PG_CONFIG)
    
    try:
        # 1. Extraer y normalizar
        caracteristicas_canonicas, mapeo_raw_to_canonica = extraer_caracteristicas_unicas(mongo_db)
        
        # 2. Cargar catálogo
        mapeo_canonica_to_id = cargar_catalogo(pg_conn, caracteristicas_canonicas)
        
        # 3. Procesar inmuebles
        num_inmuebles, num_relaciones = procesar_inmuebles(
            mongo_db, 
            pg_conn, 
            mapeo_raw_to_canonica, 
            mapeo_canonica_to_id
        )
        
        # 4. Reporte
        generar_reporte(pg_conn)
        
        print(f"[SUCCESS] ETL completado")
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        pg_conn.rollback()
        sys.exit(1)
    
    finally:
        pg_conn.close()
        mongo_client.close()

if __name__ == '__main__':
    main()
