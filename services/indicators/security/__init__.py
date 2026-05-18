"""
Security Indicator - Seguridad Objetiva

AHP + Proximidad CAI + Sectores policiales.
"""

from .calculator import (
    get_security_score,
    get_crime_stats_by_sector,
    analyze_security_distribution
)

__all__ = [
    'get_security_score',
    'get_crime_stats_by_sector',
    'analyze_security_distribution'
]

