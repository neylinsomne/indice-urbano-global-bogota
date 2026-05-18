"""
Intent parser estructurado para queries de búsqueda inmobiliaria en
lenguaje natural.

Toma una consulta libre como
    "Apto cerca a hospital y parque en Chapinero, menos de 500M, IUG > 3.5"
y devuelve un objeto SearchIntent con:
    - proximity[]            (categorías POI + radio + hard/soft)
    - filters                (tipo, precio, área, habitaciones, localidad, barrio)
    - iug                    (umbrales por dimensión)
    - address_anchor         (si hay dirección, se geocodifica)
    - amenities[]            (piscina, gimnasio, etc.)
    - intent                 (search | compare | explain | recommend)

Dos motores trabajan en cascada:
  1. Rule-based con regex + diccionario de sinónimos. SIEMPRE corre,
     es determinista, predecible y rápido.
  2. LLM (Gemini Flash). Solo se invoca como "complemento" si el
     rule-based detecta una query no trivial donde quedaron campos
     sin extraer. El LLM puede rellenar lo que faltó.

El parser nunca falla: en peor caso devuelve un SearchIntent con
proximity vacío y filters mínimos, y la capa downstream decide qué
hacer (responder "no entendí" o relajar).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Diccionarios y reglas
# ════════════════════════════════════════════════════════════════════

# Sinónimos → categorías reales en iug.dotaciones_poi y otras tablas
# Cada categoría incluye TODAS las variantes que existen en la BD.
# Esto permite que "hospital" matchee con ips/hospital/clinica si las
# tres existen como filas.
CATEGORY_SYNONYMS: Dict[str, List[str]] = {
    # Salud
    "ips":               ["ips", "hospital", "clinica", "centro_salud", "centro medico", "centro médico", "consultorio"],
    "farmacia":          ["farmacia", "drogueria", "droguería"],
    # Educación
    "colegio":           ["colegio", "escuela", "instituto", "primaria", "secundaria", "bachillerato"],
    "universidad":       ["universidad", "facultad", "campus", "educacion superior", "educación superior"],
    "jardin":            ["jardin", "jardín", "preescolar", "guarderia", "guardería"],
    # Comercio
    "centro_comercial":  ["centro_comercial", "centro comercial", "mall", "cc"],
    "supermercado":      ["supermercado", "supermarket", "hipermercado"],
    "plaza_mercado":     ["plaza_mercado", "plaza de mercado", "mercado"],
    # Cultura
    "biblioteca":        ["biblioteca", "biblored"],
    "teatro":            ["teatro", "auditorio"],
    "museo":             ["museo", "galeria", "galería"],
    # Recreación
    "parque":            ["parque", "zona verde", "zonas verdes", "verde"],
    "escenario_deportivo": ["escenario deportivo", "polideportivo", "coliseo", "estadio"],
    "cancha_futbol":     ["cancha", "canchas", "futbol", "fútbol"],
    # Transporte
    "transmilenio":      ["transmilenio", "tm", "estacion tm", "estación tm", "tronco"],
    "sitp":              ["sitp", "alimentador", "paradero", "bus"],
    # Seguridad
    "cai":               ["cai", "policia", "policía", "estacion de policia", "estación de policía"],
}

# Mapeo categoría → tabla y where adicional. Soporta "ips" → varias
# entradas reales en dotaciones_poi (ips, hospital, clinica).
CATEGORY_TO_DB: Dict[str, Dict[str, Any]] = {
    "ips":               {"table": "iug.dotaciones_poi", "where": "categoria IN ('ips','hospital','clinica')"},
    "farmacia":          {"table": "iug.dotaciones_poi", "where": "categoria = 'farmacia'"},
    "colegio":           {"table": "iug.dotaciones_poi", "where": "categoria = 'colegio'"},
    "universidad":       {"table": "iug.dotaciones_poi", "where": "categoria = 'universidad'"},
    "jardin":            {"table": "iug.dotaciones_poi", "where": "categoria = 'jardin'"},
    "centro_comercial":  {"table": "iug.dotaciones_poi", "where": "categoria = 'centro_comercial'"},
    "supermercado":      {"table": "iug.dotaciones_poi", "where": "categoria = 'supermercado'"},
    "plaza_mercado":     {"table": "iug.dotaciones_poi", "where": "categoria = 'plaza_mercado'"},
    "biblioteca":        {"table": "iug.dotaciones_poi", "where": "categoria = 'biblioteca'"},
    "teatro":            {"table": "iug.dotaciones_poi", "where": "categoria = 'teatro'"},
    "museo":             {"table": "iug.dotaciones_poi", "where": "categoria = 'museo'"},
    "parque":            {"table": "iug.dotaciones_poi", "where": "categoria IN ('parque','escenario_deportivo','cancha_futbol')"},
    "escenario_deportivo": {"table": "iug.dotaciones_poi", "where": "categoria = 'escenario_deportivo'"},
    "cancha_futbol":     {"table": "iug.dotaciones_poi", "where": "categoria = 'cancha_futbol'"},
    "transmilenio":      {"table": "iug.estacion_transmilenio", "where": "geom IS NOT NULL"},
    "sitp":              {"table": "iug.sitp_paradero",         "where": "geom IS NOT NULL"},
    "cai":               {"table": "iug.cai_policia",           "where": "geom IS NOT NULL"},
}

# Etiquetas humanas para los reportes finales ("a 320 m de un hospital")
CATEGORY_HUMAN_LABEL: Dict[str, str] = {
    "ips":               "centro médico",
    "farmacia":          "farmacia",
    "colegio":           "colegio",
    "universidad":       "universidad",
    "jardin":            "jardín infantil",
    "centro_comercial":  "centro comercial",
    "supermercado":      "supermercado",
    "plaza_mercado":     "plaza de mercado",
    "biblioteca":        "biblioteca",
    "teatro":            "teatro",
    "museo":             "museo",
    "parque":            "parque",
    "escenario_deportivo": "escenario deportivo",
    "cancha_futbol":     "cancha de fútbol",
    "transmilenio":      "estación de TransMilenio",
    "sitp":              "paradero SITP",
    "cai":               "CAI de Policía",
}

# Frases que indican distancia "soft" en metros, ordenadas por prioridad.
# El primer match gana. Las frases más específicas van primero.
DISTANCE_HINTS: List[tuple[str, int]] = [
    (r"\bpegad[oa]\s+a\b",                  150),
    (r"\ba\s+una\s+cuadra\b",               150),
    (r"\bmuy\s+cerca\b",                    300),
    (r"\bal\s+lado\b",                      300),
    (r"\ba\s+pocos\s+pasos\b",              300),
    (r"\bcaminando\b",                      600),
    (r"\ba\s+pie\b",                        600),
    (r"\bcerca(?:no|na)?\b",                600),
    (r"\bproxim(?:o|a|os|as|idad)\b",       800),
    (r"\bcerca\s+en\s+carro\b",            2000),
    (r"\ben\s+(?:la\s+)?zona\b",           1500),
    (r"\bal\s+rededor\b",                  1000),
    (r"\balrededor\b",                     1000),
]

# Localidades de Bogotá (UPPER-CASE como vienen en la BD)
LOCALIDADES_BOGOTA = [
    "USAQUEN", "CHAPINERO", "SANTA FE", "SAN CRISTOBAL", "USME",
    "TUNJUELITO", "BOSA", "KENNEDY", "FONTIBON", "ENGATIVA",
    "SUBA", "BARRIOS UNIDOS", "TEUSAQUILLO", "LOS MARTIRES",
    "ANTONIO NARIÑO", "PUENTE ARANDA", "LA CANDELARIA",
    "RAFAEL URIBE URIBE", "CIUDAD BOLIVAR", "SUMAPAZ",
]

# Tipos de inmueble válidos en la BD
TIPOS_INMUEBLE = ["Apartamento", "Casa", "Lote", "Oficina", "Local", "Bodega"]

# Amenidades indexadas como booleanas en v_inmuebles_caracteristicas
AMENITY_KEYWORDS: Dict[str, List[str]] = {
    "tiene_piscina":      ["piscina"],
    "tiene_gimnasio":     ["gimnasio", "gym"],
    "tiene_parqueadero":  ["parqueadero", "garaje", "garage", "estacionamiento"],
    "tiene_vigilancia":   ["vigilancia", "porteria", "portería", "seguridad 24"],
    "tiene_ascensor":     ["ascensor", "elevador"],
    "tiene_salon_comunal":["salon comunal", "salón comunal", "salon social"],
    "tiene_bbq":          ["bbq", "asadero", "zona bbq"],
    "tiene_cancha":       ["cancha privada", "cancha en conjunto"],
    "tiene_jacuzzi":      ["jacuzzi"],
    "tiene_deposito":     ["deposito", "depósito", "cuarto util", "cuarto útil"],
}

# Mapeo de palabras claves de "calidad urbana" a umbrales por dimensión.
# Coincide con la escala 0-5 normalizada de los subíndices del IUG.
IUG_QUALITY_HINTS: List[tuple[str, str, float]] = [
    # frase                          dimension     umbral_min
    (r"\bmuy\s+seguro\b",             "iseg",        4.0),
    (r"\bsegur[oa]\b",                "iseg",        3.5),
    (r"\bbien\s+conectado\b",         "iacc",        3.5),
    (r"\bcon\s+buena\s+accesibilidad\b","iacc",      3.5),
    (r"\bbuena\s+dotaci[oó]n\b",      "idot",        3.5),
    (r"\bmuchos\s+servicios\b",       "idot",        3.5),
    (r"\bbuen\s+iug\b",               "iurb",        3.5),
    (r"\biug\s+alto\b",               "iurb",        4.0),
    (r"\biug\s+muy\s+alto\b",         "iurb",        4.5),
    (r"\bzona\s+top\b",               "iurb",        4.0),
]

# Patrón Bogotá para direcciones tipo "Cra 7 #80-23" / "Calle 100 # 15-50"
ADDRESS_REGEX = re.compile(
    r"\b(?:cra|carrera|calle|cl|av|avenida|diag|diagonal|tv|transversal)\s*"
    r"\d+[a-z]?(?:\s*(?:bis|este|sur|norte))?\s*[#°nro\.]+\s*\d+[a-z]?\s*[-–]?\s*\d*",
    flags=re.IGNORECASE,
)


# ════════════════════════════════════════════════════════════════════
# Dataclasses del resultado
# ════════════════════════════════════════════════════════════════════

@dataclass
class ProximityRequirement:
    categoria: str             # clave de CATEGORY_TO_DB
    max_m: int                 # radio en metros
    preferencia: str = "hard"  # 'hard' | 'soft' | 'prefer'
    label: str = ""            # etiqueta humana para el reporte

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FilterClause:
    tipo_inmueble: Optional[List[str]] = None
    precio_min: Optional[int] = None
    precio_max: Optional[int] = None
    area_min: Optional[float] = None
    area_max: Optional[float] = None
    habitaciones_min: Optional[int] = None
    habitaciones_max: Optional[int] = None
    banos_min: Optional[int] = None
    localidad: Optional[str] = None      # UPPER-CASE
    barrio: Optional[str] = None         # nombre exacto

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class IugConstraints:
    iurb_min: Optional[float] = None
    iacc_min: Optional[float] = None
    iseg_min: Optional[float] = None
    ihed_min: Optional[float] = None
    idot_min: Optional[float] = None
    ipnu_min: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AddressAnchor:
    raw: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    max_m: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchIntent:
    query_raw: str
    intent: str = "search"
    proximity: List[ProximityRequirement] = field(default_factory=list)
    filters: FilterClause = field(default_factory=FilterClause)
    iug: IugConstraints = field(default_factory=IugConstraints)
    address_anchor: Optional[AddressAnchor] = None
    amenities: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)  # debugging / warnings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_raw":       self.query_raw,
            "intent":          self.intent,
            "proximity":       [p.to_dict() for p in self.proximity],
            "filters":         self.filters.to_dict(),
            "iug":             self.iug.to_dict(),
            "address_anchor":  self.address_anchor.to_dict() if self.address_anchor else None,
            "amenities":       self.amenities,
            "notes":           self.notes,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers de extracción
# ════════════════════════════════════════════════════════════════════

def _detect_distance(q: str) -> Optional[int]:
    """Busca expresiones explícitas (500 m, 1 km, 8 minutos) y heurísticas."""
    # Explícito: "500m", "500 metros"
    m = re.search(r"(\d{2,4})\s*m(?:\b|etro)", q, flags=re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 50 <= val <= 5000:
            return val

    # Explícito: "1.5 km", "2 km"
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*km\b", q, flags=re.IGNORECASE)
    if m:
        km = float(m.group(1).replace(",", "."))
        return int(km * 1000)

    # Tiempo a pie: "5 minutos a pie", "10 min caminando" → ~80 m/min
    m = re.search(r"(\d+)\s*min(?:utos?)?(?:\s+(?:a\s+pie|caminando))?", q, flags=re.IGNORECASE)
    if m:
        mins = int(m.group(1))
        if 1 <= mins <= 30:
            return mins * 80

    # Heurística por keyword (primer match)
    for pat, dist in DISTANCE_HINTS:
        if re.search(pat, q, flags=re.IGNORECASE):
            return dist

    return None


def _detect_categories(q: str) -> List[str]:
    """Detecta TODAS las categorías mencionadas (no solo la primera)."""
    out: List[str] = []
    q_low = q.lower()
    for canonical, variants in CATEGORY_SYNONYMS.items():
        for v in variants:
            # \b … \b para no matchear substrings (ej. "mercado" no debe
            # matchear "supermercado" cuando ya hay "supermercado" explícito).
            if re.search(rf"\b{re.escape(v)}\b", q_low):
                if canonical not in out:
                    out.append(canonical)
                break
    return out


def _detect_filters(q: str) -> FilterClause:
    f = FilterClause()

    # Tipo de inmueble
    tipos_detectados: List[str] = []
    if re.search(r"\b(apartamento|aptos?|apto)\b", q, flags=re.IGNORECASE):
        tipos_detectados.append("Apartamento")
    if re.search(r"\bcasas?\b", q, flags=re.IGNORECASE):
        tipos_detectados.append("Casa")
    if re.search(r"\blotes?\b", q, flags=re.IGNORECASE):
        tipos_detectados.append("Lote")
    if re.search(r"\boficinas?\b", q, flags=re.IGNORECASE):
        tipos_detectados.append("Oficina")
    if re.search(r"\b(local(?:es)?|comercial(?:es)?)\b", q, flags=re.IGNORECASE):
        tipos_detectados.append("Local")
    if tipos_detectados:
        f.tipo_inmueble = tipos_detectados

    # Precio — millones o "M"
    # "menos de 500M", "bajo 500 millones", "<500M"
    m = re.search(r"(?:menos\s+de|hasta|bajo|m[áa]ximo|<)\s*\$?\s*(\d{2,4})\s*m(?:illones)?", q, flags=re.IGNORECASE)
    if m:
        f.precio_max = int(m.group(1)) * 1_000_000

    m = re.search(r"(?:más\s+de|sobre|m[íi]nimo|>)\s*\$?\s*(\d{2,4})\s*m(?:illones)?", q, flags=re.IGNORECASE)
    if m:
        f.precio_min = int(m.group(1)) * 1_000_000

    # Rango "entre 300 y 500M"
    m = re.search(r"entre\s*\$?\s*(\d{2,4})\s*(?:y|\-)\s*\$?\s*(\d{2,4})\s*m", q, flags=re.IGNORECASE)
    if m:
        f.precio_min = int(m.group(1)) * 1_000_000
        f.precio_max = int(m.group(2)) * 1_000_000

    # Área "más de 80 m2", "80m2", ">80 metros"
    m = re.search(r"(?:m[áa]s\s+de|sobre|m[íi]nimo|>)\s*(\d{2,4})\s*(?:m2|metros?\s+cuadrados?)", q, flags=re.IGNORECASE)
    if m:
        f.area_min = float(m.group(1))

    m = re.search(r"(?:menos\s+de|hasta|m[áa]ximo|<)\s*(\d{2,4})\s*(?:m2|metros?\s+cuadrados?)", q, flags=re.IGNORECASE)
    if m:
        f.area_max = float(m.group(1))

    # Habitaciones — "3 habitaciones", "3 hab", "3 cuartos"
    m = re.search(r"(\d+)\s*(?:habitaciones?|cuartos?|alcobas?|hab\.?)", q, flags=re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 10:
            f.habitaciones_min = n

    # Baños
    m = re.search(r"(\d+)\s*ba[ñn]os?", q, flags=re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 10:
            f.banos_min = n

    # Localidad
    q_upper = q.upper()
    for loc in LOCALIDADES_BOGOTA:
        if loc in q_upper:
            f.localidad = loc
            break

    return f


def _detect_iug(q: str) -> IugConstraints:
    c = IugConstraints()

    # Heurísticas de "calidad"
    for pat, dim, val in IUG_QUALITY_HINTS:
        if re.search(pat, q, flags=re.IGNORECASE):
            setattr(c, f"{dim}_min", val)

    # Explícito: "IUG > 3.5", "iurb >= 4"
    m = re.search(r"\b(iurb|iug|iacc|iseg|ihed|idot|ipnu)\s*(?:>=?|mayor\s+a)?\s*(\d(?:[\.,]\d+)?)", q, flags=re.IGNORECASE)
    if m:
        dim = m.group(1).lower().replace("iug", "iurb")
        val = float(m.group(2).replace(",", "."))
        if 0 <= val <= 5:
            setattr(c, f"{dim}_min", val)

    return c


def _detect_amenities(q: str) -> List[str]:
    found: List[str] = []
    q_low = q.lower()
    for col, words in AMENITY_KEYWORDS.items():
        for w in words:
            if w in q_low:
                if col not in found:
                    found.append(col)
                break
    return found


def _detect_address(q: str) -> Optional[str]:
    """Sólo extracción del raw string; geocoding va aparte para no acoplar redis aquí."""
    m = ADDRESS_REGEX.search(q)
    return m.group(0).strip() if m else None


# ════════════════════════════════════════════════════════════════════
# Motor 1 — rule-based
# ════════════════════════════════════════════════════════════════════

def parse_rule_based(query: str) -> SearchIntent:
    """
    Parser rule-based. Determinista, sin red, sin LLM. Siempre devuelve
    un SearchIntent (posiblemente con campos vacíos).
    """
    q = query.strip()
    intent = SearchIntent(query_raw=q)

    # Proximity: categorías + distancia global (si no se especifica
    # distancia por categoría individual, se aplica la global o un default)
    cats = _detect_categories(q)
    global_dist = _detect_distance(q) or 600  # default 600m si no dice nada
    for cat in cats:
        intent.proximity.append(
            ProximityRequirement(
                categoria=cat,
                max_m=global_dist,
                preferencia="hard",
                label=CATEGORY_HUMAN_LABEL.get(cat, cat),
            )
        )

    # Filtros del inmueble
    intent.filters = _detect_filters(q)

    # IUG
    intent.iug = _detect_iug(q)

    # Amenidades
    intent.amenities = _detect_amenities(q)

    # Dirección — sólo extrae el raw; el geocoding lo hace la capa que
    # tiene acceso a Redis para cache.
    addr = _detect_address(q)
    if addr:
        intent.address_anchor = AddressAnchor(raw=addr, max_m=_detect_distance(q) or 500)

    # Notas
    if not cats and not intent.filters.to_dict() and not intent.iug.to_dict():
        intent.notes.append("query_no_extraccion_rule_based")

    return intent


# ════════════════════════════════════════════════════════════════════
# Motor 2 — LLM enrichment (opcional)
# ════════════════════════════════════════════════════════════════════

_LLM_PROMPT = """Eres un parser de búsquedas inmobiliarias en Bogotá. Recibes una consulta libre y devuelves SOLAMENTE un JSON con los campos extraídos. NO escribas explicación, sólo el JSON.

