"""
Mejora #15: Indices de Sobol para descomposicion de varianza del IUG.

Pregunta clave: ¿Que parametros del sistema importan mas para la
varianza del IUG?

Sobol' (1993) descompone la varianza total como:
    V(Y) = sum V_i + sum V_ij + ... + V_{1,2,...,p}

donde:
    V_i = V[E(Y|X_i)]              (efecto de primer orden)
    V_T = V_i + sum_j V_{i,j} + ... (efecto total, incluye interacciones)

Los indices Sobol son:
    S_i = V_i / V(Y)               (sensibilidad de primer orden)
    S_T = V_T / V(Y)               (sensibilidad total)

Si S_i << S_T => las interacciones de X_i con otros parametros
importan mas que su efecto directo.

Implementacion: muestreo Saltelli (2010) sobre los pesos del IUG.
"""
import logging
from typing import Optional

import numpy as np
import asyncpg

logger = logging.getLogger(__name__)


def saltelli_sample(n_samples: int, n_params: int) -> tuple:
    """
    Genera matrices A, B, AB para indices Sobol de primer orden y
    totales (Saltelli, 2010).

    Returns:
        A: (n, p) matriz base
        B: (n, p) matriz alterna
        AB: lista de p matrices, cada una con A pero columna i de B
    """
    rng = np.random.default_rng(42)
    A = rng.uniform(0, 1, size=(n_samples, n_params))
    B = rng.uniform(0, 1, size=(n_samples, n_params))

    AB = []
    for i in range(n_params):
        ab = A.copy()
        ab[:, i] = B[:, i]
        AB.append(ab)

    return A, B, AB


def normalizar_pesos(pesos_raw: np.ndarray) -> np.ndarray:
    """Normaliza filas para que sumen 1, con minimo 0.05 por componente."""
    pesos_min = np.maximum(pesos_raw, 0.05)
    return pesos_min / pesos_min.sum(axis=1, keepdims=True)


