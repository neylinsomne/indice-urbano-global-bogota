"""
Global Urban Indicator - I_URB

Indicador Urbanístico Global como suma ponderada de:
- I_ACC (Accesibilidad)
- I_SEG (Seguridad)
- I_HED (Calidad Hedónica)
- I_PNU (Potencial Normativo)
"""

from .calculator import (
    calculate_iurb,
    get_iurb_for_inmueble,
    interpret_iurb,
    check_alerts,
    calculate_iurb_bulk,
    analyze_iurb_distribution,
    get_top_inmuebles
)

from .config import (
    PESOS_INDICADORES,
    PESOS_IGUALES,
    PESOS_INVERSION,
    PESOS_RESIDENCIAL,
    PESOS_ACTIVOS,
    INTERPRETACION,
    ALERTAS
)

__all__ = [
    'calculate_iurb',
    'get_iurb_for_inmueble',
    'interpret_iurb',
    'check_alerts',
    'calculate_iurb_bulk',
    'analyze_iurb_distribution',
    'get_top_inmuebles',
    'PESOS_INDICADORES',
    'PESOS_IGUALES',
    'PESOS_INVERSION',
    'PESOS_RESIDENCIAL',
    'PESOS_ACTIVOS',
    'INTERPRETACION',
    'ALERTAS'
]
