"""
Sistema de Cuestionario AHP

Genera preguntas de comparación pareada amigables y procesa respuestas del usuario.
"""
from typing import List, Dict, Tuple
from pydantic import BaseModel, Field
import numpy as np
from .ahp_calculator import calcular_pesos_ahp, matriz_desde_comparaciones


class CriterioAHP(BaseModel):
    """Criterio a comparar"""
    id: str = Field(..., description="ID único del criterio")
    nombre: str = Field(..., description="Nombre amigable")
    descripcion: str = Field(..., description="Descripción detallada")
    icono: str = Field(default="", description="Emoji o ícono")


class PreguntaComparacion(BaseModel):
    """Pregunta de comparación pareada"""
    id: str = Field(..., description="ID de la pregunta")
    criterio_a_id: str
    criterio_a_nombre: str
    criterio_b_id: str
    criterio_b_nombre: str
    pregunta: str = Field(..., description="Texto de la pregunta")
    escala_min: int = 1
    escala_max: int = 9
    opciones: List[Dict[str, str]] = Field(default_factory=list)


class RespuestasUsuario(BaseModel):
    """Respuestas del usuario al cuestionario"""
    respuestas: Dict[str, float] = Field(
        ...,
        description="Map de question_id -> valor en escala Saaty (1-9)"
    )


# Catálogos de criterios predefinidos

CRITERIOS_DOTACIONES = [
    CriterioAHP(
        id="salud",
        nombre="Salud",
        descripcion="Cercanía a hospitales, clínicas, centros médicos y farmacias",
        icono="🏥"
    ),
    CriterioAHP(
        id="educacion",
        nombre="Educación",
        descripcion="Cercanía a colegios y universidades",
        icono="🎓"
    ),
    CriterioAHP(
        id="comercio",
        nombre="Comercio",
        descripcion="Cercanía a centros comerciales y plazas de mercado",
        icono="🛒"
    ),
    CriterioAHP(
        id="cultura",
        nombre="Cultura",
        descripcion="Cercanía a bibliotecas, teatros y auditorios",
        icono="🎭"
    ),
    CriterioAHP(
        id="recreacion",
        nombre="Recreación",
        descripcion="Cercanía a parques y canchas deportivas",
        icono="⚽"
    )
]

CRITERIOS_TRANSPORTE = [
    CriterioAHP(
        id="transmilenio",
        nombre="TransMilenio",
        descripcion="Cercanía a estaciones de TransMilenio",
        icono="🚌"
    ),
    CriterioAHP(
        id="sitp",
        nombre="SITP",
        descripcion="Cercanía a paradas de bus SITP",
        icono="🚏"
    ),
    CriterioAHP(
        id="vias",
        nombre="Vías Principales",
        descripcion="Acceso a vías principales y autopistas",
        icono="🛣️"
    )
]

CRITERIOS_INDICADORES_PRINCIPALES = [
    CriterioAHP(
        id="iacc",
        nombre="Accesibilidad",
        descripcion="Proximidad a transporte público",
        icono="🚇"
    ),
    CriterioAHP(
        id="iseg",
        nombre="Seguridad",
        descripcion="Seguridad de la zona (baja criminalidad)",
        icono="🛡️"
    ),
    CriterioAHP(
        id="ihed",
        nombre="Calidad Urbana",
        descripcion="Dotaciones y calidad del entorno",
        icono="🏙️"
    ),
    CriterioAHP(
        id="ipnu",
        nombre="Potencial de Desarrollo",
        descripcion="Potencial de desarrollo según normativa POT",
        icono="📈"
    )
]


def generar_cuestionario(criterios: List[CriterioAHP]) -> List[PreguntaComparacion]:
    """
    Genera cuestionario de comparaciones pareadas

    Args:
        criterios: Lista de criterios a comparar

    Returns:
        Lista de preguntas ordenadas
    """
    preguntas = []
    n = len(criterios)

    # Generar todas las combinaciones (i,j) con i < j
    for i in range(n):
        for j in range(i + 1, n):
            crit_a = criterios[i]
            crit_b = criterios[j]

            pregunta = PreguntaComparacion(
                id=f"{crit_a.id}_vs_{crit_b.id}",
                criterio_a_id=crit_a.id,
                criterio_a_nombre=f"{crit_a.icono} {crit_a.nombre}",
                criterio_b_id=crit_b.id,
                criterio_b_nombre=f"{crit_b.icono} {crit_b.nombre}",
                pregunta=f"¿Qué es más importante para ti: {crit_a.nombre} o {crit_b.nombre}?",
                opciones=[
                    {"valor": "9", "texto": f"{crit_a.nombre} es EXTREMADAMENTE más importante"},
                    {"valor": "7", "texto": f"{crit_a.nombre} es MUY fuertemente más importante"},
                    {"valor": "5", "texto": f"{crit_a.nombre} es FUERTEMENTE más importante"},
                    {"valor": "3", "texto": f"{crit_a.nombre} es MODERADAMENTE más importante"},
                    {"valor": "1", "texto": "Ambos tienen IGUAL importancia"},
                    {"valor": "0.333", "texto": f"{crit_b.nombre} es MODERADAMENTE más importante"},
                    {"valor": "0.2", "texto": f"{crit_b.nombre} es FUERTEMENTE más importante"},
                    {"valor": "0.143", "texto": f"{crit_b.nombre} es MUY fuertemente más importante"},
                    {"valor": "0.111", "texto": f"{crit_b.nombre} es EXTREMADAMENTE más importante"}
                ]
            )

            preguntas.append(pregunta)

    return preguntas


