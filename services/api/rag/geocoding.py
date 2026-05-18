"""
Geocoding de direcciones de Bogotá vía Nominatim (OpenStreetMap).
Resultados cacheados en Redis 7 días — Nominatim tiene rate limit
estricto (1 req/s) y muchas queries repiten direcciones.

Para que el geocoder responda con buena precisión sobre Bogotá,
usamos el bounding box de la ciudad + countrycodes=co + viewbox.

Si Nominatim no responde o devuelve resultado fuera del bbox, la
función retorna None y la capa caller decide cómo seguir (típicamente
descartar el address_anchor del intent).
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import httpx

from db.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)


# Bbox de Bogotá D.C. — usado tanto para acotar la búsqueda como para
# validar que el resultado caiga DENTRO de la ciudad. Si está fuera,
# probablemente Nominatim devolvió un homónimo de otra parte del mundo.
BOGOTA_BBOX = {
    "min_lon": -74.30,
    "max_lon": -73.95,
    "min_lat":   4.45,
    "max_lat":   4.85,
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "INMU-IUG-Bogota/1.0 (research project; contact: palomavigias@gmail.com)"
GEOCODE_TTL = 7 * 24 * 3600  # 7 días


def _in_bogota(lat: float, lon: float) -> bool:
    return (
        BOGOTA_BBOX["min_lat"] <= lat <= BOGOTA_BBOX["max_lat"]
        and BOGOTA_BBOX["min_lon"] <= lon <= BOGOTA_BBOX["max_lon"]
    )


async def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Resuelve una dirección bogotana a (lat, lon).

    Args:
        address: Texto libre, p.ej. "Cra 7 #80-23" o "Calle 100 #15-50".

    Returns:
        (lat, lon) si la dirección cae dentro de Bogotá, None en otro caso.
    """
    if not address or len(address) < 3:
        return None

    # Limpieza: Nominatim no entiende "#" como nomenclatura de calle.
    # Convertimos "Cra 7 # 80-23" → "Cra 7 80 23 Bogotá".
    cleaned = (
        address.replace("#", " ")
               .replace("°", " ")
               .replace("Nro.", " ")
               .replace("Nro", " ")
               .replace(".", " ")
    )
    cleaned = " ".join(cleaned.split())  # collapse whitespace

    key = f"geocode:{cleaned.lower().strip()}"
    cached = await cache_get(key)
    if cached:
        # cache_get devuelve dict ya parseado
        if isinstance(cached, dict) and "lat" in cached and "lon" in cached:
            return (float(cached["lat"]), float(cached["lon"]))
        if isinstance(cached, str) and cached == "NULL":
            return None  # negative cache

    params = {
        "q": f"{cleaned}, Bogotá, Colombia",
        "format": "json",
        "limit": 3,
        "countrycodes": "co",
        "viewbox": f"{BOGOTA_BBOX['min_lon']},{BOGOTA_BBOX['max_lat']},"
                   f"{BOGOTA_BBOX['max_lon']},{BOGOTA_BBOX['min_lat']}",
        "bounded": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(NOMINATIM_URL, params=params,
                                 headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            results = r.json()
    except Exception as e:
        logger.warning("Nominatim falló para '%s': %s", address, e)
        # cache negativo corto (1h) para no martillarlos
        await cache_set(key, "NULL", ttl=3600)
        return None

    for item in results:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if _in_bogota(lat, lon):
            await cache_set(key, {"lat": lat, "lon": lon}, ttl=GEOCODE_TTL)
            logger.info("Geocoded '%s' → (%.5f, %.5f)", address, lat, lon)
            return (lat, lon)

    await cache_set(key, "NULL", ttl=GEOCODE_TTL)
    return None
