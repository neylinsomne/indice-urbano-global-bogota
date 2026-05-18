"""
Servicio ACM (Análisis Comparativo de Mercado)

Selecciona comparables, aplica homologación y calcula estadísticas
siguiendo la metodología estándar de avalúos inmobiliarios en Colombia.
Funciona para cualquier ciudad disponible en la base de datos.
"""
import math
import statistics
import datetime
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Factor de descuento por oferta (precio listado vs precio real de mercado)
FACTOR_OFERTA = 0.95

# Jerarquía de estados para calcular factor de conservación
ESTADO_JERARQUIA = {
    'Remodelado': 5,
    'Nuevos': 5,
    'Buen estado': 4,
    'En construcción': 3,
    'Usados': 3,
    'Sobre planos': 3,
    'Para remodelar': 1,
}

# Factor de conservación según diferencia de jerarquía (sujeto - comparable)
FACTOR_CONSERVACION_POR_DIFF = {
    -4: 0.85, -3: 0.88, -2: 0.92, -1: 0.95,
    0: 1.00,
    1: 1.05, 2: 1.10, 3: 1.15, 4: 1.20,
}

# Reconstrucción de URLs por fuente
URL_TEMPLATES = {
    'finca_raiz': 'https://www.fincaraiz.com.co/{codigo}',
    'habi': 'https://habi.co/inmueble/{codigo}',
    'metrocuadrado': 'https://www.metrocuadrado.com/inmueble/{codigo}',
}


def build_listing_url(pagina: str, codigo_fuente: str) -> str:
    """Reconstruye la URL del anuncio original a partir de pagina + codigo_fuente."""
    if not pagina or not codigo_fuente:
        return ''
    template = URL_TEMPLATES.get(pagina, '')
    if template:
        return template.format(codigo=codigo_fuente)
    return ''


def _extract_ciudad(ubicacion: str) -> str:
    """
    Extrae la ciudad del campo ubicacion.
    Formato típico: 'Barrio, Ciudad, Departamento'
    """
    if not ubicacion:
        return ''
    parts = [p.strip() for p in ubicacion.split(',')]
    if len(parts) >= 2:
        return parts[1]  # "Medellín", "Bogotá", etc.
    return parts[0]


def _get_factor_conservacion(estado_comparable: str, estado_sujeto: str,
                             area_comparable: float, area_sujeto: float) -> float:
    """Calcula factor de conservación/remodelación/entorno/área."""
    nivel_comp = ESTADO_JERARQUIA.get(estado_comparable or '', 3)
    nivel_suj = ESTADO_JERARQUIA.get(estado_sujeto or '', 3)
    diff = max(-4, min(4, nivel_suj - nivel_comp))
    factor = FACTOR_CONSERVACION_POR_DIFF.get(diff, 1.0)

    # Ajuste por diferencia de área (si >15% de diferencia, ±5%)
    if area_sujeto and area_comparable and area_sujeto > 0:
        ratio_area = area_comparable / area_sujeto
        if ratio_area > 1.15:
            factor *= 0.95
        elif ratio_area < 0.85:
            factor *= 1.05

    return round(factor, 2)


async def fetch_subject(conn: asyncpg.Connection, id_inmueble: int) -> dict:
    """Obtiene los datos del inmueble sujeto del estudio."""
    row = await conn.fetchrow("""
        SELECT
            id_inmueble, tipo_inmueble, ubicacion,
            estado, edad, area_construida, precio, image, pagina,
            inmobiliaria, fecha, estrato, habitaciones, banos,
            descripcion, codigo_fuente,
            ST_Y(geom) as latitud, ST_X(geom) as longitud
        FROM iug.inmueble
        WHERE id_inmueble = $1
    """, id_inmueble)

    if not row:
        raise ValueError(f"Inmueble {id_inmueble} no encontrado")

    d = dict(row)
    d['ciudad'] = _extract_ciudad(d.get('ubicacion'))
    d['url_anuncio'] = build_listing_url(d.get('pagina'), d.get('codigo_fuente'))
    return d


