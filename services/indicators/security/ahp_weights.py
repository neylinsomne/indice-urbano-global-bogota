"""
Calculadora de pesos AHP (Analytical Hierarchy Process) para criminalidad.
Genera matriz de comparación pareada y calcula pesos que suman 1.0
"""
import numpy as np

print("=" * 80)
print("CALCULADORA DE PESOS AHP PARA CRIMINALIDAD")
print("=" * 80)

# Matriz de comparación pareada (escala Saaty 1-9)
# Filas vs Columnas: Homicidios, Sexuales, Hurtos, Otros
# 
# Escala:
# 1 = Igual importancia
# 3 = Moderadamente más importante
# 5 = Fuertemente más importante
# 7 = Muy fuertemente más importante
# 9 = Extremadamente más importante

print("\nMatriz de Comparacion Pareada (Escala Saaty)")
print("-" * 80)

# Homicidios >> Sexuales > Hurtos >> Otros
matriz_ahp = np.array([
    [1,   3,   5,   9],  # Homicidios vs [Hom, Sex, Hur, Otros]
    [1/3, 1,   3,   7],  # Sexuales vs ...
    [1/5, 1/3, 1,   5],  # Hurtos vs ...
    [1/9, 1/7, 1/5, 1]   # Otros vs ...
])

delitos = ['Homicidios', 'Delitos Sexuales', 'Hurto Personas', 'Otros Delitos']

print("\n        Hom    Sex    Hur    Otros")
for i, delito in enumerate(delitos):
    print(f"{delito:15s} {matriz_ahp[i]}")

# Calcular pesos (eigenvector principal normalizado)
eigenvalues, eigenvectors = np.linalg.eig(matriz_ahp)

# Eigenvector correspondiente al eigenvalue máximo
max_index = np.argmax(eigenvalues)
principal_eigenvector = np.real(eigenvectors[:, max_index])

# Normalizar para que sumen 1
pesos = principal_eigenvector / np.sum(principal_eigenvector)

print("\n" + "=" * 80)
print("PESOS AHP CALCULADOS")
print("=" * 80)

total = 0
for delito, peso in zip(delitos, pesos):
    print(f"   {delito:20s}: {peso:.4f} ({peso*100:5.2f}%)")
    total += peso

print(f"\n   {'TOTAL':20s}: {total:.4f} ({total*100:5.2f}%)")

# Calcular Consistency Ratio (CR)
lambda_max = np.max(eigenvalues).real
n = len(delitos)
CI = (lambda_max - n) / (n - 1)

# Random Index para n=4
RI = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41}
CR = CI / RI[n]

print("\nValidacion de Consistencia")
print(f"   Consistency Index (CI): {CI:.4f}")
print(f"   Consistency Ratio (CR): {CR:.4f}")

if CR < 0.10:
    print(f"   OK Matriz consistente (CR < 0.10)")
else:
    print(f"   WARNING Matriz inconsistente (CR >= 0.10) - Revisar comparaciones")

# Generar SQL para insertar en BD
print("\n" + "=" * 80)
print("SQL PARA INSERTAR EN POSTGRESQL")
print("=" * 80)

mapping = {
    'Homicidios': 'homicidios',
    'Delitos Sexuales': 'delitos_sexuales',
    'Hurto Personas': 'hurto_personas',
    'Otros Delitos': 'otros_delitos'
}

print("""
INSERT INTO iug.ahp_pesos_crimen (tipo_delito, peso_ahp, descripcion) VALUES""")

for i, (delito, peso) in enumerate(zip(delitos, pesos)):
    tipo_db = mapping[delito]
    comma = "," if i < len(delitos) - 1 else ";"
    print(f"('{tipo_db}', {peso:.4f}, '{delito}'){comma}")

print("\nON CONFLICT (tipo_delito) DO UPDATE SET peso_ahp = EXCLUDED.peso_ahp;")

print("\n" + "=" * 80)
print("EJEMPLO DE USO")
print("=" * 80)

print("""
-- Calcular masa de crimen para una localidad
UPDATE iug.criminalidad_localidad
SET masa_crimen = 
    (homicidios_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='homicidios')) +
    (delitos_sexuales_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='delitos_sexuales')) +
    (hurto_personas_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='hurto_personas')) +
    (otros_delitos_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='otros_delitos'));
""")

print("=" * 80)

# Generar diccionario Python
print("\nDICCIONARIO PYTHON")
print("-" * 80)
print("pesos_ahp = {")
for delito, peso in zip(delitos, pesos):
    tipo_db = mapping[delito]
    print(f"    '{tipo_db}': {peso:.4f},")
print("}")
print(f"\n# Suma total: {sum(pesos):.6f}")

print("\n" + "=" * 80)
