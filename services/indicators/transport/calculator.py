"""
Transport Indicator Calculator - Accesibilidad

Calcula indicador de transporte usando Gravity Model.

El cálculo está implementado en SQL (trg_inmueble_indicadores_raw),
este módulo provee utilidades Python para:
- Análisis de accesibilidad
- Visualización de isocronas
- Cálculo manual si se necesita fuera de triggers
"""

import psycopg2
from typing import Dict, List, Optional
import numpy as np


def get_transport_score(id_inmueble: int, conn: psycopg2.extensions.connection) -> Dict:
    """
    Obtiene score de transporte para un inmueble
    
    Returns:
        dict con 'score', 'n_sitp', 'n_transmilenio', etc.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                iacc as score,
                iacc_normalizado,
                (SELECT COUNT(*) 
                 FROM iug.osm_transport_point t
                 WHERE ST_DWithin(i.geom::geography, t.geom::geography, 1000)
                ) as n_sitp_1km,
                (SELECT COUNT(*) 
                 FROM iug.estacion_transmilenio tm
                 WHERE ST_DWithin(i.geom::geography, tm.geom::geography, 1000)
                ) as n_transmilenio_1km
            FROM iug.inmueble i
            WHERE id_inmueble = %s
        """, (id_inmueble,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            'score_raw': row[0],
            'score_normalized': row[1],
            'n_sitp_1km': row[2],
            'n_transmilenio_1km': row[3]
        }


def calculate_gravity_model(
    point_geom: str,  # WKT o EWKT
    conn: psycopg2.extensions.connection,
    radios: Dict[str, int] = None
) -> float:
    """
    Calcula gravity model para un punto específico
    
    Útil para calcular score sin insertar en BD.
    
    Args:
        point_geom: Geometría del punto (WKT/EWKT)
        conn: Conexión PostgreSQL
        radios: dict {'sitp': 800, 'transmilenio': 1500}
    
    Returns:
        float: Score gravity (sin normalizar)
    """
    if radios is None:
        radios = {'sitp': 800, 'transmilenio': 1500}
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT iug.calcular_score_gravity(%s::geometry, %s, %s)
        """, (point_geom, radios['sitp'], radios['transmilenio']))
        
        score = cur.fetchone()[0]
        return float(score) if score else 0.0


def get_nearby_transport(
    id_inmueble: int,
    conn: psycopg2.extensions.connection,
    radius_m: int = 1000
) -> Dict[str, List[Dict]]:
    """
    Obtiene transporte cercano a un inmueble
    
    Returns:
        {
            'sitp': [{name, distance_m}, ...],
            'transmilenio': [{name, distance_m}, ...]
        }
    """
    result = {'sitp': [], 'transmilenio': []}
    
    with conn.cursor() as cur:
        # SITP
        cur.execute("""
            SELECT 
                t.name,
                ST_Distance(i.geom::geography, t.geom::geography) as distance_m
            FROM iug.inmueble i
            CROSS JOIN LATERAL (
                SELECT name, geom
                FROM iug.osm_transport_point
                WHERE ST_DWithin(i.geom::geography, geom::geography, %s)
                ORDER BY geom::geography <-> i.geom::geography
                LIMIT 10
            ) t
            WHERE i.id_inmueble = %s
        """, (radius_m, id_inmueble))
        
        result['sitp'] = [
            {'name': row[0], 'distance_m': round(row[1], 1)}
            for row in cur.fetchall()
        ]
        
        # TransMilenio
        cur.execute("""
            SELECT 
                tm.nombre,
                ST_Distance(i.geom::geography, tm.geom::geography) as distance_m
            FROM iug.inmueble i
            CROSS JOIN LATERAL (
                SELECT nombre, geom
                FROM iug.estacion_transmilenio
                WHERE ST_DWithin(i.geom::geography, geom::geography, %s)
                ORDER BY geom::geography <-> i.geom::geography
                LIMIT 10
            ) tm
            WHERE i.id_inmueble = %s
        """, (radius_m, id_inmueble))
        
        result['transmilenio'] = [
            {'name': row[0], 'distance_m': round(row[1], 1)}
            for row in cur.fetchall()
        ]
    
    return result


def analyze_accessibility_distribution(conn: psycopg2.extensions.connection) -> Dict:
    """
    Analiza distribución de accesibilidad en la ciudad
    
    Returns:
        Stats de distribución por tipo de inmueble
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                tipo_inmueble,
                COUNT(*) as n,
                AVG(iacc) as avg_score,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY iacc) as median,
                MIN(iacc) as min_score,
                MAX(iacc) as max_score
            FROM iug.inmueble
            WHERE iacc IS NOT NULL AND tipo_inmueble IS NOT NULL
            GROUP BY tipo_inmueble
            ORDER BY avg_score DESC
        """)
        
        results = []
        for row in cur.fetchall():
            results.append({
                'tipo': row[0],
                'count': row[1],
                'avg': float(row[2]) if row[2] else None,
                'median': float(row[3]) if row[3] else None,
                'min': float(row[4]) if row[4] else None,
                'max': float(row[5]) if row[5] else None
            })
        
        return {'by_type': results}
