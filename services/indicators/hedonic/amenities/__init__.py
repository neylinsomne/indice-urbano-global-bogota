"""
I_Dot - Amenities/Dotación Component

Conteo ponderado de características del inmueble.
"""

from .calculator import (
    calculate_amenities_score,
    calculate_batch_amenities,
    save_amenities_scores
)

__all__ = [
    'calculate_amenities_score',
    'calculate_batch_amenities',
    'save_amenities_scores',
]

