"""
Global Urban Indicator Calculator - I_URB

Calcula el Indicador Urbanístico Global como suma ponderada de:
- I_ACC (Accesibilidad)
- I_SEG (Seguridad)
- I_HED (Calidad Hedónica)
- I_PNU (Potencial Normativo)
"""

import psycopg2
from typing import Dict, List, Optional, Tuple
from .config import PESOS_ACTIVOS, NORMALIZATION, INTERPRETACION, ALERTAS


def calculate_iurb(
    iacc: Optional[float],
    iseg: Optional[float],
    ihed: Optional[float],
    ipnu: Optional[float],
    pesos: Dict[str, float] = None
) -> Optional[float]:
    """
    Calcula I_URB a partir de los indicadores individuales

    Args:
        iacc: Indicador de accesibilidad (0-5)
        iseg: Indicador de seguridad (0-5)
        ihed: Indicador hedónico (0-5)
        ipnu: Indicador normativo (0-5)
        pesos: Dict con pesos (default: PESOS_ACTIVOS)

    Returns:
        float: I_URB (0-5) o None si no hay suficientes datos
    """
    if pesos is None:
        pesos = PESOS_ACTIVOS

    # Construir lista de (valor, peso) para indicadores no-null
    valores_pesos = []
    if iacc is not None:
        valores_pesos.append((iacc, pesos['iacc']))
    if iseg is not None:
        valores_pesos.append((iseg, pesos['iseg']))
    if ihed is not None:
        valores_pesos.append((ihed, pesos['ihed']))
    if ipnu is not None:
        valores_pesos.append((ipnu, pesos['ipnu']))

    # Verificar mínimo de indicadores
    min_required = NORMALIZATION.get('min_indicators', 2)
    if len(valores_pesos) < min_required:
        return None

    # Calcular suma ponderada normalizada
    total_peso = sum(peso for _, peso in valores_pesos)
    if total_peso == 0:
        return None

    iurb = sum(valor * peso for valor, peso in valores_pesos) / total_peso

    # Clamp a rango 0-5
    return max(0.0, min(5.0, iurb))


def get_iurb_for_inmueble(id_inmueble: int, conn: psycopg2.extensions.connection) -> Optional[Dict]:
    """
    Obtiene I_URB y todos los sub-indicadores para un inmueble

    Args:
        id_inmueble: ID del inmueble
        conn: Conexión PostgreSQL

    Returns:
        dict con todos los indicadores e I_URB calculado
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                iacc,
                iseg,
                ihed,
                ipnu,
                idot,
                idim
            FROM iug.inmueble
            WHERE id_inmueble = %s
        """, (id_inmueble,))

        row = cur.fetchone()
        if not row:
            return None

        iacc = float(row[0]) if row[0] is not None else None
        iseg = float(row[1]) if row[1] is not None else None
        ihed = float(row[2]) if row[2] is not None else None
        ipnu = float(row[3]) if row[3] is not None else None
        idot = float(row[4]) if row[4] is not None else None
        idim = float(row[5]) if row[5] is not None else None

        iurb = calculate_iurb(iacc, iseg, ihed, ipnu)

        return {
            'id_inmueble': id_inmueble,
            'iurb': iurb,
            'iacc': iacc,
            'iseg': iseg,
            'ihed': ihed,
            'ipnu': ipnu,
            'idot': idot,
            'idim': idim,
            'interpretation': interpret_iurb(iurb) if iurb else None,
            'alerts': check_alerts(iacc, iseg, ihed, ipnu)
        }


def interpret_iurb(iurb: float) -> Dict[str, str]:
    """
    Interpreta el valor de I_URB

    Args:
        iurb: Valor del indicador (0-5)

    Returns:
        dict con 'categoria', 'label', 'descripcion'
    """
    for categoria, config in INTERPRETACION.items():
        if config['min'] <= iurb < config['max']:
            return {
                'categoria': categoria,
                'label': config['label'],
                'descripcion': config['descripcion']
            }

    # Default: excelente si >= 5.0
    return {
        'categoria': 'excelente',
        'label': 'Excelente',
        'descripcion': 'Ubicación premium. Alto potencial de desarrollo y calidad de vida.'
    }


def check_alerts(
    iacc: Optional[float],
    iseg: Optional[float],
    ihed: Optional[float],
    ipnu: Optional[float]
) -> List[str]:
    """
    Verifica si hay alertas en algún indicador

    Returns:
        Lista de mensajes de alerta
    """
    alertas = []

    if iseg is not None and iseg < ALERTAS['seguridad_baja']['threshold']:
        alertas.append(ALERTAS['seguridad_baja']['message'])

    if iacc is not None and iacc < ALERTAS['accesibilidad_baja']['threshold']:
        alertas.append(ALERTAS['accesibilidad_baja']['message'])

    if ipnu is not None and ipnu < ALERTAS['potencial_muy_bajo']['threshold']:
        alertas.append(ALERTAS['potencial_muy_bajo']['message'])

    return alertas