def procesar_respuestas(
    criterios: List[CriterioAHP],
    respuestas: RespuestasUsuario
) -> Dict:
    """
    Procesa respuestas del usuario y calcula pesos AHP

    Args:
        criterios: Lista de criterios originales (en orden)
        respuestas: Respuestas del usuario

    Returns:
        Dict con:
        - pesos: Dict de criterio_id -> peso
        - consistency_ratio: Ratio de consistencia
        - is_consistent: Si la matriz es consistente
        - matriz_comparacion: Matriz generada
    """
    n = len(criterios)

    # Construir lista de comparaciones en orden
    comparaciones = []

    for i in range(n):
        for j in range(i + 1, n):
            question_id = f"{criterios[i].id}_vs_{criterios[j].id}"

            if question_id not in respuestas.respuestas:
                raise ValueError(f"Falta respuesta para: {question_id}")

            valor = respuestas.respuestas[question_id]
            comparaciones.append(valor)

    # Construir matriz
    matriz = matriz_desde_comparaciones(comparaciones, n)

    # Calcular pesos
    resultado = calcular_pesos_ahp(matriz)

    # Mapear pesos a IDs de criterios
    pesos_dict = {}
    for i, criterio in enumerate(criterios):
        pesos_dict[criterio.id] = resultado['pesos'][i]

    return {
        'pesos': pesos_dict,
        'consistency_ratio': resultado['consistency_ratio'],
        'is_consistent': resultado['is_consistent'],
        'matriz_comparacion': matriz.tolist()
    }


def get_cuestionario_dotaciones() -> List[PreguntaComparacion]:
    """Cuestionario para pesos de dotaciones"""
    return generar_cuestionario(CRITERIOS_DOTACIONES)


def get_cuestionario_transporte() -> List[PreguntaComparacion]:
    """Cuestionario para pesos de transporte"""
    return generar_cuestionario(CRITERIOS_TRANSPORTE)


def get_cuestionario_indicadores() -> List[PreguntaComparacion]:
    """Cuestionario para pesos de indicadores principales (I_URB)"""
    return generar_cuestionario(CRITERIOS_INDICADORES_PRINCIPALES)


# Ejemplo de uso
if __name__ == "__main__":
    print("=" * 80)
    print("EJEMPLO: Cuestionario de Dotaciones")
    print("=" * 80)

    preguntas = get_cuestionario_dotaciones()

    print(f"\nTotal de preguntas: {len(preguntas)}\n")

    for i, p in enumerate(preguntas, 1):
        print(f"Pregunta {i}: {p.pregunta}")
        print(f"  Comparando: {p.criterio_a_nombre} vs {p.criterio_b_nombre}")
        print()

    # Simular respuestas
    print("=" * 80)
    print("EJEMPLO: Procesando respuestas simuladas")
    print("=" * 80)

    respuestas_ejemplo = RespuestasUsuario(
        respuestas={
            "salud_vs_educacion": 5,      # Salud fuertemente más importante que educación
            "salud_vs_comercio": 7,       # Salud muy fuertemente más importante que comercio
            "salud_vs_cultura": 9,        # Salud extremadamente más importante que cultura
            "salud_vs_recreacion": 7,     # Salud muy fuertemente más importante que recreación
            "educacion_vs_comercio": 3,   # Educación moderadamente más importante que comercio
            "educacion_vs_cultura": 5,    # Educación fuertemente más importante que cultura
            "educacion_vs_recreacion": 3, # Educación moderadamente más importante que recreación
            "comercio_vs_cultura": 3,     # Comercio moderadamente más importante que cultura
            "comercio_vs_recreacion": 1,  # Comercio igual importancia que recreación
            "cultura_vs_recreacion": 1    # Cultura igual importancia que recreación
        }
    )

    resultado = procesar_respuestas(CRITERIOS_DOTACIONES, respuestas_ejemplo)

    print("\nPesos calculados:")
    for crit in CRITERIOS_DOTACIONES:
        peso = resultado['pesos'][crit.id]
        print(f"  {crit.icono} {crit.nombre:15s}: {peso:.4f} ({peso * 100:.2f}%)")

    print(f"\nConsistency Ratio: {resultado['consistency_ratio']:.4f}")
    print(f"Consistente: {'Sí ✓' if resultado['is_consistent'] else 'No ✗'}")