async def fetch_comparables(conn: asyncpg.Connection, subject: dict, n: int = 4) -> list:
    """
    Busca N propiedades comparables al sujeto.
    Filtra por misma ciudad (extraída de ubicacion), mismo tipo,
    rango de área/precio. Ordena por distancia geográfica.
    """
    area = float(subject['area_construida'] or 0)
    precio = float(subject['precio'] or 0)
    has_geom = subject['latitud'] is not None and subject['longitud'] is not None
    ciudad = subject.get('ciudad', '')

    if area <= 0 or precio <= 0:
        raise ValueError("El inmueble sujeto no tiene area o precio valido")

    if not ciudad:
        raise ValueError("No se pudo determinar la ciudad del inmueble sujeto")

    # Intentar con márgenes estrechos primero, luego ampliar
    margins = [
        (0.20, 0.30),
        (0.35, 0.45),
        (0.50, 0.60),
    ]

    rows = []
    for margin_area, margin_precio in margins:
        area_min = area * (1 - margin_area)
        area_max = area * (1 + margin_area)
        precio_min = precio * (1 - margin_precio)
        precio_max = precio * (1 + margin_precio)

        # Filtro por ciudad: buscar en el campo ubicacion
        ciudad_pattern = f"%, {ciudad},%"

        if has_geom:
            rows = await conn.fetch("""
                SELECT
                    id_inmueble, tipo_inmueble, ubicacion,
                    estado, edad, area_construida, precio, pagina,
                    inmobiliaria, fecha, image, codigo_fuente,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_Point($8, $7), 4326)::geography
                    ) as distancia_m
                FROM iug.inmueble
                WHERE id_inmueble != $1
                  AND tipo_inmueble = $2
                  AND ubicacion ILIKE $3
                  AND area_construida BETWEEN $4 AND $5
                  AND precio BETWEEN $6 AND $9
                  AND precio IS NOT NULL
                  AND area_construida IS NOT NULL
                  AND geom IS NOT NULL
                  AND is_outlier = FALSE
                ORDER BY ST_Distance(
                    geom::geography,
                    ST_SetSRID(ST_Point($8, $7), 4326)::geography
                )
                LIMIT $10
            """, subject['id_inmueble'], subject['tipo_inmueble'],
                ciudad_pattern,
                area_min, area_max, precio_min,
                subject['latitud'], subject['longitud'],
                precio_max, n)
        else:
            rows = await conn.fetch("""
                SELECT
                    id_inmueble, tipo_inmueble, ubicacion,
                    estado, edad, area_construida, precio, pagina,
                    inmobiliaria, fecha, image, codigo_fuente,
                    0::float as distancia_m
                FROM iug.inmueble
                WHERE id_inmueble != $1
                  AND tipo_inmueble = $2
                  AND ubicacion ILIKE $3
                  AND area_construida BETWEEN $4 AND $5
                  AND precio BETWEEN $6 AND $7
                  AND precio IS NOT NULL
                  AND area_construida IS NOT NULL
                  AND is_outlier = FALSE
                ORDER BY ABS(area_construida - $8) + ABS(precio - $9) / 1000000
                LIMIT $10
            """, subject['id_inmueble'], subject['tipo_inmueble'],
                ciudad_pattern,
                area_min, area_max, precio_min, precio_max,
                area, precio, n)

        if len(rows) >= n:
            break

    result = []
    for r in rows:
        d = dict(r)
        d['url_anuncio'] = build_listing_url(d.get('pagina'), d.get('codigo_fuente'))
        result.append(d)
    return result


