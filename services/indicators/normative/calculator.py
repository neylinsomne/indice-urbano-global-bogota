"""
Normative Indicator Calculator - I_PNU

Calcula indicador de Potencial Normativo de Uso del Suelo (POT 555).

El cálculo está implementado en SQL (calcular_ipnu.sql),
este módulo provee utilidades Python para:
- Obtener I_PNU de inmuebles
- Analizar distribución por zonas POT
- Interpretar potencial normativo
"""

import psycopg2
from typing import Dict, Optional


def get_normative_score(id_inmueble: int, conn: psycopg2.extensions.connection) -> Optional[Dict]:
    """
    Obtiene score normativo (I_PNU) para un inmueble

    Args:
        id_inmueble: ID del inmueble
        conn: Conexión PostgreSQL

    Returns:
        dict con 'ipnu', 'tratamiento', 'edificabilidad', 'area_actividad'
        None si el inmueble no existe o no está en Bogotá
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                i.ipnu,
                t.nombre as tratamiento,
                e.rango as edificabilidad,
                a.codigo as area_actividad,
                a.nombre as area_actividad_nombre
            FROM iug.inmueble i
            LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
            LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
            LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
            WHERE i.id_inmueble = %s
        """, (id_inmueble,))

        row = cur.fetchone()
        if not row:
            return None

        return {
            'ipnu': float(row[0]) if row[0] else None,
            'tratamiento': row[1],
            'edificabilidad': row[2],
            'area_actividad_codigo': row[3],
            'area_actividad_nombre': row[4]
        }


def interpret_ipnu(ipnu: float) -> Dict[str, str]:
    """
    Interpreta el valor de I_PNU

    Args:
        ipnu: Valor del indicador (0-5)

    Returns:
        dict con 'categoria', 'label', 'descripcion'
    """
    if ipnu >= 4.5:
        return {
            'categoria': 'muy_alto',
            'label': 'Muy Alto',
            'descripcion': 'Desarrollo de torres/proyectos grandes. Máximo ROI potencial.'
        }
    elif ipnu >= 4.0:
        return {
            'categoria': 'alto',
            'label': 'Alto',
            'descripcion': 'Proyectos medianos/grandes. Buen potencial de valorización.'
        }
    elif ipnu >= 3.5:
        return {
            'categoria': 'medio_alto',
            'label': 'Medio-Alto',
            'descripcion': 'Desarrollo residencial/comercial estándar. Potencial sólido.'
        }
    elif ipnu >= 3.0:
        return {
            'categoria': 'medio',
            'label': 'Medio',
            'descripcion': 'Vivienda de densidad media. Crecimiento moderado.'
        }
    elif ipnu >= 2.5:
        return {
            'categoria': 'medio_bajo',
            'label': 'Medio-Bajo',
            'descripcion': 'Vivienda unifamiliar/bifamiliar. Limitaciones de altura.'
        }
    elif ipnu >= 2.0:
        return {
            'categoria': 'bajo',
            'label': 'Bajo',
            'descripcion': 'Zonas con restricciones. Inversión conservadora.'
        }
    else:
        return {
            'categoria': 'muy_bajo',
            'label': 'Muy Bajo',
            'descripcion': 'Conservación/protección. No recomendado para desarrollo.'
        }


def analyze_ipnu_distribution(conn: psycopg2.extensions.connection) -> Dict:
    """
    Analiza distribución de I_PNU en la ciudad

    Returns:
        Stats de distribución por tipo de inmueble y tratamiento
    """
    with conn.cursor() as cur:
        # Por tipo de inmueble
        cur.execute("""
            SELECT
                tipo_inmueble,
                COUNT(*) as n,
                ROUND(AVG(ipnu)::numeric, 2) as avg_ipnu,
                ROUND(MIN(ipnu)::numeric, 2) as min_ipnu,
                ROUND(MAX(ipnu)::numeric, 2) as max_ipnu,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ipnu)::numeric, 2) as median
            FROM iug.inmueble
            WHERE ipnu IS NOT NULL
            GROUP BY tipo_inmueble
            ORDER BY avg_ipnu DESC
        """)

        by_type = []
        for row in cur.fetchall():
            by_type.append({
                'tipo': row[0],
                'count': row[1],
                'avg': float(row[2]) if row[2] else None,
                'min': float(row[3]) if row[3] else None,
                'max': float(row[4]) if row[4] else None,
                'median': float(row[5]) if row[5] else None
            })

        # Por tratamiento urbanístico
        cur.execute("""
            SELECT
                t.nombre as tratamiento,
                COUNT(DISTINCT i.id_inmueble) as n_inmuebles,
                ROUND(AVG(i.ipnu)::numeric, 2) as avg_ipnu
            FROM iug.inmueble i
            JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
            WHERE i.ipnu IS NOT NULL
            GROUP BY t.nombre
            ORDER BY avg_ipnu DESC
        """)

        by_treatment = []
        for row in cur.fetchall():
            by_treatment.append({
                'tratamiento': row[0],
                'count': row[1],
                'avg_ipnu': float(row[2]) if row[2] else None
            })

        return {
            'by_type': by_type,
            'by_treatment': by_treatment
        }


def get_pot_zones_for_inmueble(id_inmueble: int, conn: psycopg2.extensions.connection) -> Optional[Dict]:
    """
    Obtiene todas las zonas POT que afectan a un inmueble

    Returns:
        dict con información completa de POT
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                t.codigo as tratamiento_codigo,
                t.nombre as tratamiento_nombre,
                t.tipo as tratamiento_tipo,
                e.codigo as edificabilidad_codigo,
                e.rango as edificabilidad_rango,
                e.pisos_min,
                e.pisos_max,
                a.codigo as actividad_codigo,
                a.nombre as actividad_nombre,
                u.codigo as upl_codigo,
                u.nombre as upl_nombre,
                u.localidad
            FROM iug.inmueble i
            LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
            LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
            LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
            LEFT JOIN iug.pot_upl u ON ST_Within(i.geom, u.geom)
            WHERE i.id_inmueble = %s
        """, (id_inmueble,))

        row = cur.fetchone()
        if not row:
            return None

        return {
            'tratamiento': {
                'codigo': row[0],
                'nombre': row[1],
                'tipo': row[2]
            },
            'edificabilidad': {
                'codigo': row[3],
                'rango': row[4],
                'pisos_min': row[5],
                'pisos_max': row[6]
            },
            'area_actividad': {
                'codigo': row[7],
                'nombre': row[8]
            },
            'upl': {
                'codigo': row[9],
                'nombre': row[10],
                'localidad': row[11]
            }
        }
