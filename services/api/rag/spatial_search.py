"""
Constructor de queries espaciales a partir de un SearchIntent.

Toma el intent parseado y arma:
  1. SQL parametrizada con LEFT JOINs LATERAL sobre las tablas POI
     correspondientes (una por requisito de proximidad), midiendo la
     distancia geográfica mínima desde el inmueble al POI más cercano.
  2. Filtros aplicados como WHERE clauses indexadas.
  3. Scoring híbrido (IUG global + proximidad + similitud de filtros)
     con pesos configurables.
  4. Re-intento "relaxed" si el conjunto duro retorna 0 resultados.
  5. Explicaciones humanas por cada match.

Decisiones clave:
  - Uso geography (no projected geometry) para que ST_Distance retorne
    metros directos.
  - LATERAL en lugar de JOIN normal: queremos LA distancia mínima del
    POI más cercano, no un row por cada POI cercano.
  - El score se calcula en SQL para que el ORDER BY no necesite traer
    toda la tabla a Python.
  - LIMIT alto (200) sólo si el ranking final aplica en Python; aquí
    LIMITamos a 30 porque ya ordenamos en SQL.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import asyncpg

from rag.intent_parser import (
    CATEGORY_TO_DB,
    CATEGORY_HUMAN_LABEL,
    SearchIntent,
    ProximityRequirement,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constantes de scoring
# ════════════════════════════════════════════════════════════════════

DEFAULT_LIMIT = 20
HARD_LIMIT = 50
SCORE_WEIGHTS = {
    "iug":         0.45,   # peso del IUG global
    "proximity":   0.40,   # peso de la cercanía promedio a POIs pedidos
    "address":     0.15,   # peso de la cercanía a la dirección anchor
}


# ════════════════════════════════════════════════════════════════════
# Helpers de construcción de SQL
# ════════════════════════════════════════════════════════════════════

def _proximity_join_clauses(reqs: List[ProximityRequirement]) -> tuple[List[str], List[str], List[str]]:
    """
    Para cada requisito de proximidad arma un LEFT JOIN LATERAL que
    expone:
        d_<idx> : distancia en metros al POI más cercano
        n_<idx> : nombre del POI más cercano

    Y devuelve también las WHERE clauses para los hard requirements.

    Returns:
        joins, select_distances, where_hard
    """
    joins: List[str] = []
    selects: List[str] = []
    where_hard: List[str] = []

    for i, req in enumerate(reqs):
        cfg = CATEGORY_TO_DB.get(req.categoria)
        if not cfg:
            continue
        alias = f"p{i}"
        table = cfg["table"]
        where_inner = cfg["where"]

        joins.append(f"""
            LEFT JOIN LATERAL (
                SELECT nombre,
                       ST_Distance(i.geom::geography, {alias}_src.geom::geography)::int AS dist_m
                FROM {table} AS {alias}_src
                WHERE {where_inner}
                  AND ST_DWithin(i.geom::geography, {alias}_src.geom::geography, {req.max_m})
                ORDER BY i.geom <-> {alias}_src.geom
                LIMIT 1
            ) AS {alias} ON TRUE
        """)
        selects.append(f"{alias}.dist_m AS d_{i}")
        selects.append(f"{alias}.nombre AS n_{i}")

        if req.preferencia == "hard":
            where_hard.append(f"{alias}.dist_m IS NOT NULL")

    return joins, selects, where_hard


def _filter_where_clauses(intent: SearchIntent, params: List[Any]) -> List[str]:
    """Convierte FilterClause + IugConstraints en WHERE clauses parametrizadas."""
    f = intent.filters
    iug = intent.iug
    where: List[str] = ["i.geom IS NOT NULL", "i.iurb IS NOT NULL"]

    # Sanity floor: el scraper a veces mete arriendos en la columna precio
    # (canon mensual de 1-3M COP) y rows en Cartagena/Cali con valores
    # absurdos. Para tipos de vivienda asumimos venta y filtramos lo que
    # claramente no es un precio de venta bogotano.
    where.append(
        "NOT (i.tipo_inmueble IN ('Casa','Apartamento','Apartaestudio') "
        "AND i.precio IS NOT NULL AND i.precio < 30000000)"
    )

    if f.tipo_inmueble:
        params.append(f.tipo_inmueble)
        where.append(f"i.tipo_inmueble = ANY(${len(params)})")
    if f.precio_min is not None:
        params.append(f.precio_min)
        where.append(f"i.precio >= ${len(params)}")
    if f.precio_max is not None:
        params.append(f.precio_max)
        where.append(f"i.precio <= ${len(params)}")
    if f.area_min is not None:
        params.append(f.area_min)
        where.append(f"i.area_construida >= ${len(params)}")
    if f.area_max is not None:
        params.append(f.area_max)
        where.append(f"i.area_construida <= ${len(params)}")
    if f.habitaciones_min is not None:
        params.append(f.habitaciones_min)
        where.append(f"i.habitaciones >= ${len(params)}")
    if f.habitaciones_max is not None:
        params.append(f.habitaciones_max)
        where.append(f"i.habitaciones <= ${len(params)}")
    if f.banos_min is not None:
        params.append(f.banos_min)
        where.append(f"i.banos >= ${len(params)}")
    if f.localidad:
        params.append(f.localidad)
        where.append(f"UPPER(l.nombre) = UPPER(${len(params)})")
    if f.barrio:
        params.append(f.barrio)
        where.append(f"UPPER(b.nombre) = UPPER(${len(params)})")

    for dim in ("iurb", "iacc", "iseg", "ihed", "idot", "ipnu"):
        val = getattr(iug, f"{dim}_min", None)
        if val is not None:
            params.append(val)
            where.append(f"i.{dim} >= ${len(params)}")

    return where


def _amenity_joins(amenities: List[str]) -> tuple[List[str], List[str]]:
    """Si hay amenidades, se hace un JOIN con v_inmuebles_caracteristicas
    para filtrar booleanos. La vista ya tiene una fila por inmueble."""
    if not amenities:
        return [], []
    join = ["LEFT JOIN iug.v_inmuebles_caracteristicas vc ON vc.id_inmueble = i.id_inmueble"]
    where = [f"vc.{a} = TRUE" for a in amenities if a.startswith("tiene_")]
    return join, where


def _build_address_proximity(intent: SearchIntent, params: List[Any]) -> tuple[str, str, str, str]:
    """
    Si hay address_anchor con (lat,lon) resuelto, añade columna d_addr
    + condición. Devuelve (select_extra, join_extra, where_extra, label).
    """
    a = intent.address_anchor
    if not a or a.lat is None or a.lon is None:
        return "", "", "", ""

    params.append(a.lon)
    p_lon = f"${len(params)}"
    params.append(a.lat)
    p_lat = f"${len(params)}"
    params.append(a.max_m)
    p_max = f"${len(params)}"

    select_extra = (
        f", ST_Distance(i.geom::geography, "
        f"ST_SetSRID(ST_MakePoint({p_lon}, {p_lat}), 4326)::geography)::int AS d_addr"
    )
    where_extra = (
        f"ST_DWithin(i.geom::geography, "
        f"ST_SetSRID(ST_MakePoint({p_lon}, {p_lat}), 4326)::geography, {p_max})"
    )
    return select_extra, "", where_extra, a.raw


# ════════════════════════════════════════════════════════════════════
# Score builder
# ════════════════════════════════════════════════════════════════════

def _score_expression(intent: SearchIntent, scope: str = "outer") -> str:
    """
    Construye una expresión SQL que combina:
      - score_iug = iurb / 5
      - score_prox = promedio de (1 - d_i / max_i) cumplidos
      - score_addr = (1 - d_addr / max_addr) si hay anchor

    scope='outer'  → referencias a base.* (CTE)
    scope='inner'  → referencias a i.* / p<i>.* (inline, raramente útil)
    """
    parts: List[str] = []
    base = "base." if scope == "outer" else ""

    # IUG (en outer "base.iurb", en inner "i.iurb")
    iurb_col = f"{base}iurb" if scope == "outer" else "i.iurb"
    parts.append(f"(COALESCE({iurb_col}, 0) / 5.0) * {SCORE_WEIGHTS['iug']}")

    # Proximidad: en outer las distancias ya son base.d_<i>
    if intent.proximity:
        prox_terms: List[str] = []
        for i, req in enumerate(intent.proximity):
            col = f"{base}d_{i}" if scope == "outer" else f"p{i}.dist_m"
            t = (
                f"CASE WHEN {col} IS NULL THEN 0 "
                f"     ELSE GREATEST(0, 1 - {col}::float / {req.max_m}) END"
            )
            prox_terms.append(t)
        avg = "(" + " + ".join(prox_terms) + f") / {len(prox_terms)}.0"
        parts.append(f"({avg}) * {SCORE_WEIGHTS['proximity']}")

    # Dirección anchor
    if intent.address_anchor and intent.address_anchor.lat is not None:
        max_m = intent.address_anchor.max_m
        col = f"{base}d_addr" if scope == "outer" else "d_addr"
        parts.append(
            f"GREATEST(0, 1 - {col}::float / {max_m}) * {SCORE_WEIGHTS['address']}"
        )

    return " + ".join(parts) if parts else "0.0"


# ════════════════════════════════════════════════════════════════════
# Builder principal
# ════════════════════════════════════════════════════════════════════

def build_query(intent: SearchIntent, *, limit: int = DEFAULT_LIMIT,
                relax_proximity: bool = False) -> tuple[str, List[Any]]:
    """
    Construye la SQL parametrizada.

    Args:
        intent: SearchIntent parseado.
        limit: tope de resultados.
        relax_proximity: si True, todos los HARD se vuelven SOFT
            (no se exige que el POI esté dentro del radio para
            que el inmueble aparezca, sólo penaliza el score).
    """
    params: List[Any] = []

    # Si relax, marca todo soft sin mutar el intent original
    reqs = intent.proximity
    if relax_proximity:
        reqs = [ProximityRequirement(
            categoria=r.categoria, max_m=r.max_m,
            preferencia="soft", label=r.label,
        ) for r in reqs]

    joins, prox_selects, where_hard = _proximity_join_clauses(reqs)
    where_filters = _filter_where_clauses(intent, params)
    am_joins, am_where = _amenity_joins(intent.amenities)
    addr_sel, _, addr_where, addr_label = _build_address_proximity(intent, params)

    score_expr = _score_expression(intent, scope="outer")

    where_all = where_filters + where_hard + am_where
    if addr_where:
        where_all.append(addr_where)

    # Estructura: CTE 'base' calcula todas las columnas (incluidas las
    # distancias d_i, d_addr) y luego un SELECT externo agrega la
    # columna `score` y ordena. Necesario porque PostgreSQL no permite
    # usar un alias del mismo SELECT en otra expresión del mismo nivel.
    inner_prox_select = ", ".join(prox_selects) if prox_selects else "NULL AS _no_prox"
    sql = f"""
    WITH base AS (
        SELECT
            i.id_inmueble,
            i.tipo_inmueble,
            i.precio,
            i.area_construida AS area,
            i.habitaciones,
            i.banos,
            i.iurb,
            i.iacc, i.iseg, i.ihed, i.idot, i.ipnu,
            l.nombre AS localidad,
            b.nombre AS barrio,
            ST_X(i.geom)::float AS lon,
            ST_Y(i.geom)::float AS lat,
            {inner_prox_select}
            {addr_sel}
        FROM iug.inmueble i
        LEFT JOIN iug.localidad l ON i.id_localidad = l.id_localidad
        LEFT JOIN iug.barrio b   ON i.id_barrio    = b.id_barrio
        {" ".join(am_joins)}
        {" ".join(joins)}
        WHERE {" AND ".join(where_all)}
    )
    SELECT base.*, ({score_expr}) AS score
    FROM base
    ORDER BY score DESC NULLS LAST
    LIMIT {min(limit, HARD_LIMIT)}
    """
    return sql, params


# ════════════════════════════════════════════════════════════════════
# Explicaciones humanas (post-procesamiento)
# ════════════════════════════════════════════════════════════════════

def _walking_minutes(meters: int) -> int:
    """80 m/min — caminata urbana promedio."""
    return max(1, round(meters / 80))


def explain_row(row: Dict[str, Any], intent: SearchIntent) -> Dict[str, Any]:
    """
    Toma una fila del resultado y arma un dict con:
        - los datos básicos del inmueble
        - una lista de "explicaciones" humanas que componen su match
    """
    explicaciones: List[Dict[str, str]] = []

    # Filtros del inmueble
    if intent.filters.tipo_inmueble or intent.filters.area_min or intent.filters.habitaciones_min:
        bits: List[str] = []
        if row.get("tipo_inmueble"):
            bits.append(str(row["tipo_inmueble"]))
        if row.get("area") is not None:
            bits.append(f"{int(row['area'])} m²")
        if row.get("habitaciones") is not None:
            bits.append(f"{int(row['habitaciones'])} habs")
        if bits:
            explicaciones.append({"dim": "filtro", "txt": " · ".join(bits)})

    # Proximidad cumplida
    for i, req in enumerate(intent.proximity):
        d = row.get(f"d_{i}")
        n = row.get(f"n_{i}")
        if d is None:
            continue
        mins = _walking_minutes(d)
        label = CATEGORY_HUMAN_LABEL.get(req.categoria, req.categoria)
        if n:
            txt = f"a {d} m de {label} ({n}) · ~{mins} min a pie"
        else:
            txt = f"a {d} m del {label} más cercano · ~{mins} min a pie"
        explicaciones.append({"dim": "proximidad", "txt": txt})

    # Dirección
    if intent.address_anchor and row.get("d_addr") is not None:
        d = int(row["d_addr"])
        explicaciones.append({
            "dim": "direccion",
            "txt": f"a {d} m de {intent.address_anchor.raw}",
        })

    # Indicador
    iurb = row.get("iurb")
    iseg = row.get("iseg")
    if iurb is not None:
        parts = [f"IUG {float(iurb):.2f}/5"]
        if iseg is not None and intent.iug.iseg_min is not None:
            parts.append(f"Seguridad {float(iseg):.2f}")
        explicaciones.append({"dim": "indicador", "txt": " · ".join(parts)})

    # Localidad
    if row.get("localidad"):
        explicaciones.append({"dim": "ubicacion", "txt": f"{row['localidad']}"
                              + (f", {row['barrio']}" if row.get("barrio") else "")})

    return {
        "id_inmueble":   row["id_inmueble"],
        "tipo":          row.get("tipo_inmueble"),
        "precio":        int(row["precio"]) if row.get("precio") else None,
        "area":          float(row["area"]) if row.get("area") else None,
        "habitaciones":  int(row["habitaciones"]) if row.get("habitaciones") else None,
        "banos":         int(row["banos"]) if row.get("banos") else None,
        "iug":           float(row["iurb"]) if row.get("iurb") is not None else None,
        "localidad":     row.get("localidad"),
        "barrio":        row.get("barrio"),
        "lat":           row.get("lat"),
        "lon":           row.get("lon"),
        "score":         round(float(row["score"]), 4) if row.get("score") is not None else 0.0,
        "explicaciones": explicaciones,
    }


# ════════════════════════════════════════════════════════════════════
# Ejecutor con fallback de relaxation
# ════════════════════════════════════════════════════════════════════

def generate_suggestions(intent: SearchIntent, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Genera 3-4 opciones contextuales (estilo Claude A/B/C/D) que el
    usuario puede clickear para refinar la búsqueda.

    La lógica decide qué proponer según lo que YA tiene el intent:
      - Si hay pocos resultados → ofrecer relajar
      - Si hay muchos → ofrecer filtrar
      - Si falta IUG mínimo → ofrecer "solo buen IUG"
      - Si falta precio → ofrecer rango típico
      - Si la proximidad es ancha → ofrecer estrechar
      - Siempre: ofrecer cambiar tipo de inmueble o comparar localidad

    Cada sugerencia incluye:
      - letter:    A | B | C | D
      - label:     texto para el botón
      - prompt:    la query que se ejecutará si el usuario clickea
      - reason:    explicación corta (qué cambia)
    """
    out: List[Dict[str, Any]] = []
    n = len(results)
    iug = intent.iug
    f = intent.filters

    # 1. Si pocos resultados, sugerir relajar el primer requisito de proximidad
    if n < 3 and intent.proximity:
        first = intent.proximity[0]
        nuevo_radio = min(first.max_m + 500, 2500)
        out.append({
            "letter": "A",
            "label": f"Ampliar radio a {nuevo_radio} m del {first.label}",
            "prompt": _rewrite_with_proximity(intent.query_raw, first.label, nuevo_radio),
            "reason": "Tu búsqueda devolvió pocos resultados — probemos un radio mayor.",
        })

    # 2. Si tiene >5 resultados, sugerir afinar con IUG si no está
    if n >= 5 and iug.iurb_min is None:
        out.append({
            "letter": chr(ord("A") + len(out)),
            "label": "Solo zonas con buen IUG (≥ 3.5)",
            "prompt": f"{intent.query_raw}, con IUG mayor a 3.5",
            "reason": "Filtra a las zonas que pasan el umbral de calidad urbana.",
        })

    # 3. Si no hay precio, sugerir uno típico
    if f.precio_max is None and f.precio_min is None:
        out.append({
            "letter": chr(ord("A") + len(out)),
            "label": "Limitar presupuesto a 500M",
            "prompt": f"{intent.query_raw}, menos de 500 millones",
            "reason": "Acota el resultado al rango más típico del mercado bogotano.",
        })

    # 4. Si no hay localidad y hay resultados, sugerir focalizar en el top
    if f.localidad is None and n > 0:
        top_loc = results[0].get("localidad")
        if top_loc:
            out.append({
                "letter": chr(ord("A") + len(out)),
                "label": f"Sólo en {top_loc.title()}",
                "prompt": f"{intent.query_raw}, en {top_loc.title()}",
                "reason": f"La mejor coincidencia está en {top_loc.title()} — concentra la búsqueda allí.",
            })

    # 5. Comparativo de tipo de inmueble si está fijo
    if f.tipo_inmueble and len(f.tipo_inmueble) == 1:
        actual = f.tipo_inmueble[0]
        alt = "Casa" if actual == "Apartamento" else "Apartamento"
        out.append({
            "letter": chr(ord("A") + len(out)),
            "label": f"Comparar con {alt.lower()}s",
            "prompt": intent.query_raw.replace(actual.lower(), alt.lower())
                                       .replace(actual, alt),
            "reason": f"Mira la misma búsqueda pero con {alt.lower()}s.",
        })

    # 6. Si tiene seguridad pero no es alta, ofrecer subirla
    if iug.iseg_min is None and "seguridad" not in intent.query_raw.lower():
        out.append({
            "letter": chr(ord("A") + len(out)),
            "label": "Priorizar zonas muy seguras",
            "prompt": f"{intent.query_raw}, muy seguro",
            "reason": "Añade el filtro de seguridad alta (I_SEG ≥ 4).",
        })

    # Default si nada aplicó
    if not out:
        out.append({
            "letter": "A",
            "label": "Ver más resultados similares",
            "prompt": intent.query_raw,
            "reason": "Repite la búsqueda mostrando más matches.",
        })

    return out[:4]