async def fetch_comparables_dbscan(conn: asyncpg.Connection, subject: dict, n: int = 4) -> list:
    """
    Busca N comparables usando DBSCAN (clustering espacial + atributos).
    1. Obtiene todos los inmuebles del mismo tipo en la misma ciudad
    2. Normaliza features (precio/m2, area, lat, lon)
    3. Aplica DBSCAN para encontrar el cluster del sujeto
    4. Selecciona los N vecinos más cercanos dentro del cluster
    """
    import numpy as np
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler

    area = float(subject['area_construida'] or 0)
    precio = float(subject['precio'] or 0)
    has_geom = subject['latitud'] is not None and subject['longitud'] is not None

    if area <= 0 or precio <= 0:
        raise ValueError("El inmueble sujeto no tiene area o precio valido")

    ciudad = subject.get('ciudad', '')
    if not ciudad:
        raise ValueError("No se pudo determinar la ciudad del inmueble sujeto")

    ciudad_pattern = f"%, {ciudad},%"

    # Traer todos los inmuebles candidatos de la misma ciudad y tipo
    rows = await conn.fetch("""
        SELECT
            id_inmueble, tipo_inmueble, ubicacion,
            estado, edad, area_construida, precio, pagina,
            inmobiliaria, fecha, image, codigo_fuente,
            ST_Y(geom) as lat, ST_X(geom) as lon
        FROM iug.inmueble
        WHERE tipo_inmueble = $1
          AND ubicacion ILIKE $2
          AND precio IS NOT NULL
          AND area_construida IS NOT NULL
          AND area_construida > 0
          AND geom IS NOT NULL
          AND is_outlier = FALSE
    """, subject['tipo_inmueble'], ciudad_pattern)

    if len(rows) < n + 1:
        raise ValueError(
            f"Solo hay {len(rows)} inmuebles de tipo {subject['tipo_inmueble']} "
            f"en {ciudad}. Se necesitan al menos {n + 1} para DBSCAN."
        )

    # Preparar features: precio/m2, area, lat, lon
    all_data = []
    subject_idx = None
    for i, r in enumerate(rows):
        a = float(r['area_construida'])
        p = float(r['precio'])
        precio_m2 = p / a
        all_data.append({
            'row': dict(r),
            'features': [precio_m2, a, float(r['lat']), float(r['lon'])]
        })
        if r['id_inmueble'] == subject['id_inmueble']:
            subject_idx = i

    # Si el sujeto no está en el resultado (puede no tener geom en la query original)
    if subject_idx is None and has_geom:
        subject_precio_m2 = precio / area
        all_data.append({
            'row': dict(subject),
            'features': [subject_precio_m2, area, subject['latitud'], subject['longitud']]
        })
        subject_idx = len(all_data) - 1

    if subject_idx is None:
        raise ValueError("El inmueble sujeto no tiene coordenadas para DBSCAN")

    # Normalizar features
    X = np.array([d['features'] for d in all_data])
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # DBSCAN con eps adaptativo
    # Probar eps desde 0.5 hasta 2.0 para encontrar un cluster con suficientes miembros
    subject_label = -1
    cluster_indices = []
    for eps in [0.5, 0.8, 1.0, 1.3, 1.6, 2.0]:
        db = DBSCAN(eps=eps, min_samples=3)
        labels = db.fit_predict(X_scaled)
        subject_label = labels[subject_idx]

        if subject_label == -1:
            continue

        # Encontrar todos los puntos en el mismo cluster (excluyendo el sujeto)
        cluster_indices = [
            i for i in range(len(labels))
            if labels[i] == subject_label and i != subject_idx
        ]

        if len(cluster_indices) >= n:
            break

    if len(cluster_indices) < 2:
        # Fallback: usar los N vecinos más cercanos en el espacio normalizado
        logger.warning("DBSCAN no encontro cluster suficiente, usando KNN fallback")
        from sklearn.neighbors import NearestNeighbors
        knn = NearestNeighbors(n_neighbors=n + 1)
        knn.fit(X_scaled)
        distances, indices = knn.kneighbors(X_scaled[subject_idx].reshape(1, -1))
        cluster_indices = [idx for idx in indices[0] if idx != subject_idx][:n]

    # Ordenar por distancia euclidiana al sujeto en el espacio normalizado
    subject_vec = X_scaled[subject_idx]
    distances = []
    for idx in cluster_indices:
        dist = np.linalg.norm(X_scaled[idx] - subject_vec)
        distances.append((idx, dist))
    distances.sort(key=lambda x: x[1])

    # Tomar los N más cercanos
    result = []
    for idx, dist in distances[:n]:
        d = all_data[idx]['row']
        d['url_anuncio'] = build_listing_url(d.get('pagina'), d.get('codigo_fuente'))
        d['distancia_m'] = round(dist, 4)
        result.append(d)

    return result


def compute_homologation(comparable: dict, subject: dict) -> dict:
    """Aplica factores de homologación a un comparable."""
    precio = float(comparable['precio'])
    area = float(comparable['area_construida'])
    precio_m2 = precio / area

    factor_cons = _get_factor_conservacion(
        comparable.get('estado'), subject.get('estado'),
        area, float(subject['area_construida'] or 0)
    )

    precio_m2_hom = precio_m2 * FACTOR_OFERTA * factor_cons

    return {
        'precio_m2': round(precio_m2, 0),
        'factor_oferta': FACTOR_OFERTA,
        'factor_conservacion': factor_cons,
        'precio_m2_hom': round(precio_m2_hom, 0),
    }


