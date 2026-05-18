"""
Servicio de detección de outliers post-scraping usando DBSCAN.

Agrupa inmuebles por (ciudad, tipo_inmueble) y ejecuta DBSCAN
sobre features normalizados para identificar propiedades anómalas.
Genera explicaciones legibles de por qué cada propiedad es outlier.
"""
import json
import logging
from datetime import datetime, timezone

import asyncpg
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ── Parámetros ──────────────────────────────────────────────────
EPS = 1.5
MIN_SAMPLES = 5
MIN_GROUP_SIZE = 10        # grupos con menos propiedades se ignoran
ANOMALY_RATIO_HIGH = 3.0   # valor / mediana > 3 → anomalía
ANOMALY_RATIO_LOW = 0.25   # valor / mediana < 0.25 → anomalía

FEATURE_NAMES = {
    'precio_m2': 'Precio/m\u00b2',
    'area':      '\u00c1rea construida',
    'estrato':   'Estrato',
}


def _extract_ciudad(ubicacion: str) -> str:
    if not ubicacion:
        return ''
    parts = [p.strip() for p in ubicacion.split(',')]
    return parts[1] if len(parts) >= 2 else parts[0]


def _build_explanation(features: dict, medians: dict) -> dict:
    """
    Genera etiquetas de outlier comparando cada feature con la mediana del grupo.
    Retorna dict con features que contribuyen a la anomalía.
    """
    labels = {}
    for key, value in features.items():
        median = medians.get(key, 0)
        if median == 0 or value is None:
            continue

        ratio = value / median
        if ratio > ANOMALY_RATIO_HIGH or ratio < ANOMALY_RATIO_LOW:
            if ratio > 1:
                desc = f"{FEATURE_NAMES.get(key, key)} {ratio:.1f}x por encima de la mediana"
            else:
                desc = f"{FEATURE_NAMES.get(key, key)} {ratio:.2f}x de la t\u00edpica"

            labels[key] = {
                'valor': round(float(value), 2),
                'mediana': round(float(median), 2),
                'ratio': round(float(ratio), 2),
                'desc': desc,
            }

    return labels


async def run_outlier_classification(conn: asyncpg.Connection, admin_id: int = None) -> dict:
    """
    Ejecuta clasificación batch de outliers sobre todos los inmuebles.
    Retorna resumen de la ejecución.
    """
    # 1. Crear run
    run_id = await conn.fetchval(
        "INSERT INTO iug.outlier_run (triggered_by, params) "
        "VALUES ($1, $2) RETURNING id",
        admin_id,
        json.dumps({
            'eps': EPS, 'min_samples': MIN_SAMPLES,
            'features': list(FEATURE_NAMES.keys()),
            'min_group_size': MIN_GROUP_SIZE,
            'anomaly_ratio_high': ANOMALY_RATIO_HIGH,
            'anomaly_ratio_low': ANOMALY_RATIO_LOW,
        }),
    )

    # 2. Limpiar clasificaciones pendientes anteriores (no las confirmadas)
    await conn.execute("""
        UPDATE iug.inmueble SET is_outlier = FALSE
        WHERE id_inmueble IN (
            SELECT id_inmueble FROM iug.inmueble_outlier
            WHERE review_status = 'pending'
        )
    """)
    await conn.execute(
        "DELETE FROM iug.inmueble_outlier WHERE review_status = 'pending'"
    )

    # 3. Obtener todos los inmuebles con datos suficientes
    rows = await conn.fetch("""
        SELECT id_inmueble, ubicacion, tipo_inmueble,
               precio, area_construida, estrato
        FROM iug.inmueble
        WHERE precio IS NOT NULL
          AND area_construida IS NOT NULL
          AND area_construida > 0
          AND is_outlier = FALSE
    """)

    if not rows:
        await conn.execute(
            "UPDATE iug.outlier_run SET finished_at = NOW(), "
            "total_analyzed = 0, total_outliers = 0 WHERE id = $1",
            run_id,
        )
        return {'run_id': run_id, 'total_analyzed': 0, 'total_outliers': 0}

    # 4. Agrupar por (ciudad, tipo_inmueble)
    groups: dict[tuple, list] = {}
    for r in rows:
        ciudad = _extract_ciudad(r['ubicacion'])
        tipo = r['tipo_inmueble'] or 'Desconocido'
        key = (ciudad.lower().strip(), tipo)
        groups.setdefault(key, []).append(dict(r))

    total_analyzed = 0
    total_outliers = 0
    outlier_inserts = []

    for (ciudad, tipo), items in groups.items():
        if len(items) < MIN_GROUP_SIZE:
            continue

        total_analyzed += len(items)

        # 5. Construir matrix de features
        feature_data = []
        valid_items = []
        for item in items:
            area = float(item['area_construida'])
            precio = float(item['precio'])
            precio_m2 = precio / area
            estrato = float(item['estrato']) if item['estrato'] else None

            feats = [precio_m2, area]
            if estrato is not None:
                feats.append(estrato)

            feature_data.append(feats)
            valid_items.append({**item, '_precio_m2': precio_m2, '_estrato': estrato})

        # Rellenar estrato faltante con mediana del grupo
        has_estrato = any(len(f) == 3 for f in feature_data)
        if has_estrato:
            estratos = [f[2] for f in feature_data if len(f) == 3]
            med_estrato = float(np.median(estratos)) if estratos else 3.0
            for f in feature_data:
                if len(f) == 2:
                    f.append(med_estrato)

        X = np.array(feature_data)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # 6. DBSCAN
        db = DBSCAN(eps=EPS, min_samples=MIN_SAMPLES)
        labels = db.fit_predict(X_scaled)

        # 7. Calcular medianas del grupo
        precios_m2 = [v['_precio_m2'] for v in valid_items]
        areas = [float(v['area_construida']) for v in valid_items]
        medians = {
            'precio_m2': float(np.median(precios_m2)),
            'area': float(np.median(areas)),
        }
        if has_estrato:
            estratos_all = [v['_estrato'] for v in valid_items if v['_estrato'] is not None]
            if estratos_all:
                medians['estrato'] = float(np.median(estratos_all))

        # 8. Procesar outliers (cluster -1)
        for i, label in enumerate(labels):
            if label != -1:
                continue

            item = valid_items[i]
            features = {
                'precio_m2': item['_precio_m2'],
                'area': float(item['area_construida']),
            }
            if item['_estrato'] is not None:
                features['estrato'] = item['_estrato']

            explanation = _build_explanation(features, medians)

            # Solo marcar si hay al menos una razón extrema
            if not explanation:
                continue

            total_outliers += 1
            outlier_inserts.append((
                item['id_inmueble'],
                run_id,
                json.dumps(explanation),
            ))

    # 9. Insertar resultados
    if outlier_inserts:
        await conn.executemany(
            "INSERT INTO iug.inmueble_outlier (id_inmueble, run_id, outlier_labels) "
            "VALUES ($1, $2, $3::jsonb) "
            "ON CONFLICT (id_inmueble) DO UPDATE SET "
            "  run_id = EXCLUDED.run_id, "
            "  outlier_labels = EXCLUDED.outlier_labels, "
            "  review_status = 'pending', "
            "  reviewed_by = NULL, "
            "  reviewed_at = NULL, "
            "  classified_at = NOW()",
            outlier_inserts,
        )

        ids = [row[0] for row in outlier_inserts]
        # Batch update is_outlier
        await conn.execute(
            "UPDATE iug.inmueble SET is_outlier = TRUE "
            "WHERE id_inmueble = ANY($1::bigint[])",
            ids,
        )

    # 10. Finalizar run
    await conn.execute(
        "UPDATE iug.outlier_run SET finished_at = NOW(), "
        "total_analyzed = $1, total_outliers = $2 WHERE id = $3",
        total_analyzed, total_outliers, run_id,
    )

    logger.info(
        "Outlier classification run #%d: %d analyzed, %d outliers detected",
        run_id, total_analyzed, total_outliers,
    )

    return {
        'run_id': run_id,
        'total_analyzed': total_analyzed,
        'total_outliers': total_outliers,
    }