def _rewrite_with_proximity(query: str, label: str, new_radius_m: int) -> str:
    """Reemplaza la distancia/radio mencionado en la query si la hay."""
    import re as _re
    # Si la query tiene "Xm" o "X metros", reemplazar
    new_pat = f"{new_radius_m} m"
    rewritten = _re.sub(r"\d+\s*m(etros?)?\b", new_pat, query, count=1, flags=_re.IGNORECASE)
    if rewritten == query:
        # No tenía distancia explícita — anexa
        rewritten = f"{query} (a {new_radius_m} m del {label})"
    return rewritten


async def search(
    pool: asyncpg.Pool,
    intent: SearchIntent,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    Ejecuta la búsqueda. Si los HARD requirements producen 0 resultados,
    re-intenta con todos en SOFT y devuelve indicación de "se relajó".
    """
    sql, params = build_query(intent, limit=limit, relax_proximity=False)

    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, *params)
        except Exception as e:
            logger.exception("Error ejecutando query natural: %s", e)
            return {
                "results": [],
                "count": 0,
                "relaxed": False,
                "error": "Error ejecutando la búsqueda",
                "sql": sql if logger.isEnabledFor(logging.DEBUG) else None,
            }

    relaxed = False
    if not rows and intent.proximity:
        sql2, params2 = build_query(intent, limit=limit, relax_proximity=True)
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(sql2, *params2)
                relaxed = True
            except Exception:
                rows = []

    results = [explain_row(dict(r), intent) for r in rows]
    suggestions = generate_suggestions(intent, results)

    return {
        "results": results,
        "count": len(results),
        "relaxed": relaxed,
        "intent": intent.to_dict(),
        "suggestions": suggestions,
    }
