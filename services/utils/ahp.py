"""
AHP (Analytic Hierarchy Process) Utilities

Cálculo de pesos usando matriz de comparación par a par.
"""

import numpy as np
from typing import Dict, Tuple


# Índice de consistencia aleatorio (RI) por tamaño de matriz
RI_VALUES = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49
}


def calculate_ahp_weights(comparison_matrix: np.ndarray) -> Dict:
    """
    Calcula pesos AHP usando método de eigenvalues
    
    Args:
        comparison_matrix: Matriz cuadrada de comparaciones par a par
                          Escala 1-9 de Saaty
    
    Returns:
        dict con 'weights', 'lambda_max', 'CI', 'CR', 'is_consistent'
    
    Example:
        >>> # Homicidios vs Sexuales = 3 (Homicidios más importante)
        >>> matrix = np.array([
        ...     [1,   3,   5,   9],   # Homicidios
        ...     [1/3, 1,   3,   7],   # Sexuales
        ...     [1/5, 1/3, 1,   5],   # Hurtos
        ...     [1/9, 1/7, 1/5, 1]    # Otros
        ... ])
        >>> result = calculate_ahp_weights(matrix)
        >>> result['weights']  # [0.566, 0.267, 0.120, 0.047]
    """
    n = comparison_matrix.shape[0]
    
    # 1. Calcular eigenvalues y eigenvectors
    eigenvalues, eigenvectors = np.linalg.eig(comparison_matrix)
    
    # 2. Encontrar el mayor eigenvalue (λ_max)
    max_idx = eigenvalues.argmax()
    lambda_max = eigenvalues[max_idx].real
    
    # 3. Eigenvector correspondiente = pesos
    weights_raw = eigenvectors[:, max_idx].real
    
    # 4. Normalizar pesos (suma = 1)
    weights = weights_raw / weights_raw.sum()
    
    # 5. Calcular Consistency Index (CI)
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0
    
    # 6. Calcular Consistency Ratio (CR)
    RI = RI_VALUES.get(n, 1.49)
    CR = CI / RI if RI > 0 else 0
    
    # 7. Verificar consistencia (CR < 0.10 es aceptable)
    is_consistent = CR < 0.10
    
    return {
        'weights': weights,
        'lambda_max': lambda_max,
        'CI': CI,
        'CR': CR,
        'RI': RI,
        'is_consistent': is_consistent
    }


def create_comparison_matrix_from_ranks(ranks: Dict[str, int]) -> Tuple[np.ndarray, list]:
    """
    Crea matriz de comparación simple desde rankings
    
    Args:
        ranks: dict {item: rank} donde rank menor = más importante
    
    Returns:
        tuple (matrix, items_order)
    
    Example:
        >>> ranks = {'Homicidios': 1, 'Sexuales': 2, 'Hurtos': 3}
        >>> matrix, items = create_comparison_matrix_from_ranks(ranks)
    """
    items = sorted(ranks.keys(), key=lambda x: ranks[x])
    n = len(items)
    
    matrix = np.ones((n, n))
    
    for i in range(n):
        for j in range(n):
            if i < j:
                # Item i es más importante que j
                diff = ranks[items[j]] - ranks[items[i]]
                matrix[i, j] = min(9, 1 + 2 * diff)  # Escalado simple
                matrix[j, i] = 1 / matrix[i, j]
    
    return matrix, items


def validate_comparison_matrix(matrix: np.ndarray, tolerance: float = 1e-6) -> Dict:
    """
    Valida que la matriz de comparación sea correcta
    
    Verifica:
    - Diagonal = 1
    - Simetría recíproca: M[i,j] = 1/M[j,i]
    
    Returns:
        dict con 'is_valid', 'errors'
    """
    n = matrix.shape[0]
    errors = []
    
    # Check diagonal
    diagonal = np.diag(matrix)
    if not np.allclose(diagonal, 1.0, atol=tolerance):
        errors.append("Diagonal debe ser todo 1s")
    
    # Check reciprocal symmetry
    for i in range(n):
        for j in range(i + 1, n):
            expected = 1 / matrix[j, i]
            if not np.isclose(matrix[i, j], expected, atol=tolerance):
                errors.append(f"Violación de simetría en [{i},{j}]: {matrix[i,j]} ≠ 1/{matrix[j,i]}")
    
    return {
        'is_valid': len(errors) == 0,
        'errors': errors
    }
