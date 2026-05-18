"""
Transport Indicator Configuration

Configuración del modelo gravity:
- Radios de influencia
- Pesos por tipo de transporte
- Parámetros de decay function
"""

# Radios de influencia (metros)
RADIOS = {
    'sitp': 800,            # Paradas SITP (bus)
    'transmilenio': 1500,   # Estaciones TransMilenio
    'metro': 2000,          # Estaciones Metro (Primera Línea)
    'bicicleta': 5000       # Futuro: ciclorutas
}

# Pesos por tipo de transporte (para suma ponderada)
PESOS_TRANSPORTE = {
    'transmilenio': 2.0,    # Mayor peso (sistema troncal)
    'metro': 3.0,           # Peso máximo (cuando se carguen estaciones)
    'sitp': 1.0,            # Peso base
    'bicicleta': 0.5        # Menor peso
}

# Configuración Metro de Bogotá
METRO_CONFIG = {
    'status': 'pendiente',  # 'pendiente' | 'cargado'
    'tabla': 'iug.estacion_metro',
    'radio_gravity_sql': 1500,  # Radio en la función gravity SQL (V103)
    'notas': (
        'Primera Línea del Metro de Bogotá. '
        'Cuando se carguen estaciones en iug.estacion_metro, '
        'redistribuir pesos PCA: ~0.35 metro, 0.30 TM, 0.20 SITP, 0.15 vías.'
    )
}

# Parámetros Gravity Model
GRAVITY_PARAMS = {
    'decay_function': 'exponential',  # 'exponential', 'inverse_square', 'linear'
    'beta': 0.001,  # Parámetro de decay para exponencial
    'min_distance': 50  # Distancia mínima considerada (metros)
}

# Normalización
NORMALIZATION = {
    'method': 'percentile',  # 'percentile', 'minmax', 'zscore'
    'partition_by_type': True,  # True = 0-5 por tipo, False = 0-5 global
    'target_min': 0,
    'target_max': 5
}
