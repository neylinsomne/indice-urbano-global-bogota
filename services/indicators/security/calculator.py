"""
Security Indicator Calculator - Seguridad Objetiva

Calcula indicador de seguridad usando:
- AHP pesos de criminalidad
- Proximidad a CAI
- Análisis sectores policiales

El cálculo está implementado en SQL (trg_inmueble_seguridad),
este módulo provee utilidades Python para análisis.
"""

import psycopg2
from typing import Dict, List
import numpy as np


def get_security_score(id_inmueble: int, conn: psycopg2.extensions.connection) -> Dict:
    """
    Obtiene score de seguridad para un inmueble
    
    Returns:
        dict con 'score', 'crimen_score', 'cai_score', 'sector'
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                iseg as score,
                iseg_normalizado,
                id_sector_policia,
                (SELECT nombre 
                 FROM iug.sectores_policia sp 
                 WHERE sp.id = i.id_sector_policia
                ) as nombre_sector,
                (SELECT MIN(ST_Distance(i.geom::geography, c.geom::geography))
                 FROM iug.cai c
                ) as dist_cai_m
            FROM iug.inmueble i
            WHERE id_inmueble = %s
        """, (id_inmueble,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            'score_raw': row[0],
            'score_normalized': row[1],
            'sector_id': row[2],
            'sector_nombre': row[3],
            'distancia_cai_m': round(row[4], 1) if row[4] else None
        }


def get_crime_stats_by_sector(conn: psycopg2.extensions.connection) -> List[Dict]:
    """
    Obtiene estadísticas de crimen por sector policial
    
    Returns:
        Lista de sectores con stats de crimen
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id,
                nombre,
                homicidios,
                delitos_sexuales,
                hurto_personas,
                otros_delitos,
                ahp_crimen,
                score_seguridad
            FROM iug.sectores_policia
            WHERE ahp_crimen IS NOT NULL
            ORDER BY score_seguridad DESC
        """)
        
        results = []
        for row in cur.fetchall():
            results.append({
                'id': row[0],
                'nombre': row[1],
                'homicidios': row[2],
                'delitos_sexuales': row[3],
                'hurto_personas': row[4],
                'otros_delitos': row[5],
                'ahp_score': float(row[6]) if row[6] else None,
                'seguridad_score': float(row[7]) if row[7] else None
            })
        
        return results


def analyze_security_distribution(conn: psycopg2.extensions.connection) -> Dict:
    """
    Analiza distribución de seguridad en la ciudad
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                tipo_inmueble,
                COUNT(*) as n,
                AVG(iseg) as avg_score,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY iseg) as median
            FROM iug.inmueble
            WHERE iseg IS NOT NULL
            GROUP BY tipo_inmueble
            ORDER BY avg_score DESC
        """)
        
        results = []
        for row in cur.fetchall():
            results.append({
                'tipo': row[0],
                'count': row[1],
                'avg': float(row[2]) if row[2] else None,
                'median': float(row[3]) if row[3] else None
            })
        
        return {'by_type': results}
