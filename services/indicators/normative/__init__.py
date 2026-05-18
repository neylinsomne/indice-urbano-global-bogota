"""
Normative Indicator - I_PNU

Indicador de Potencial Normativo de Uso del Suelo (POT 555).
Califica el potencial de desarrollo inmobiliario según normativa de Bogotá.
"""

from .calculator import (
    get_normative_score,
    interpret_ipnu,
    analyze_ipnu_distribution,
    get_pot_zones_for_inmueble
)

from .config import (
    PESOS_COMPONENTES,
    SCORE_TRATAMIENTO,
    SCORE_EDIFICABILIDAD,
    SCORE_AREA_ACTIVIDAD,
    INTERPRETACION
)

__all__ = [
    'get_normative_score',
    'interpret_ipnu',
    'analyze_ipnu_distribution',
    'get_pot_zones_for_inmueble',
    'PESOS_COMPONENTES',
    'SCORE_TRATAMIENTO',
    'SCORE_EDIFICABILIDAD',
    'SCORE_AREA_ACTIVIDAD',
    'INTERPRETACION'
]
