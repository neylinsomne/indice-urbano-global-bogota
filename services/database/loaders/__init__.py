"""
Data Loaders Package

Módulos de carga de datos espaciales para el sistema de estudio inmobiliario.
Cada loader verifica si las tablas están vacías antes de ejecutar la carga.

Uso:
    from loaders import load_pot, load_dotaciones
    load_pot()
    load_dotaciones()
"""

from .load_pot555 import load_all_pot as load_pot
from .load_osm_roads import main as load_osm_roads
from .load_universidades import main as load_universidades
from .load_seguridad_completo import main as load_seguridad
from .load_dotaciones import load_all_dotaciones as load_dotaciones
from .load_espaciales_basicas import load_all_espaciales as load_espaciales

__all__ = [
    'load_pot',
    'load_osm_roads',
    'load_universidades',
    'load_seguridad',
    'load_dotaciones',
    'load_espaciales'
]