def calculate_iurb_bulk(conn: psycopg2.extensions.connection, limite: int = None) -> int:
    """
    Calcula I_URB para todos los inmuebles y lo almacena en la BD

    Args:
        conn: Conexión PostgreSQL
        limite: Número máximo de inmuebles a actualizar (None = todos)

    Returns:
        Número de inmuebles actualizados
    """
    with conn.cursor() as cur:
        # Verificar si columna iurb existe
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'iug'
            AND table_name = 'inmueble'
            AND column_name = 'iurb'
        """)

        if not cur.fetchone():
            # Crear columna si no existe
            cur.execute("ALTER TABLE iug.inmueble ADD COLUMN iurb NUMERIC(3,2)")
            conn.commit()
            print("Columna iurb creada en iug.inmueble")

        # Calcular I_URB usando la fórmula ponderada
        pesos = PESOS_ACTIVOS
        query = f"""
            UPDATE iug.inmueble
            SET iurb = (
                COALESCE(iacc * {pesos['iacc']}, 0) +
                COALESCE(iseg * {pesos['iseg']}, 0) +
                COALESCE(ihed * {pesos['ihed']}, 0) +
                COALESCE(ipnu * {pesos['ipnu']}, 0)
            ) / (
                (CASE WHEN iacc IS NOT NULL THEN {pesos['iacc']} ELSE 0 END) +
                (CASE WHEN iseg IS NOT NULL THEN {pesos['iseg']} ELSE 0 END) +
                (CASE WHEN ihed IS NOT NULL THEN {pesos['ihed']} ELSE 0 END) +
                (CASE WHEN ipnu IS NOT NULL THEN {pesos['ipnu']} ELSE 0 END)
            )
            WHERE (
                (CASE WHEN iacc IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN iseg IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN ihed IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN ipnu IS NOT NULL THEN 1 ELSE 0 END)
            ) >= {NORMALIZATION['min_indicators']}
        """

        if limite:
            query += f" LIMIT {limite}"

        cur.execute(query)
        count = cur.rowcount
        conn.commit()

        return count


def analyze_iurb_distribution(conn: psycopg2.extensions.connection) -> Dict:
    """
    Analiza la distribución de I_URB en la base de datos

    Returns:
        Estadísticas de distribución
    """
    with conn.cursor() as cur:
        # Estadísticas generales
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(iurb) as con_iurb,
                ROUND(AVG(iurb)::numeric, 2) as promedio,
                ROUND(STDDEV(iurb)::numeric, 2) as desviacion,
                ROUND(MIN(iurb)::numeric, 2) as minimo,
                ROUND(MAX(iurb)::numeric, 2) as maximo,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as mediana,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY iurb)::numeric, 2) as p75
            FROM iug.inmueble
        """)

        row = cur.fetchone()
        general = {
            'total_inmuebles': row[0],
            'con_iurb': row[1],
            'cobertura_pct': round(row[1] / row[0] * 100, 1) if row[0] > 0 else 0,
            'promedio': float(row[2]) if row[2] else None,
            'desviacion': float(row[3]) if row[3] else None,
            'minimo': float(row[4]) if row[4] else None,
            'maximo': float(row[5]) if row[5] else None,
            'p25': float(row[6]) if row[6] else None,
            'mediana': float(row[7]) if row[7] else None,
            'p75': float(row[8]) if row[8] else None
        }

        # Distribución por categoría
        cur.execute("""
            SELECT
                CASE
                    WHEN iurb >= 4.5 THEN 'Excelente'
                    WHEN iurb >= 4.0 THEN 'Muy Bueno'
                    WHEN iurb >= 3.5 THEN 'Bueno'
                    WHEN iurb >= 3.0 THEN 'Regular'
                    WHEN iurb >= 2.5 THEN 'Por Debajo del Promedio'
                    WHEN iurb >= 2.0 THEN 'Deficiente'
                    ELSE 'Muy Deficiente'
                END as categoria,
                COUNT(*) as cantidad,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as porcentaje
            FROM iug.inmueble
            WHERE iurb IS NOT NULL
            GROUP BY categoria
            ORDER BY MIN(iurb) DESC
        """)

        categorias = []
        for row in cur.fetchall():
            categorias.append({
                'categoria': row[0],
                'cantidad': row[1],
                'porcentaje': float(row[2])
            })

        # Por tipo de inmueble
        cur.execute("""
            SELECT
                tipo_inmueble,
                COUNT(*) as n,
                ROUND(AVG(iurb)::numeric, 2) as avg_iurb
            FROM iug.inmueble
            WHERE iurb IS NOT NULL AND tipo_inmueble IS NOT NULL
            GROUP BY tipo_inmueble
            ORDER BY avg_iurb DESC
        """)

        por_tipo = []
        for row in cur.fetchall():
            por_tipo.append({
                'tipo': row[0],
                'cantidad': row[1],
                'promedio': float(row[2]) if row[2] else None
            })

        return {
            'general': general,
            'categorias': categorias,
            'por_tipo': por_tipo
        }


def get_top_inmuebles(
    conn: psycopg2.extensions.connection,
    limit: int = 10,
    order_by: str = 'iurb'
) -> List[Dict]:
    """
    Obtiene los inmuebles con mejor I_URB

    Args:
        conn: Conexión PostgreSQL
        limit: Número de resultados
        order_by: Campo para ordenar ('iurb', 'iacc', 'iseg', etc.)

    Returns:
        Lista de inmuebles ordenados
    """
    valid_fields = ['iurb', 'iacc', 'iseg', 'ihed', 'ipnu']
    if order_by not in valid_fields:
        order_by = 'iurb'

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                id_inmueble,
                ubicacion,
                tipo_inmueble,
                precio,
                iurb,
                iacc,
                iseg,
                ihed,
                ipnu
            FROM iug.inmueble
            WHERE {order_by} IS NOT NULL
            ORDER BY {order_by} DESC
            LIMIT %s
        """, (limit,))

        results = []
        for row in cur.fetchall():
            results.append({
                'id_inmueble': row[0],
                'ubicacion': row[1],
                'tipo': row[2],
                'precio': row[3],
                'iurb': float(row[4]) if row[4] else None,
                'iacc': float(row[5]) if row[5] else None,
                'iseg': float(row[6]) if row[6] else None,
                'ihed': float(row[7]) if row[7] else None,
                'ipnu': float(row[8]) if row[8] else None
            })

        return results
