"""
Configuracion del scraper Habi.
Define ciudades, tipos de propiedad y URLs a scrapear.

Habi maneja:
  - Tipos: apartamentos, casas
  - Transacciones: solo venta (Habi no tiene arriendo)
  - Ciudades: las principales de Colombia
"""
import os

# Ciudades a scrapear
HABI_CIUDADES = [
    "bogota", "medellin", "cali", "barranquilla",
    "cajica", "chia", "madrid",
]

# Tipos de propiedad disponibles en Habi
# Habi solo maneja apartamentos y casas
HABI_TIPOS = ["apartamentos", "casas"]

# URL base
HABI_BASE_URL = "https://habi.co/venta-{tipo}/{ciudad}"

# MongoDB
MONGO_DB = os.getenv("MONGO_DB_HABI", "Real_state_tesis")
MONGO_COLLECTION_HABI = os.getenv("MONGO_COLLECTION_HABI", "habi_newera")


def get_habi_urls():
    """Genera todas las combinaciones ciudad x tipo."""
    return [
        {'url': HABI_BASE_URL.format(tipo=t, ciudad=c), 'tipo': t, 'ciudad': c}
        for t in HABI_TIPOS
        for c in HABI_CIUDADES
    ]