def compute_statistics(prices_hom: list) -> dict:
    """
    Calcula estadisticas del ACM:
    promedio, desviacion tipica MUESTRAL, CV,
    intervalo de confianza 90% con t-Student, asimetria.

    Usa t-Student en vez de z-normal porque n es tipicamente 2-6.
    Con n=3, t_{2,0.95}=2.920 vs z=1.645 (IC 77% mas ancho y realista).
    """
    from scipy import stats as sp_stats

    n = len(prices_hom)
    if n == 0:
        raise ValueError("No hay precios homologados para calcular estadisticas")

    mean = statistics.mean(prices_hom)

    # Desviacion tipica MUESTRAL (dividir por n-1, no n)
    if n > 1:
        stdev = math.sqrt(sum((x - mean) ** 2 for x in prices_hom) / (n - 1))
    else:
        stdev = 0.0

    cv = (stdev / mean) if mean > 0 else 0.0

    # t-Student para IC 90% (bilateral) con n-1 grados de libertad
    if n > 1:
        t_value = float(sp_stats.t.ppf(0.95, df=n - 1))
    else:
        t_value = 0.0
    margin = t_value * (stdev / math.sqrt(n)) if n > 1 else 0.0
    ci_upper = mean + margin
    ci_lower = mean - margin

    # Asimetria: solo reportar si n >= 8 (con menos es no interpretable)
    skewness = None
    if stdev > 0 and n >= 8:
        skew_num = sum((x - mean) ** 3 for x in prices_hom) / (n - 1)
        skewness = skew_num / (stdev ** 3)

    result = {
        'promedio_m2': round(mean, 0),
        'desviacion_tipica': round(stdev, 0),
        'coeficiente_variacion': round(cv * 100, 2),
        'limite_superior': round(ci_upper, 0),
        'limite_inferior': round(ci_lower, 0),
        't_student': round(t_value, 4),
        'grados_libertad': n - 1,
        'n_comparables': n,
    }

    if skewness is not None:
        result['coeficiente_asimetria'] = round(skewness * 100, 2)
    else:
        result['coeficiente_asimetria'] = None
        if n < 8:
            result['nota_asimetria'] = (
                f'Asimetria no reportada: n={n} < 8 (no interpretable)'
            )

    return result


def compute_price_objectives(stats: dict, area: float) -> dict:
    """Calcula precios objetivo, mínimo y máximo."""
    return {
        'precio_objetivo': round(stats['promedio_m2'] * area, -3),
        'precio_minimo': round(stats['limite_inferior'] * area, -3),
        'precio_maximo': round(stats['limite_superior'] * area, -3),
        'rango_objetivo': '6 a 12 meses',
        'rango_minimo': '0 a 6 meses',
        'rango_maximo': '12 a 24 meses',
    }


