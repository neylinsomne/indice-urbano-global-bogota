"""
Sistema AHP Personalizado

Permite a usuarios personalizar pesos de indicadores según sus preferencias mediante:
- Cuestionario de comparaciones pareadas
- Cálculo automático de pesos AHP
- Aplicación a IDOT y otros sub-indicadores
"""

from .ahp_calculator import calcular_pesos_ahp, validar_consistencia
from .questionnaire import generar_cuestionario, procesar_respuestas
from .dotaciones_ahp import calcular_pesos_dotaciones, aplicar_pesos_personalizados

__all__ = [
    'calcular_pesos_ahp',
    'validar_consistencia',
    'generar_cuestionario',
    'procesar_respuestas',
    'calcular_pesos_dotaciones',
    'aplicar_pesos_personalizados'
]