# ─── Trigger logic ──────────────────────────────────────────
MIN_NEW_FOR_DBSCAN = 30      # nuevas propiedades para disparar DBSCAN
MAX_DAYS_WITHOUT_RUN = 7     # dias maximos sin DBSCAN si hay datos nuevos


async def should_reclassify(conn) -> dict:
    """
    Evalua si se debe ejecutar DBSCAN post-scraping.
    Framework de 2 capas:
      - Capa 1: N propiedades nuevas (scraped_at > ultimo run) >= MIN_NEW_FOR_DBSCAN
      - Capa 2: Mas de MAX_DAYS_WITHOUT_RUN dias desde el ultimo run Y hay nuevas
    Devuelve {'trigger': bool, 'reasons': list, 'n_new': int}
    """
    reasons = []

    last_run = await conn.fetchrow(
        "SELECT started_at FROM iug.outlier_run ORDER BY started_at DESC LIMIT 1"
    )

    if last_run is None:
        # Nunca se ha corrido: trigger si hay suficientes datos
        n_total = await conn.fetchval(
            "SELECT COUNT(*) FROM iug.inmueble WHERE precio > 0 AND area_construida > 0"
        ) or 0
        if n_total >= MIN_NEW_FOR_DBSCAN:
            reasons.append(f'primer_run ({n_total} propiedades disponibles)')
        return {'trigger': bool(reasons), 'reasons': reasons, 'n_new': int(n_total)}

    last_started_at = last_run['started_at']
    # Quitar timezone para comparar con ultima_vista (timestamp without tz)
    if hasattr(last_started_at, 'replace'):
        last_started_at = last_started_at.replace(tzinfo=None)

    n_new = await conn.fetchval("""
        SELECT COUNT(*) FROM iug.inmueble
        WHERE ultima_vista > $1 AND precio > 0 AND area_construida > 0
    """, last_started_at) or 0

    if n_new <= 0:
        return {
            'trigger': False, 'reasons': [], 'n_new': 0,
            'message': 'Sin propiedades nuevas desde el ultimo run',
        }

    # Capa 1: volumen suficiente
    if n_new >= MIN_NEW_FOR_DBSCAN:
        reasons.append(f'nuevas_propiedades={n_new} (>={MIN_NEW_FOR_DBSCAN})')

    # Capa 2: tiempo sin correr
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    ts = last_started_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days_since = (now - ts).days
    if days_since >= MAX_DAYS_WITHOUT_RUN:
        reasons.append(f'tiempo_sin_run={days_since}d (>={MAX_DAYS_WITHOUT_RUN}d)')

    return {'trigger': bool(reasons), 'reasons': reasons, 'n_new': int(n_new)}
