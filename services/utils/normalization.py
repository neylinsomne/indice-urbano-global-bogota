"""
Normalization Utilities

Funciones genéricas para normalizar scores a escala 0-5.

Métodos disponibles:
- Percentil ranking (robusto a outliers)
- Min-Max escalado
- Z-score con clipping
"""

import numpy as np
import pandas as pd
from typing import Union, List


def percentile_normalize(
    scores: Union[List[float], np.ndarray, pd.Series],
    target_min: float = 0,
    target_max: float = 5
) -> np.ndarray:
    """
    Normaliza scores usando percentil ranking (PERCENT_RANK en SQL)
    
    Ventajas:
    - Robusto a outliers
    - Distribución uniforme en el rango
    - Mismo método que SQL PERCENT_RANK()
    
    Args:
        scores: Scores a normalizar
        target_min: Valor mínimo del rango objetivo (default 0)
        target_max: Valor máximo del rango objetivo (default 5)
    
    Returns:
        np.ndarray: Scores normalizados en [target_min, target_max]
    
    Example:
        >>> scores = [10, 20, 30, 40, 50]
        >>> percentile_normalize(scores)
        array([0. , 1.25, 2.5 , 3.75, 5. ])
    """
    scores_array = np.array(scores, dtype=float)
    
    if len(scores_array) == 0:
        return scores_array
    
    # Ranking (argsort de argsort)
    ranks = scores_array.argsort().argsort()
    
    # Percentile (0 to 1)
    n = len(scores_array)
    if n == 1:
        percentiles = np.array([0.5])  # Single value at midpoint
    else:
        percentiles = ranks / (n - 1)
    
    # Scale to target range
    normalized = target_min + (target_max - target_min) * percentiles
    
    return normalized


def minmax_normalize(
    scores: Union[List[float], np.ndarray, pd.Series],
    target_min: float = 0,
    target_max: float = 5,
    score_min: float = None,
    score_max: float = None
) -> np.ndarray:
    """
    Normaliza scores usando Min-Max scaling
    
    Formula: (score - min) / (max - min) * (target_max - target_min) + target_min
    
    Args:
        scores: Scores a normalizar
        target_min: Valor mínimo del rango objetivo
        target_max: Valor máximo del rango objetivo
        score_min: Mínimo de scores (opcional, se calcula si no se provee)
        score_max: Máximo de scores (opcional, se calcula si no se provee)
    
    Returns:
        np.ndarray: Scores normalizados
    """
    scores_array = np.array(scores, dtype=float)
    
    if len(scores_array) == 0:
        return scores_array
    
    # Get or calculate min/max
    s_min = score_min if score_min is not None else scores_array.min()
    s_max = score_max if score_max is not None else scores_array.max()
    
    # Avoid division by zero
    if s_max == s_min:
        return np.full_like(scores_array, (target_min + target_max) / 2)
    
    # Normalize
    normalized = ((scores_array - s_min) / (s_max - s_min)) * (target_max - target_min) + target_min
    
    # Clip to ensure within bounds
    normalized = np.clip(normalized, target_min, target_max)
    
    return normalized


def zscore_normalize(
    scores: Union[List[float], np.ndarray, pd.Series],
    target_min: float = 0,
    target_max: float = 5,
    n_std: float = 3.0
) -> np.ndarray:
    """
    Normaliza usando Z-score con clipping a ±n desviaciones estándar
    
    Args:
        scores: Scores a normalizar
        target_min: Valor mínimo del rango objetivo
        target_max: Valor máximo del rango objetivo
        n_std: Número de desviaciones estándar para clipping
    
    Returns:
        np.ndarray: Scores normalizados
    """
    scores_array = np.array(scores, dtype=float)
    
    if len(scores_array) == 0:
        return scores_array
    
    # Calcular z-scores
    mean = scores_array.mean()
    std = scores_array.std()
    
    if std == 0:
        return np.full_like(scores_array, (target_min + target_max) / 2)
    
    z_scores = (scores_array - mean) / std
    
    # Clip a ±n_std
    z_clipped = np.clip(z_scores, -n_std, n_std)
    
    # Escalar a target range
    # z_clipped está en [-n_std, n_std]
    normalized = ((z_clipped + n_std) / (2 * n_std)) * (target_max - target_min) + target_min
    
    return normalized


def invert_score(
    score: float,
    max_value: float = 5
) -> float:
    """
    Invierte un score (útil cuando mayor score = peor)
    
    Example: crimen alto = score bajo de seguridad
    
    Args:
        score: Score a invertir
        max_value: Valor máximo de la escala
    
    Returns:
        float: Score invertido
    """
    return max_value - score