async def build_acm_data(conn: asyncpg.Connection, id_inmueble: int,
                         metodo: str = 'clasico') -> dict:
    """
    Construye el payload completo del ACM para un inmueble.
    Funciona para cualquier ciudad disponible en la base de datos.

    Args:
        metodo: 'clasico' (filtro por rango precio/area) o 'dbscan' (clustering)
    """
    subject = await fetch_subject(conn, id_inmueble)

    if metodo == 'dbscan':
        comparables = await fetch_comparables_dbscan(conn, subject, n=4)
    else:
        comparables = await fetch_comparables(conn, subject, n=4)

    if len(comparables) < 2:
        raise ValueError(
            f"Solo se encontraron {len(comparables)} comparables para "
            f"{subject.get('tipo_inmueble')} en {subject.get('ciudad')}. "
            f"Se necesitan al menos 2 para generar el estudio."
        )

    rows = []
    prices_hom = []
    for i, comp in enumerate(comparables, 1):
        hom = compute_homologation(comp, subject)
        rows.append({
            'numero': i,
            'comparable': comp,
            'homologation': hom,
        })
        prices_hom.append(hom['precio_m2_hom'])

    stats = compute_statistics(prices_hom)
    area = float(subject['area_construida'])
    objectives = compute_price_objectives(stats, area)

    return {
        'subject': subject,
        'comparables': rows,
        'statistics': stats,
        'objectives': objectives,
        'total_comparables': len(comparables),
        'metodo': metodo,
        'generated_at': datetime.date.today().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Geocodificación y ACM desde dirección (para endpoint manual)
# ─────────────────────────────────────────────────────────────────────────────

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def geocode_address(address: str, ciudad: str) -> tuple[Optional[float], Optional[float]]:
    """
    Convierte una dirección a coordenadas lat/lon usando la API de Google Maps.
    Retorna (lat, lon) o (None, None) si falla o no hay API key.
    """
    if not GOOGLE_API_KEY:
        return None, None

    query = f"{address}, {ciudad}, Colombia"
    try:
        import httpx
        params = {"address": query, "key": GOOGLE_API_KEY}
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(_GEOCODE_URL, params=params)
            r.raise_for_status()
            data = r.json()

        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"])
    except Exception as e:
        logger.warning(f"Geocodificación falló para '{query}': {e}")

    return None, None


async def build_acm_from_address(
    conn: asyncpg.Connection,
    subject_data: dict,
    n: int = 4,
) -> dict:
    """
    Construye el ACM para un inmueble ingresado manualmente (sin ID de DB).

    Geocodifica la dirección y busca comparables en la base de datos.
    Si la geocodificación falla, busca por ciudad y tipo sin distancia.

    Args:
        subject_data: dict con keys:
            tipo_inmueble, ubicacion, ciudad, area_construida, precio,
            estado (opt), edad (opt), estrato (opt), image (opt), url_anuncio (opt)
    """
    area = float(subject_data.get("area_construida") or 0)
    precio = float(subject_data.get("precio") or 0)

    if area <= 0 or precio <= 0:
        raise ValueError("El inmueble sujeto debe tener área y precio válidos.")

    ciudad = subject_data.get("ciudad", "").strip()
    ubicacion = subject_data.get("ubicacion", "").strip()

    if not ciudad:
        ciudad = _extract_ciudad(ubicacion)
    if not ciudad:
        raise ValueError("Debes especificar la ciudad del inmueble.")

    # Geocodificar
    lat, lon = await geocode_address(ubicacion, ciudad)

    # Construir subject virtual (id_inmueble=0 no existe en la DB)
    subject = {
        "id_inmueble": 0,
        "tipo_inmueble": subject_data.get("tipo_inmueble", "Apartamento"),
        "ubicacion": ubicacion or f"Barrio, {ciudad}, Colombia",
        "ciudad": ciudad,
        "estado": subject_data.get("estado") or "Buen estado",
        "edad": subject_data.get("edad"),
        "area_construida": area,
        "precio": precio,
        "estrato": subject_data.get("estrato"),
        "image": subject_data.get("image") or "",
        "url_anuncio": subject_data.get("url_anuncio") or "",
        "pagina": None,
        "codigo_fuente": None,
        "fecha": None,
        "latitud": lat,
        "longitud": lon,
        "habitaciones": subject_data.get("habitaciones"),
        "banos": subject_data.get("banos"),
        "descripcion": subject_data.get("descripcion"),
    }

    # Buscar comparables desde la base de datos
    comparables = await fetch_comparables(conn, subject, n=n)

    if len(comparables) < 2:
        raise ValueError(
            f"Solo se encontraron {len(comparables)} comparables para "
            f"{subject['tipo_inmueble']} en {ciudad}. "
            f"Se necesitan al menos 2. Intenta ampliar el rango de área o precio."
        )

    rows = []
    prices_hom = []
    for i, comp in enumerate(comparables, 1):
        hom = compute_homologation(comp, subject)
        rows.append({"numero": i, "comparable": comp, "homologation": hom})
        prices_hom.append(hom["precio_m2_hom"])

    stats = compute_statistics(prices_hom)
    objectives = compute_price_objectives(stats, area)

    # Obtener indicadores de zona (localidad/barrio más cercano)
    zone_indicators = None
    if lat and lon:
        try:
            zone_row = await conn.fetchrow("""
                SELECT i.iacc, i.iseg, i.ihed, i.idot, i.ipnu, i.iurb
                FROM iug.inmueble i
                WHERE i.geom IS NOT NULL
                  AND i.iurb IS NOT NULL
                ORDER BY i.geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
                LIMIT 1
            """, lon, lat)
            if zone_row:
                zone_indicators = {
                    'iacc': float(zone_row['iacc'] or 0),
                    'iseg': float(zone_row['iseg'] or 0),
                    'ihed': float(zone_row['ihed'] or 0),
                    'idot': float(zone_row['idot'] or 0),
                    'ipnu': float(zone_row['ipnu'] or 0),
                    'iurb': float(zone_row['iurb'] or 0),
                }
        except Exception as e:
            logger.warning(f"No se pudieron obtener indicadores de zona: {e}")

    return {
        "subject": subject,
        "comparables": rows,
        "statistics": stats,
        "objectives": objectives,
        "total_comparables": len(comparables),
        "metodo": "manual",
        "generated_at": datetime.date.today().isoformat(),
        "zone_indicators": zone_indicators,
    }
