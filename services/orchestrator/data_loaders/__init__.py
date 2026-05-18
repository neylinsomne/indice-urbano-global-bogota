"""Data Loaders Package

Cargadores automáticos de datos estáticos.
Se ejecutan en startup si las tablas están vacías.
"""

from .dotaciones_loader import load_dotaciones_if_empty
from .osm_loader import load_all_osm_data
from .security_loader import load_all_security_data

__all__ = [
    'load_dotaciones_if_empty',
    'load_all_osm_data',
    'load_all_security_data'
]