Categorías válidas (campo proximity[].categoria):
  ips, farmacia, colegio, universidad, jardin, centro_comercial, supermercado,
  plaza_mercado, biblioteca, teatro, museo, parque, escenario_deportivo,
  cancha_futbol, transmilenio, sitp, cai

Localidades válidas (UPPER-CASE):
  USAQUEN, CHAPINERO, SANTA FE, SAN CRISTOBAL, USME, TUNJUELITO, BOSA,
  KENNEDY, FONTIBON, ENGATIVA, SUBA, BARRIOS UNIDOS, TEUSAQUILLO,
  LOS MARTIRES, ANTONIO NARIÑO, PUENTE ARANDA, LA CANDELARIA,
  RAFAEL URIBE URIBE, CIUDAD BOLIVAR, SUMAPAZ

Tipos de inmueble (capitalizados):
  Apartamento, Casa, Lote, Oficina, Local, Bodega

Esquema esperado:
{{
  "intent": "search",
  "proximity": [{{"categoria":"...", "max_m": 500, "preferencia":"hard"}}],
  "filters": {{"tipo_inmueble":["Apartamento"], "precio_max":500000000,
              "area_min":70, "habitaciones_min":2, "localidad":"CHAPINERO"}},
  "iug": {{"iurb_min": 3.5, "iseg_min": 4.0}},
  "amenities": ["tiene_piscina"],
  "address_raw": null
}}

