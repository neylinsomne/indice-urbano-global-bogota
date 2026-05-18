"""
Global Urban Indicator Configuration (I_URB)

Configuración del Indicador Urbanístico Global:
- Pesos de cada sub-indicador
- Normalización final
- Interpretación de categorías
"""

# Pesos de componentes (deben sumar 1.0)
PESOS_INDICADORES = {
    'iacc': 0.25,     # 25% - Accesibilidad y transporte público
    'iseg': 0.20,     # 20% - Seguridad objetiva (criminalidad)
    'ihed': 0.25,     # 25% - Calidad hedónica (dimensión + dotaciones)
    'ipnu': 0.30      # 30% - Potencial normativo (POT 555)
}

# Alternativa: Pesos iguales
PESOS_IGUALES = {
    'iacc': 0.25,
    'iseg': 0.25,
    'ihed': 0.25,
    'ipnu': 0.25
}

# Alternativa: Mayor peso a normativo (para inversión)
PESOS_INVERSION = {
    'iacc': 0.20,
    'iseg': 0.15,
    'ihed': 0.20,
    'ipnu': 0.45      # Mayor peso al potencial de desarrollo
}

# Alternativa: Mayor peso a calidad de vida (para residencia)
PESOS_RESIDENCIAL = {
    'iacc': 0.30,     # Mayor accesibilidad
    'iseg': 0.30,     # Mayor seguridad
    'ihed': 0.30,     # Mayor calidad
    'ipnu': 0.10      # Menor importancia del POT
}

# Configuración activa (cambiar según necesidad)
PESOS_ACTIVOS = PESOS_INDICADORES  # Por defecto: pesos equilibrados

# Normalización
NORMALIZATION = {
    'method': 'weighted_average',  # Método: weighted_average, percentile, minmax
    'min_value': 0.0,
    'max_value': 5.0,
    'handle_nulls': 'skip',  # 'skip' = omitir del promedio, 'zero' = tratar como 0
    'min_indicators': 2  # Mínimo de indicadores no-null para calcular I_URB
}

# Interpretación de rangos I_URB
INTERPRETACION = {
    'excelente': {
        'min': 4.5,
        'max': 5.0,
        'label': 'Excelente',
        'descripcion': 'Ubicación premium. Alto potencial de desarrollo y calidad de vida.'
    },
    'muy_bueno': {
        'min': 4.0,
        'max': 4.5,
        'label': 'Muy Bueno',
        'descripcion': 'Ubicación muy atractiva. Buen balance entre desarrollo y calidad.'
    },
    'bueno': {
        'min': 3.5,
        'max': 4.0,
        'label': 'Bueno',
        'descripcion': 'Ubicación sólida. Potencial de valorización medio-alto.'
    },
    'regular': {
        'min': 3.0,
        'max': 3.5,
        'label': 'Regular',
        'descripcion': 'Ubicación promedio. Algunas limitaciones.'
    },
    'por_debajo_promedio': {
        'min': 2.5,
        'max': 3.0,
        'label': 'Por Debajo del Promedio',
        'descripcion': 'Ubicación con restricciones. Potencial limitado.'
    },
    'deficiente': {
        'min': 2.0,
        'max': 2.5,
        'label': 'Deficiente',
        'descripcion': 'Ubicación poco atractiva. Múltiples limitaciones.'
    },
    'muy_deficiente': {
        'min': 0.0,
        'max': 2.0,
        'label': 'Muy Deficiente',
        'descripcion': 'Ubicación no recomendada. Restricciones severas.'
    }
}

# Umbrales de alerta
ALERTAS = {
    'seguridad_baja': {
        'threshold': 2.5,
        'message': 'Zona con seguridad por debajo del promedio'
    },
    'accesibilidad_baja': {
        'threshold': 2.0,
        'message': 'Accesibilidad limitada a transporte público'
    },
    'potencial_muy_bajo': {
        'threshold': 2.0,
        'message': 'Potencial normativo muy bajo (restricciones POT)'
    }
}