def calcular_iurb_con_pesos(X_indicadores: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    """
    Calcula IURB para todos los inmuebles dados pesos.

    Args:
        X_indicadores: (n_inmuebles, p_subindices)
        pesos: (n_simulaciones, p_subindices)

    Returns:
        IURB promedio por simulacion: (n_simulaciones,)
    """
    iurb_promedios = np.zeros(len(pesos))
    for s in range(len(pesos)):
        w = pesos[s]
        iurb_inmuebles = (X_indicadores * w).sum(axis=1)
        iurb_promedios[s] = iurb_inmuebles.mean()
    return iurb_promedios


def sobol_indices(Y_A: np.ndarray, Y_B: np.ndarray, Y_AB: list) -> dict:
    """
    Calcula indices Sobol S_i (primer orden) y S_Ti (total) usando
    los estimadores de Saltelli (2010).

    Args:
        Y_A: outputs del modelo en muestra A
        Y_B: outputs en muestra B
        Y_AB: lista de outputs en cada matriz mixta AB_i

    Returns:
        {
            'S_i': [...],   # primer orden
            'S_T': [...],   # total
        }
    """
    n = len(Y_A)
    var_Y = float(np.var(np.concatenate([Y_A, Y_B])))

    if var_Y < 1e-10:
        return {'error': 'Varianza de salida es cero'}

    S_i = []
    S_T = []
    for i, Y_AB_i in enumerate(Y_AB):
        # Saltelli 2010 estimator
        s_i = (np.mean(Y_B * (Y_AB_i - Y_A))) / var_Y
        s_t = (0.5 * np.mean((Y_A - Y_AB_i) ** 2)) / var_Y

        S_i.append(round(float(s_i), 4))
        S_T.append(round(float(s_t), 4))

    return {'S_i': S_i, 'S_T': S_T}


async def sobol_sensibilidad_iurb(
    conn: asyncpg.Connection,
    n_samples: int = 1024,
    tipo_inmueble: Optional[str] = None,
) -> dict:
    """
    Ejecuta analisis Sobol sobre los pesos del IUG.

    Para cada simulacion s:
        1. Generar pesos aleatorios w_s en simplex
        2. Calcular IUG promedio de la poblacion con esos pesos
    Y luego calcular S_i, S_T para cada peso.

    Args:
        n_samples: numero de muestras Saltelli (recomendado 512+)
        tipo_inmueble: filtro opcional

    Returns:
        Indices Sobol de primer orden y totales por subindice.
    """
    SUBINDICES = ['iacc', 'iseg', 'ihed', 'idot', 'ipnu']

    # Obtener matriz de indicadores
    where = ["is_outlier = FALSE", "iurb > 0",
             "iacc IS NOT NULL", "iseg IS NOT NULL",
             "ihed IS NOT NULL", "idot IS NOT NULL", "ipnu IS NOT NULL"]
    params = []
    if tipo_inmueble:
        where.append("tipo_inmueble = $1")
        params.append(tipo_inmueble)
    else:
        where.append("tipo_inmueble IN ('Apartamento', 'Casa')")

    rows = await conn.fetch(
        f"SELECT iacc, iseg, ihed, idot, ipnu FROM iug.inmueble WHERE {' AND '.join(where)}",
        *params,
    )
    if len(rows) < 50:
        return {'error': f'n={len(rows)} insuficiente'}

    X = np.array([[float(r[s]) for s in SUBINDICES] for r in rows])

    # Generar muestras Saltelli sobre pesos (5 parametros, simplex)
    A, B, AB = saltelli_sample(n_samples, len(SUBINDICES))
    A_norm = normalizar_pesos(A)
    B_norm = normalizar_pesos(B)
    AB_norm = [normalizar_pesos(ab) for ab in AB]

    # Output: IURB promedio para cada conjunto de pesos
    Y_A = calcular_iurb_con_pesos(X, A_norm)
    Y_B = calcular_iurb_con_pesos(X, B_norm)
    Y_AB = [calcular_iurb_con_pesos(X, ab) for ab in AB_norm]

    sobol = sobol_indices(Y_A, Y_B, Y_AB)

    if 'error' in sobol:
        return sobol

    return {
        'metodologia': 'Indices de Sobol (Saltelli 2010)',
        'n_samples': n_samples,
        'n_inmuebles': len(X),
        'tipo_inmueble': tipo_inmueble or 'vivienda (Apto + Casa)',
        'parametros_evaluados': SUBINDICES,
        'indices_primer_orden': {
            SUBINDICES[i]: sobol['S_i'][i] for i in range(len(SUBINDICES))
        },
        'indices_totales': {
            SUBINDICES[i]: sobol['S_T'][i] for i in range(len(SUBINDICES))
        },
        'interaccion_pct': {
            SUBINDICES[i]: round(sobol['S_T'][i] - sobol['S_i'][i], 4)
            for i in range(len(SUBINDICES))
        },
        'parametro_mas_influyente': SUBINDICES[int(np.argmax(sobol['S_T']))],
        'interpretacion': _interpretar_sobol(sobol['S_i'], sobol['S_T'], SUBINDICES),
        'referencia': 'Sobol, I. M. (1993); Saltelli, A. (2010). Comp. Phys. Comm.',
    }


def _interpretar_sobol(S_i: list, S_T: list, names: list) -> str:
    """Genera interpretacion textual de los indices Sobol."""
    interp = []

    # Parametro dominante
    idx_max = int(np.argmax(S_T))
    interp.append(
        f"{names[idx_max]} es el parametro MAS INFLUYENTE en el IUG "
        f"(S_T = {S_T[idx_max]:.3f})."
    )

    # Interacciones fuertes
    interaccion_max = max((s_t - s_i, n)
                          for s_t, s_i, n in zip(S_T, S_i, names))
    if interaccion_max[0] > 0.05:
        interp.append(
            f"{interaccion_max[1]} tiene fuertes interacciones con otros "
            f"pesos (delta = {interaccion_max[0]:.3f})."
        )

    # Parametros irrelevantes
    irrelevantes = [n for s_t, n in zip(S_T, names) if s_t < 0.05]
    if irrelevantes:
        interp.append(
            f"Parametros con baja sensibilidad (<5% varianza): "
            f"{', '.join(irrelevantes)}. Su peso podria fijarse sin "
            "alterar el resultado."
        )

    return ' '.join(interp)
