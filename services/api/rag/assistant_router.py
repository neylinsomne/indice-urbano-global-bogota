"""
Router del asistente INMU. Decide cuál de los "ayudantes" especializados
atiende cada consulta:

  - search    → spatial_search.search() (búsqueda multi-dimensional)
  - compare   → comparativa entre 2+ localidades
  - explain   → preguntas metodológicas (qué es IUG, cómo se calcula…)
  - stats     → estadísticas globales o por zona
  - acm       → resumen rápido de un inmueble por id
  - smalltalk → cortesías ("hola", "gracias")

Cada ayudante tiene un mismo contrato:
    async def handle(query, user, pool, redis, memory) -> dict
        return {
            "kind":        str,             # search | compare | explain | ...
            "content":     str,             # texto principal de la respuesta
            "results":     list,            # tarjetas (opcional)
            "suggestions": list,            # chips A/B/C/D (opcional)
            "intent":      dict,            # debug
        }

El router NO ejecuta los ayudantes — sólo detecta cuál corresponde
y devuelve un descriptor `{handler, intent}`. Quien llama al router se
encarga de awaitear el handler.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from rag.intent_parser import SearchIntent, parse as parse_intent

logger = logging.getLogger(__name__)


# Patrones que detectan cada ayudante. Se evalúan en orden — el primer
# match gana. Por eso van los más específicos arriba.
_HANDLER_PATTERNS = [
    # ── smalltalk (cortísimo)
    ("smalltalk", [
        r"^(hola|buenas|buenos d[ií]as|hey|hi|saludos)[\s!.?]*$",
        r"^(gracias|listo|ok|perfecto|genial)[\s!.?]*$",
        r"^(ad[ií]os|chao|hasta luego|nos vemos)[\s!.?]*$",
    ]),
    # ── explain (metodología)
    ("explain", [
        r"\b(qu[eé] es|c[oó]mo se calcula|c[oó]mo funciona|qu[eé] significa)\b",
        r"\b(metodolog[ií]a|definici[oó]n|f[oó]rmula|teor[ií]a)\b",
        r"\b(por qu[eé]|explica|exp[lí]?came)\b",
        r"\biug\s*\?",
        r"\b(diferencia|diferencias) entre\b",
    ]),
    # ── stats (números globales)
    ("stats", [
        r"\b(cu[aá]nt[oa]s?|total de)\b",
        r"\b(promedio|media|estad[ií]sticas?)\b",
        r"\b(ranking|top)\s+\d*\s*(localidad|barrio|zona)",
        r"\b(distribuci[oó]n|histograma)\b",
    ]),
    # ── compare (dos o más zonas)
    ("compare", [
        r"\bcompara?(?:r|me|me lo)?\b",
        r"\b(versus|vs\.?)\b",
        r"\b\w+\s+(?:o|vs)\s+\w+\b.{0,20}\b(localidad|barrio|zona)",
    ]),
    # ── acm (resumen de inmueble específico)
    ("acm", [
        r"\b(inmueble|propiedad)\s+#?\s*\d+",
        r"\bid\s+\d{3,}",
        r"\b(cot[ií]za|cotizaci[oó]n|acm)\b",
    ]),
]

# Heurísticas para "search" (cualquier consulta con keywords de búsqueda)
_SEARCH_HINTS = [
    r"\b(apartament[oa]s?|aptos?|cas[ao]s?|lotes?|oficinas?|locales?)\b",
    r"\bcerca\s+(de|al?)\b",
    r"\ba\s+\d+\s*m(?:etros?)?\b",
    r"\b\d+\s*minutos?\b",
    r"\bbusc(?:o|a|ame|ar)\b",
    r"\b(hospital|cl[íi]nica|colegio|universidad|parque|farmacia|biblioteca|transmilenio|tm|cai|centro\s+comercial)\b",
    r"\b(?:menos|m[áa]s)\s+de\s+\$?\s*\d+",
]


def detect_handler(query: str) -> str:
    """
    Detecta a qué ayudante corresponde la query. Si nada matchea con
    seguridad, asume 'search' (es el caso más común en INMU).
    """
    q = query.lower().strip()
    for name, patterns in _HANDLER_PATTERNS:
        for pat in patterns:
            if re.search(pat, q, flags=re.IGNORECASE):
                return name
    for pat in _SEARCH_HINTS:
        if re.search(pat, q, flags=re.IGNORECASE):
            return "search"
    # Fallback: si la query es muy corta, probablemente smalltalk;
    # si es larga, probablemente explain.
    return "smalltalk" if len(q) < 25 else "explain"


@dataclass
class RoutedQuery:
    handler: str         # 'search' | 'compare' | 'explain' | 'stats' | 'acm' | 'smalltalk'
    query: str           # query original (posiblemente enriquecida con memoria)
    intent: Optional[SearchIntent] = None  # sólo si handler=='search' o 'compare'


async def route(query: str, *, use_llm: bool = True) -> RoutedQuery:
    """
    Punto de entrada: clasifica la query y, si aplica, parsea el intent
    para que el ayudante de search lo use directamente.
    """
    handler = detect_handler(query)
    intent: Optional[SearchIntent] = None
    if handler in ("search", "compare"):
        intent = await parse_intent(query, use_llm=use_llm)
    return RoutedQuery(handler=handler, query=query, intent=intent)


# ════════════════════════════════════════════════════════════════════
# Respuestas para handlers ligeros (smalltalk, explain básico)
# ════════════════════════════════════════════════════════════════════

SMALLTALK_REPLIES = {
    "hola":      "¡Hola! Cuéntame qué inmueble buscas o qué dimensión del IUG quieres explorar.",
    "buenas":    "¡Buenas! ¿Te ayudo a buscar un inmueble por proximidad o calidad urbana?",
    "gracias":   "Cuando quieras. Si necesitas otro filtro o comparar zonas, dímelo.",
    "listo":     "Perfecto. ¿Refinamos la búsqueda o paso a otra dimensión?",
    "adios":     "¡Hasta pronto! Si vuelves, recuerdo los filtros que usaste.",
    "chao":      "¡Hasta luego! La sesión queda guardada por 24 horas.",
}


def smalltalk_reply(query: str) -> str:
    q = query.lower().strip()
    for key, reply in SMALLTALK_REPLIES.items():
        if q.startswith(key):
            return reply
    return "¡Aquí estoy! ¿Te ayudo a buscar un inmueble?"


# Respuestas pre-canónicas para preguntas metodológicas frecuentes.
# Evitan llamar al LLM en preguntas que ya respondemos siempre igual.
QUICK_EXPLAIN = {
    r"\b(qu[eé] es|definici[oó]n).*\biug\b": (
        "El **Índice Urbano Global (IUG)** es una métrica [0, 5] que sintetiza "
        "5 dimensiones del entorno urbano de Bogotá calculadas con datos abiertos "
        "oficiales (DANE, IDECA, SDP, POT 555, EPV 2024). Es ortogonal al precio: "
        "no usa precio como insumo, así que detecta zonas donde la calidad urbana "
        "objetiva supera o queda por debajo del valor de mercado."
    ),
    r"\bc[oó]mo se calcula.*\biug\b": (
        "IUG = 0.20·I_ACC + 0.20·I_SEG + 0.20·I_HED + 0.20·I_DOT + 0.20·I_PNU.\n"
        "Cada subíndice se normaliza a [0, 5] por rank min-max. "
        "Los pesos son equiponderados por defecto (recomendación OECD/Nardo 2008)."
    ),
    r"\bi_acc|accesibilidad": (
        "**I_ACC (Accesibilidad)**: modelo gravitacional sobre TransMilenio + SITP.\n"
        "I_ACC,i = Σⱼ Oⱼ / dᵢⱼ^β (β ≈ 1.5). Cuanto más cerca a estaciones y mayor "
        "la jerarquía, mayor el score. Fuentes: TMSA (149 estaciones) y SITP-OSM (7.693 paraderos)."
    ),
    r"\bi_seg|seguridad": (
        "**I_SEG (Seguridad)** combina 3 capas: proximidad a CAI (40%), criminalidad "
        "objetiva ICSU (30%) y percepción ciudadana EPV 2024 (30%). Dentro de criminalidad, "
        "los delitos se ponderan por severidad vía AHP (homicidio 56.6%, delitos sexuales "
        "26.7%, hurto 12%)."
    ),
    r"\bi_hed|hed[oó]nico": (
        "**I_HED (Hedónico)**: score derivado de PCA sobre área, baños, garajes, ascensor, "
        "antigüedad. Validado con KMO ≥ 0.50, esfericidad de Bartlett (p < 0.05) y "
        "bootstrap de 200 réplicas. Captura el confort privado del inmueble."
    ),
    r"\bi_dot|dotaci[oó]n": (
        "**I_DOT (Dotación)**: proximidad acumulada a equipamientos en radios de "
        "caminabilidad de 400 y 800 m. Incluye salud (8.369 POIs), educación (2.820), "
        "cultura (157), comercio (70), recreación (194)."
    ),
    r"\bi_pnu|normativo|pot": (
        "**I_PNU (Normativo POT 555)**: scoring sobre 3 capas del Plan de Ordenamiento: "
        "tratamiento urbanístico (5.703 polígonos), edificabilidad (2.748) y áreas "
        "de actividad (1.135). Conecta con el método residual dinámico catastral."
    ),
    r"\bortogonal|c[oó]mo.*valida|validaci[oó]n": (
        "El IUG se valida con 11 pruebas estadísticas: ΔR² in-sample = +0.052, "
        "ΔAIC = -1586, ρ Spearman ranking = 0.998, AUC vs estrato = 0.48 (azar, "
        "confirma ortogonalidad). Mann-Whitney Q4 vs Q1 residual con p < 10⁻⁴ "
        "(discrimina mispricing)."
    ),
}


def quick_explain(query: str) -> Optional[str]:
    q = query.lower()
    for pat, reply in QUICK_EXPLAIN.items():
        if re.search(pat, q, flags=re.IGNORECASE):
            return reply
    return None
