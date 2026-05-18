"""
I_Dot Calculator - Indicador de Dotación/Amenities

Calcula score basado en conteo ponderado de características del inmueble.

Fórmula:
    Score_Dot = Σ(ω_k · d_k)  para k=1 a m
    
Donde:
- ω_k: Peso del amenity k (configurado en weights.py)
- d_k: Variable dummy (1 si tiene amenity k, 0 si no)
- m: Total de amenities

Normalización:
    I_Dot = 5 × (Score_Dot / max_score_posible)
"""

import psycopg2
from typing import Dict, List, Optional


def get_amenity_weights(conn: psycopg2.extensions.connection) -> Dict[int, float]:
    """
    Obtiene pesos de amenities desde la base de datos
    
    Returns:
        dict {id_caracteristica: peso}
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id_caracteristica, peso 
            FROM iug.pesos_amenities
            WHERE activo = true
        """)
        
        weights = {row[0]: row[1] for row in cur.fetchall()}
    
    return weights


def calculate_amenities_score(
    id_inmueble: int,
    conn: psycopg2.extensions.connection,
    weights: Optional[Dict[int, float]] = None
) -> Dict:
    """
    Calcula score de amenities para un inmueble
    
    Args:
        id_inmueble: ID del inmueble
        conn: Conexión a PostgreSQL
        weights: Pesos de amenities (opcional, se obtiene de BD si no se provee)
    
    Returns:
        dict con 'score_raw', 'score_normalized', 'amenities_list', 'n_amenities'
    """
    # Obtener pesos si no se proveen
    if weights is None:
        weights = get_amenity_weights(conn)
    
    # Obtener características del inmueble
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ic.id_caracteristica, c.nombre_caracteristica, ic.valor_boolean
            FROM iug.inmueble_caracteristica ic
            JOIN iug.cat_caracteristica c ON ic.id_caracteristica = c.id_caracteristica
            WHERE ic.id_inmueble = %s
              AND ic.valor_boolean = true
        """, (id_inmueble,))
        
        inmueble_amenities = cur.fetchall()
    
    # Calcular suma ponderada
    score_raw = 0.0
    amenities_list = []
    
    for id_caract, nombre, valor in inmueble_amenities:
        peso = weights.get(id_caract, 1.0)  # Default peso = 1 si no está configurado
        
        if valor:  # Solo sumar si tiene el amenity
            score_raw += peso
            amenities_list.append({
                'id': id_caract,
                'nombre': nombre,
                'peso': peso
            })
    
    # Normalizar: I_Dot = 5 × (score / max_score)
    # max_score = suma de todos los pesos disponibles
    max_score = sum(weights.values()) if weights else 1.0
    
    score_normalized = (5.0 * score_raw / max_score) if max_score > 0 else 0.0
    
    # Clip a rango [0, 5]
    score_normalized = max(0.0, min(5.0, score_normalized))
    
    return {
        'score_raw': score_raw,
        'score_normalized': score_normalized,
        'max_score_possible': max_score,
        'amenities_list': amenities_list,
        'n_amenities': len(amenities_list)
    }


def calculate_batch_amenities(
    conn: psycopg2.extensions.connection,
    limit: Optional[int] = None
) -> Dict[int, Dict]:
    """
    Calcula scores de amenities para múltiples inmuebles
    
    Args:
        conn: Conexión a PostgreSQL
        limit: Límite de inmuebles a procesar (None = todos)
    
    Returns:
        dict {id_inmueble: resultado_calculate_amenities_score}
    """
    # Obtener pesos una sola vez
    weights = get_amenity_weights(conn)
    
    # Obtener todos los inmuebles con características
    with conn.cursor() as cur:
        query = """
            SELECT DISTINCT id_inmueble
            FROM iug.inmueble_caracteristica
            WHERE valor_boolean = true
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cur.execute(query)
        inmueble_ids = [row[0] for row in cur.fetchall()]
    
    # Calcular score para cada uno
    results = {}
    for id_inmueble in inmueble_ids:
        try:
            result = calculate_amenities_score(id_inmueble, conn, weights)
            results[id_inmueble] = result
        except Exception as e:
            print(f"Error processing {id_inmueble}: {e}")
    
    return results


def save_amenities_scores(
    results: Dict[int, Dict],
    conn: psycopg2.extensions.connection
):
    """
    Guarda scores de amenities en la base de datos
    
    Args:
        results: Output de calculate_batch_amenities
        conn: Conexión a PostgreSQL
    """
    with conn.cursor() as cur:
        for id_inmueble, result in results.items():
            cur.execute("""
                INSERT INTO iug.indicador_dotacion_raw (
                    id_inmueble,
                    score_amenities_raw,
                    n_amenities,
                    amenities_list
                ) VALUES (
                    %s, %s, %s, %s
                )
                ON CONFLICT (id_inmueble) DO UPDATE SET
                    score_amenities_raw = EXCLUDED.score_amenities_raw,
                    n_amenities = EXCLUDED.n_amenities,
                    amenities_list = EXCLUDED.amenities_list,
                    fecha_calculo = now()
            """, (
                id_inmueble,
                result['score_raw'],
                result['n_amenities'],
                [a['nombre'] for a in result['amenities_list']]
            ))
    
    conn.commit()
