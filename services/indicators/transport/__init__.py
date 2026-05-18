"""
Transport Indicator - Accesibilidad

Gravity model para medir accesibilidad a transporte público.
"""

from .calculator import (
    get_transport_score,
    calculate_gravity_model,
    get_nearby_transport,
    analyze_accessibility_distribution
)

from .config import RADIOS, PESOS_TRANSPORTE, GRAVITY_PARAMS

__all__ = [
    'get_transport_score',
    'calculate_gravity_model',
    'get_nearby_transport',
    'analyze_accessibility_distribution',
    'RADIOS',
    'PESOS_TRANSPORTE',
    'GRAVITY_PARAMS'
]

