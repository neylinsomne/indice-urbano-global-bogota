"""
Indicators Package

Scripts para cálculo de indicadores del IUG (Índice de Ubicación Global).

Indicadores:
- transport: Accesibilidad y conectividad (I_ACC - gravity model)
- security: Seguridad objetiva (I_SEG - AHP + proximidad)
- hedonic: Calidad estructural objetiva (I_HED = I_Dim + I_Dot)
- normative: Potencial normativo de uso del suelo (I_PNU - POT 555)
- global_urban: Indicador urbanístico global (I_URB - suma ponderada)
- market_study: Regresión hedónica de mercado (comparación)
"""

from .transport import calculate_transport_score
from .security import calculate_security_score
from .hedonic import calculate_hedonic_score
from .normative import get_normative_score
from .global_urban import calculate_iurb, get_iurb_for_inmueble

__all__ = [
    'calculate_transport_score',
    'calculate_security_score',
    'calculate_hedonic_score',
    'get_normative_score',
    'calculate_iurb',
    'get_iurb_for_inmueble',
]
