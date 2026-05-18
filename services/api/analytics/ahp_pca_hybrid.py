"""
Mejora #7: Pesos hibridos AHP-PCA para crimen.

El sistema actual tiene dos sistemas de pesos para crimen que se
contradicen:
- AHP (V21): juicio experto, pondera homicidios al 50%
- PCA (ICSU V117): datos, pondera lesiones personales al 17.7%

El AHP captura SEVERIDAD (juicio normativo).
El PCA captura DISCRIMINACION ESPACIAL (que delito diferencia mas
las zonas).

Ambos son utiles. La propuesta: combinarlos linealmente.

    w_i_hibrido = (alpha * w_i_AHP + (1-alpha) * w_i_PCA) /
                  sum_j [alpha * w_j_AHP + (1-alpha) * w_j_PCA]

Con alpha = 0.5 (default), severidad y discriminacion pesan igual.

Referencia: documento mejoras_estadisticas.tex, Seccion 'Cambio 7'.
"""
import logging
import math
from typing import Optional

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)


# Pesos AHP del sistema actual (V21)
PESOS_AHP_V21 = {
    'homicidios': 0.5660,
    'lesiones_personales': 0.0,
    'violencia_intrafamiliar': 0.0,
    'delitos_sexuales': 0.2670,
    'hurto_personas': 0.1200,
    'hurto_residencias': 0.0,
    'hurto_automotores': 0.0,
    'otros': 0.0470,
}

# Pesos PCA del ICSU (V117)
PESOS_PCA_ICSU = {
    'homicidios': 0.133,
    'lesiones_personales': 0.177,
    'violencia_intrafamiliar': 0.161,
    'delitos_sexuales': 0.164,
    'hurto_personas': 0.154,
    'hurto_residencias': 0.124,
    'hurto_automotores': 0.087,
    'otros': 0.0,
}


def calcular_pesos_hibridos(alpha: float = 0.5) -> dict:
    """
    Combina AHP y PCA segun w_hibrido = alpha*w_AHP + (1-alpha)*w_PCA.

    Args:
        alpha: Peso del juicio AHP. 0=solo PCA, 1=solo AHP.

    Returns:
        {
            'alpha': float,
            'pesos_hibridos': {tipo_delito: peso},
            'pesos_ahp': {...},
            'pesos_pca': {...},
            'cambios_vs_ahp': {tipo_delito: delta_pp}
        }
    """
    if not 0 <= alpha <= 1:
        raise ValueError(f"alpha debe estar en [0,1], recibido {alpha}")

    delitos = list(PESOS_AHP_V21.keys())
    pesos_combinados_no_norm = {}

    for d in delitos:
        w_ahp = PESOS_AHP_V21.get(d, 0.0)
        w_pca = PESOS_PCA_ICSU.get(d, 0.0)
        pesos_combinados_no_norm[d] = alpha * w_ahp + (1 - alpha) * w_pca

    total = sum(pesos_combinados_no_norm.values())
    if total < 1e-10:
        raise ValueError("Suma de pesos hibridos es cero")

    pesos_hibridos = {d: round(w / total, 4)
                      for d, w in pesos_combinados_no_norm.items()}

    cambios = {d: round(pesos_hibridos[d] - PESOS_AHP_V21.get(d, 0.0), 4)
               for d in delitos}

    return {
        'alpha': alpha,
        'interpretacion_alpha': (
            'Solo PCA (datos)' if alpha == 0 else
            'Solo AHP (juicio)' if alpha == 1 else
            f'{alpha*100:.0f}% AHP + {(1-alpha)*100:.0f}% PCA'
        ),
        'pesos_hibridos': pesos_hibridos,
        'pesos_ahp_v21': PESOS_AHP_V21,
        'pesos_pca_icsu': PESOS_PCA_ICSU,
        'cambios_vs_ahp_actual_pp': cambios,
        'delitos_agregados': [d for d, w in pesos_hibridos.items()
                              if w > 0 and PESOS_AHP_V21.get(d, 0) == 0],
        'delitos_reducidos': [d for d, c in cambios.items() if c < -0.05],
        'referencia': 'mejoras_estadisticas.tex Cambio #7; AHP Saaty (1980); PCA ICSU (V117)',
    }


