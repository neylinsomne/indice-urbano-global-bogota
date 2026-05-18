"""
Calculadora AHP (Analytical Hierarchy Process)

Implementa el método AHP para calcular pesos a partir de comparaciones pareadas.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Random Index para validación de consistencia
RANDOM_INDEX = {
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


def calcular_pesos_ahp(matriz_comparacion: np.ndarray) -> Dict:
    """
    Calcula pesos AHP a partir de matriz de comparación pareada

    Args:
        matriz_comparacion: Matriz cuadrada NxN con comparaciones en escala Saaty (1-9)

    Returns:
        Dict con:
        - pesos: Array de pesos normalizados (suman 1.0)
        - lambda_max: Eigenvalue máximo
        - consistency_index: Índice de consistencia (CI)
        - consistency_ratio: Ratio de consistencia (CR)
        - is_consistent: True si CR < 0.10

    Escala Saaty:
    - 1: Igual importancia
    - 3: Moderadamente más importante
    - 5: Fuertemente más importante
    - 7: Muy fuertemente más importante
    - 9: Extremadamente más importante
    - 2, 4, 6, 8: Valores intermedios
    """
    n = len(matriz_comparacion)

    if matriz_comparacion.shape[0] != matriz_comparacion.shape[1]:
        raise ValueError("Matriz debe ser cuadrada")

    # Calcular eigenvalues y eigenvectors
    eigenvalues, eigenvectors = np.linalg.eig(matriz_comparacion)

    # Eigenvector principal (correspondiente al eigenvalue máximo)
    max_index = np.argmax(eigenvalues.real)
    principal_eigenvector = eigenvectors[:, max_index].real

    # Normalizar pesos (deben sumar 1.0)
    pesos = principal_eigenvector / np.sum(principal_eigenvector)

    # Validar consistencia
    lambda_max = eigenvalues[max_index].real
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0
    cr = ci / RANDOM_INDEX.get(n, 1.0) if n in RANDOM_INDEX else 0

    return {
        'pesos': pesos.tolist(),
        'lambda_max': float(lambda_max),
        'consistency_index': float(ci),
        'consistency_ratio': float(cr),
        'is_consistent': cr < 0.10,
        'n_criteria': n
    }


def validar_consistencia(matriz: np.ndarray) -> Tuple[float, bool]:
    """
    Valida consistencia de matriz AHP

    Args:
        matriz: Matriz de comparación

    Returns:
        (consistency_ratio, is_valid)
    """
    result = calcular_pesos_ahp(matriz)
    return result['consistency_ratio'], result['is_consistent']


def matriz_desde_comparaciones(comparaciones: List[float], n: int) -> np.ndarray:
    """
    Construye matriz AHP a partir de comparaciones del triángulo superior

    Args:
        comparaciones: Lista de comparaciones [a12, a13, a14, ..., a23, a24, ...]
        n: Dimensión de la matriz

    Returns:
        Matriz NxN simétrica (matriz[i,j] = 1/matriz[j,i])

    Ejemplo:
        Para n=3, comparaciones = [a12, a13, a23]
        Matriz:
        [1,   a12, a13]
        [1/a12, 1,   a23]
        [1/a13, 1/a23, 1]
    """
    expected_len = n * (n - 1) // 2

    if len(comparaciones) != expected_len:
        raise ValueError(f"Se esperan {expected_len} comparaciones para matriz {n}x{n}")

    matriz = np.ones((n, n))
    idx = 0

    # Llenar triángulo superior
    for i in range(n):
        for j in range(i + 1, n):
            matriz[i, j] = comparaciones[idx]
            matriz[j, i] = 1.0 / comparaciones[idx]  # Recíproco
            idx += 1

    return matriz


def interpretar_escala_saaty(value: float) -> str:
    """
    Interpreta valor en escala Saaty

    Args:
        value: Valor 1-9

    Returns:
        Descripción textual
    """
    if value == 1:
        return "Igual importancia"
    elif value <= 2:
        return "Ligeramente más importante"
    elif value <= 4:
        return "Moderadamente más importante"
    elif value <= 6:
        return "Fuertemente más importante"
    elif value <= 8:
        return "Muy fuertemente más importante"
    else:
        return "Extremadamente más importante"


# Ejemplo de uso
if __name__ == "__main__":
    # Ejemplo: Comparar 4 dotaciones (salud, educación, comercio, recreación)
    # Salud > Educación > Comercio > Recreación

    matriz_ejemplo = np.array([
        [1,   3,   5,   7],  # Salud vs [Salud, Educación, Comercio, Recreación]
        [1/3, 1,   3,   5],  # Educación vs ...
        [1/5, 1/3, 1,   3],  # Comercio vs ...
        [1/7, 1/5, 1/3, 1]   # Recreación vs ...
    ])

    resultado = calcular_pesos_ahp(matriz_ejemplo)

    print("Pesos calculados:")
    categorias = ['Salud', 'Educación', 'Comercio', 'Recreación']
    for cat, peso in zip(categorias, resultado['pesos']):
        print(f"  {cat}: {peso:.4f} ({peso * 100:.2f}%)")

    print(f"\nConsistency Ratio: {resultado['consistency_ratio']:.4f}")
    print(f"Consistente: {'Sí' if resultado['is_consistent'] else 'No'}")
