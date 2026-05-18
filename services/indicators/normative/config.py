"""
Normative Indicator Configuration (I_PNU)

Configuración del indicador de Potencial Normativo de Uso del Suelo:
- Pesos de componentes
- Scoring de tratamiento urbanístico
- Scoring de edificabilidad
- Scoring de área de actividad
"""

# Pesos de componentes (deben sumar 1.0)
PESOS_COMPONENTES = {
    'tratamiento': 0.4,      # 40% - Define si se puede renovar/desarrollar
    'edificabilidad': 0.4,   # 40% - Determina densidad (pisos permitidos)
    'uso': 0.2               # 20% - Tipo de actividad económica
}

# Scoring de Tratamiento Urbanístico (1-5)
SCORE_TRATAMIENTO = {
    'renovacion': 5.0,       # Máximo potencial (demolición y construcción nueva)
    'desarrollo': 4.5,       # Alto potencial (zonas de expansión)
    'consolidacion': 3.0,    # Potencial medio (densificación moderada)
    'mejoramiento': 2.0,     # Potencial medio-bajo (intervenciones limitadas)
    'conservacion': 1.0,     # Restricciones fuertes (protección)
    'default': 2.5           # Valor por defecto
}

# Scoring de Edificabilidad (1-5)
SCORE_EDIFICABILIDAD = {
    '4': 5.0,    # Rango 4: >12 pisos (torres)
    '4A': 5.0,
    '4B': 5.0,
    '4C': 5.0,
    '4D': 5.0,
    '3': 4.0,    # Rango 3: 7-12 pisos (edificios medios-altos)
    '2': 3.0,    # Rango 2: 4-6 pisos (edificios bajos)
    '1': 2.0,    # Rango 1: 1-3 pisos (casas/unifamiliar)
    'default': 2.5  # Sin restricción explícita
}

# Scoring de Área de Actividad (1-5)
SCORE_AREA_ACTIVIDAD = {
    'AAERAE': 5.0,    # Área Estructurante - Actividad Económica (comercio)
    'AAGSM': 4.5,     # Grandes Servicios Metropolitanos
    'AAERVIS': 4.0,   # Área Estructurante - Vivienda y Servicios (mixto)
    'AAPGSU': 3.5,    # Proximidad - Generadora de Soporte
    'AAPRSU': 3.0,    # Proximidad - Receptora de Soporte (residencial)
    'PEMP': 1.0,      # Plan Especial Manejo y Protección (patrimonio)
    'default': 3.0    # Valor por defecto
}

# Normalización
NORMALIZATION = {
    'method': 'clamp',  # Método: clamp (0-5), percentile, minmax
    'min_value': 0.0,
    'max_value': 5.0
}

# Interpretación de rangos
INTERPRETACION = {
    'muy_alto': {'min': 4.5, 'max': 5.0, 'label': 'Muy Alto'},
    'alto': {'min': 4.0, 'max': 4.5, 'label': 'Alto'},
    'medio_alto': {'min': 3.5, 'max': 4.0, 'label': 'Medio-Alto'},
    'medio': {'min': 3.0, 'max': 3.5, 'label': 'Medio'},
    'medio_bajo': {'min': 2.5, 'max': 3.0, 'label': 'Medio-Bajo'},
    'bajo': {'min': 2.0, 'max': 2.5, 'label': 'Bajo'},
    'muy_bajo': {'min': 0.0, 'max': 2.0, 'label': 'Muy Bajo'}
}
