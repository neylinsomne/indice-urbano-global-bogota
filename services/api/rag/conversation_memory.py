"""
Memoria conversacional del asistente INMU.

Cada sesión guarda en Redis los últimos N turnos (user + assistant) y el
último SearchIntent inferido. Esto permite que el asistente:

  1. Resuelva referencias anafóricas:
     "muéstrame en chapinero" → tras "apartamento cerca a parque" →
     resuelve a "apartamento cerca a parque en Chapinero".
  2. Mantenga filtros entre turnos sin que el usuario los repita.
  3. Sepa que el usuario ya vio cierto resultado (evita repetirlo).

API pública:
  - load_memory(session_id) → ConversationState
  - save_turn(session_id, role, content, intent_snapshot=None)
  - merge_context_into_query(query, prev_intent) → str
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from db.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

MAX_TURNS = 10                # mantenemos un trail corto para acotar tokens
SESSION_TTL = 60 * 60 * 24    # 24 h


@dataclass
class Turn:
    role: str          # 'user' | 'assistant'
    content: str       # texto del mensaje (resumido para el assistant)


@dataclass
class ConversationState:
    session_id: str
    turns: List[Turn] = field(default_factory=list)
    last_intent: Optional[Dict[str, Any]] = None
    last_results_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id":       self.session_id,
            "turns":            [asdict(t) for t in self.turns],
            "last_intent":      self.last_intent,
            "last_results_ids": self.last_results_ids,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversationState":
        return cls(
            session_id=d.get("session_id", ""),
            turns=[Turn(**t) for t in (d.get("turns") or [])],
            last_intent=d.get("last_intent"),
            last_results_ids=d.get("last_results_ids") or [],
        )


def _key(session_id: str) -> str:
    return f"chat:mem:{session_id}"


async def load_memory(session_id: str) -> ConversationState:
    """Carga el estado de la sesión desde Redis, vacío si no existe."""
    if not session_id:
        return ConversationState(session_id="")
    raw = await cache_get(_key(session_id))
    if not raw or not isinstance(raw, dict):
        return ConversationState(session_id=session_id)
    try:
        return ConversationState.from_dict(raw)
    except Exception as e:
        logger.warning("Memoria corrupta para session=%s: %s", session_id, e)
        return ConversationState(session_id=session_id)


async def save_state(state: ConversationState) -> None:
    """Persiste el estado completo (turns + intent + result ids)."""
    if not state.session_id:
        return
    # Mantenemos sólo los últimos MAX_TURNS
    state.turns = state.turns[-MAX_TURNS:]
    state.last_results_ids = state.last_results_ids[-30:]
    await cache_set(_key(state.session_id), state.to_dict(), ttl=SESSION_TTL)


async def append_turn(
    session_id: str,
    role: str,
    content: str,
    *,
    intent_snapshot: Optional[Dict[str, Any]] = None,
    result_ids: Optional[List[int]] = None,
) -> ConversationState:
    """Añade un turno y opcionalmente actualiza el snapshot de intent."""
    state = await load_memory(session_id)
    state.turns.append(Turn(role=role, content=content[:600]))
    if intent_snapshot is not None:
        state.last_intent = intent_snapshot
    if result_ids:
        # No repetimos ids; mantenemos el último set top
        state.last_results_ids = list(dict.fromkeys(state.last_results_ids + result_ids))[-30:]
    await save_state(state)
    return state


# ════════════════════════════════════════════════════════════════════
# Merge de contexto previo dentro de una query nueva
# ════════════════════════════════════════════════════════════════════

# Frases que SUGIEREN refinamiento sobre el contexto previo
# (el usuario asume que el chatbot recuerda los filtros anteriores).
_REFINEMENT_HINTS = [
    "muéstrame", "muestrame", "ahora", "también", "y en", "y con",
    "pero", "filtra", "filtrar", "solo", "sólo", "limitando",
    "ampliando", "agrega", "añade", "añadiendo",
]


def looks_like_refinement(query: str) -> bool:
    """Detecta si la query parece un refinamiento del turno previo."""
    q = query.lower().strip()
    if len(q) < 50:  # queries muy cortas casi siempre son refinamiento
        return True
    return any(h in q for h in _REFINEMENT_HINTS)


def merge_context_into_query(query: str, prev_intent: Optional[Dict[str, Any]]) -> str:
    """
    Si la query parece refinamiento Y hay intent previo, le anexa los
    filtros que faltan en formato natural. Sin perder los filtros NUEVOS
    que vengan en la query actual.

    Ej:
      prev_intent = "apartamento cerca a hospital, menos de 600M"
      query nueva = "ahora en chapinero"
      → "ahora en chapinero (filtros previos: apartamento, cerca a hospital, menos de 600M)"

    El intent parser de la query nueva siempre tendrá prioridad. Esto
    sólo aporta CONTEXTO para que extraiga más cosas.
    """
    if not prev_intent or not looks_like_refinement(query):
        return query

    bits: List[str] = []

    # Tipo de inmueble previo
    f = prev_intent.get("filters", {}) or {}
    if f.get("tipo_inmueble"):
        bits.append(", ".join(f["tipo_inmueble"]).lower())

    # Proximidades previas (categorías)
    proximities = prev_intent.get("proximity") or []
    for p in proximities[:3]:
        if p.get("label"):
            bits.append(f"cerca a {p['label']}")

    # Precio previo
    if f.get("precio_max"):
        bits.append(f"menos de {f['precio_max'] // 1_000_000}M")
    if f.get("precio_min"):
        bits.append(f"más de {f['precio_min'] // 1_000_000}M")

    # IUG previo
    iug = prev_intent.get("iug", {}) or {}
    if iug.get("iurb_min"):
        bits.append(f"IUG > {iug['iurb_min']}")

    if not bits:
        return query

    return f"{query} (filtros previos: {'; '.join(bits)})"