Reglas:
  - distancias en metros enteros (1km=1000)
  - precios en pesos colombianos enteros
  - habitaciones_min y banos_min son enteros
  - sólo incluye campos donde haya señal CLARA en la consulta; lo demás omite
  - si la consulta menciona "centro médico", "hospital", "clínica" → categoria=ips
  - si menciona "parque" → categoria=parque (NO escenario_deportivo a menos que diga "cancha"/"deportivo")
  - preferencia="hard" por defecto; "soft" si dice "preferible"/"de ser posible"

Consulta del usuario:
"{query}"

JSON:
"""


def _merge_llm_into_intent(base: SearchIntent, llm_dict: Dict[str, Any]) -> SearchIntent:
    """Mezcla campos del LLM en el SearchIntent sin pisar lo que el
    rule-based ya extrajo con confianza."""
    # Proximity: añadir las que el rule-based no tenía
    existing_cats = {p.categoria for p in base.proximity}
    for p in llm_dict.get("proximity") or []:
        cat = p.get("categoria")
        if not cat or cat in existing_cats or cat not in CATEGORY_TO_DB:
            continue
        max_m = int(p.get("max_m") or 600)
        if not (50 <= max_m <= 5000):
            max_m = 600
        base.proximity.append(
            ProximityRequirement(
                categoria=cat, max_m=max_m,
                preferencia=p.get("preferencia") or "hard",
                label=CATEGORY_HUMAN_LABEL.get(cat, cat),
            )
        )

    # Filters: rellenar SOLO campos que estaban en None
    llm_f = llm_dict.get("filters") or {}
    for k in ("tipo_inmueble", "precio_min", "precio_max", "area_min",
              "area_max", "habitaciones_min", "banos_min", "localidad"):
        if getattr(base.filters, k) is None and llm_f.get(k) is not None:
            setattr(base.filters, k, llm_f[k])

    # IUG: ídem
    llm_iug = llm_dict.get("iug") or {}
    for k in ("iurb_min", "iacc_min", "iseg_min", "ihed_min", "idot_min", "ipnu_min"):
        if getattr(base.iug, k) is None and llm_iug.get(k) is not None:
            try:
                val = float(llm_iug[k])
                if 0 <= val <= 5:
                    setattr(base.iug, k, val)
            except (ValueError, TypeError):
                continue

    # Amenities: añadir las que faltan
    for a in llm_dict.get("amenities") or []:
        if a in AMENITY_KEYWORDS and a not in base.amenities:
            base.amenities.append(a)

    # Dirección: si rule-based no detectó nada
    if base.address_anchor is None and llm_dict.get("address_raw"):
        base.address_anchor = AddressAnchor(raw=str(llm_dict["address_raw"]), max_m=500)

    base.notes.append("llm_merge_applied")
    return base


async def enrich_with_gemini(intent: SearchIntent) -> SearchIntent:
    """
    Llama a Gemini Flash para rellenar campos que el rule-based no extrajo.
    Es opcional: si no hay API key configurada, devuelve el intent intacto.
    Acepta tanto GOOGLE_API_KEY como GEMINI_API_KEY (alias soportado).
    """
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        intent.notes.append("llm_skipped_no_api_key")
        return intent

    try:
        import httpx
    except ImportError:
        intent.notes.append("llm_skipped_no_httpx")
        return intent

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash-exp:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": _LLM_PROMPT.format(query=intent.query_raw)}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 600},
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
    except Exception as e:
        logger.warning("Gemini enrichment falló: %s", e)
        intent.notes.append(f"llm_error_{type(e).__name__}")
        return intent

    # Extraer JSON de la respuesta (puede venir con ```json … ```)
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        intent.notes.append("llm_no_json_match")
        return intent

    try:
        llm_dict = json.loads(m.group(0))
    except json.JSONDecodeError:
        intent.notes.append("llm_json_invalid")
        return intent

    return _merge_llm_into_intent(intent, llm_dict)


# ════════════════════════════════════════════════════════════════════
# API pública
# ════════════════════════════════════════════════════════════════════

async def parse(query: str, *, use_llm: bool = True) -> SearchIntent:
    """
    Punto de entrada principal. Aplica rule-based y, si use_llm=True y
    hay GOOGLE_API_KEY configurada, enriquece con Gemini Flash.
    """
    intent = parse_rule_based(query)

    # Sólo invocamos al LLM si quedó algo importante sin detectar
    needs_llm = (
        use_llm
        and (
            not intent.proximity
            or not intent.filters.to_dict()
        )
    )
    if needs_llm:
        intent = await enrich_with_gemini(intent)

    return intent


def parse_sync(query: str) -> SearchIntent:
    """Variante 100% sync (sin LLM) para tests rápidos."""
    return parse_rule_based(query)