def sensibilidad_alpha(alphas: Optional[list] = None) -> dict:
    """
    Calcula como cambian los pesos para diferentes valores de alpha.

    Util para visualizar transicion suave AHP -> PCA.
    """
    if alphas is None:
        alphas = [0.0, 0.25, 0.5, 0.75, 1.0]

    series_por_delito = {d: [] for d in PESOS_AHP_V21.keys()}

    for alpha in alphas:
        result = calcular_pesos_hibridos(alpha)
        for delito, peso in result['pesos_hibridos'].items():
            series_por_delito[delito].append({
                'alpha': alpha,
                'peso': peso,
            })

    return {
        'metodologia': 'Sensibilidad de pesos al parametro alpha',
        'alphas_evaluados': alphas,
        'series_por_delito': series_por_delito,
        'recomendacion': (
            'alpha=0.5 balance neutro. '
            'alpha=0.7 si se prioriza juicio normativo (peritaje). '
            'alpha=0.3 si se prioriza adecuacion empirica (academia).'
        ),
    }


async def aplicar_pesos_hibridos_localidad(
    conn: asyncpg.Connection,
    alpha: float = 0.5,
) -> dict:
    """
    Recalcula la masa de crimen para todas las localidades usando
    los pesos hibridos. NO actualiza la tabla; solo simula.

    Returns:
        {
            'localidades': [
                {nombre, masa_crimen_actual, masa_crimen_hibrida,
                 cambio_pct, ranking_actual, ranking_hibrido}
            ]
        }
    """
    pesos = calcular_pesos_hibridos(alpha)['pesos_hibridos']

    rows = await conn.fetch("""
        SELECT codigo_localidad, nombre_localidad,
               homicidios_2024, delitos_sexuales_2024,
               hurto_personas_2024, otros_delitos_2024,
               masa_crimen
        FROM iug.criminalidad_localidad
        ORDER BY nombre_localidad
    """)

    localidades = []
    for r in rows:
        # Mapeo a tipos de delito
        h = float(r['homicidios_2024'] or 0)
        s = float(r['delitos_sexuales_2024'] or 0)
        hp = float(r['hurto_personas_2024'] or 0)
        o = float(r['otros_delitos_2024'] or 0)

        # Masa hibrida (solo con los 4 tipos disponibles en V21)
        masa_hibrida = (
            h * pesos.get('homicidios', 0) +
            s * pesos.get('delitos_sexuales', 0) +
            hp * pesos.get('hurto_personas', 0) +
            o * pesos.get('otros', 0)
        )

        masa_actual = float(r['masa_crimen'] or 0)
        cambio_pct = ((masa_hibrida - masa_actual) / masa_actual * 100
                      if masa_actual > 0 else 0)

        localidades.append({
            'codigo': r['codigo_localidad'],
            'nombre': r['nombre_localidad'],
            'masa_crimen_actual_v21': round(masa_actual, 2),
            'masa_crimen_hibrida': round(masa_hibrida, 2),
            'cambio_pct': round(cambio_pct, 2),
        })

    # Rankings
    sorted_actual = sorted(localidades, key=lambda x: -x['masa_crimen_actual_v21'])
    sorted_hibrido = sorted(localidades, key=lambda x: -x['masa_crimen_hibrida'])

    rank_map_actual = {l['codigo']: i + 1 for i, l in enumerate(sorted_actual)}
    rank_map_hibrido = {l['codigo']: i + 1 for i, l in enumerate(sorted_hibrido)}

    for l in localidades:
        l['ranking_actual'] = rank_map_actual[l['codigo']]
        l['ranking_hibrido'] = rank_map_hibrido[l['codigo']]
        l['cambio_ranking'] = l['ranking_actual'] - l['ranking_hibrido']

    # Spearman entre rankings
    actual_ranks = [rank_map_actual[l['codigo']] for l in localidades]
    hibrido_ranks = [rank_map_hibrido[l['codigo']] for l in localidades]

    from scipy import stats as sp_stats
    rho, p_val = sp_stats.spearmanr(actual_ranks, hibrido_ranks)

    return {
        'alpha': alpha,
        'pesos_hibridos': pesos,
        'localidades': localidades,
        'spearman_rankings': {
            'rho': round(float(rho), 4),
            'p_value': round(float(p_val), 6),
            'interpretacion': (
                f'Rankings altamente correlacionados (rho={rho:.3f})'
                if rho > 0.85 else
                f'Rankings difieren significativamente (rho={rho:.3f})'
            ),
        },
        'mayores_cambios': sorted(
            localidades, key=lambda x: -abs(x['cambio_ranking'])
        )[:5],
    }
