"""
Indicador Compuesto de Seguridad Urbana — Bogota 2024
=====================================================
Metodologia: PCA (Analisis de Componentes Principales)
Referencia:  OECD/JRC Handbook on Constructing Composite Indicators (2008)

Fuentes de datos:
  - DAILoc.geojson: 11 tipos de delito por localidad (2024) — datos objetivos
  - EPV 2024 (CCB): Percepcion, victimizacion, espacios publicos — datos subjetivos

Pipeline:
  1. Cargar y fusionar datos objetivos + subjetivos por localidad
  2. Normalizar (z-score)
  3. Tests de adecuacion: KMO + Bartlett
  4. PCA por dimension + PCA global
  5. Pesos derivados de loadings del PC1
  6. Score compuesto 0-5
  7. Analisis de sensibilidad Monte Carlo
  8. Clustering post-hoc (K-means)
  9. Exportar JSON + reporte
"""

import json
import math
import os
from collections import OrderedDict

# ── Utilidades numericas (sin dependencia de sklearn/scipy) ──

def mean(v):
    return sum(v) / len(v)

def std(v, ddof=1):
    m = mean(v)
    return math.sqrt(sum((x - m)**2 for x in v) / (len(v) - ddof))

def zscore(v):
    m, s = mean(v), std(v)
    if s == 0:
        return [0.0] * len(v)
    return [(x - m) / s for x in v]

def minmax(v, lo=0, hi=5):
    mn, mx = min(v), max(v)
    if mx == mn:
        return [2.5] * len(v)
    return [lo + (x - mn) / (mx - mn) * (hi - lo) for x in v]

def corr_matrix(matrix):
    """Calcula la matriz de correlacion de Pearson. matrix = [[col1], [col2], ...]"""
    p = len(matrix)
    R = [[0.0]*p for _ in range(p)]
    for i in range(p):
        for j in range(p):
            if i == j:
                R[i][j] = 1.0
            elif j > i:
                xi, xj = matrix[i], matrix[j]
                n = len(xi)
                mx, my = mean(xi), mean(xj)
                num = sum((xi[k]-mx)*(xj[k]-my) for k in range(n))
                dx = math.sqrt(sum((xi[k]-mx)**2 for k in range(n)))
                dy = math.sqrt(sum((xj[k]-my)**2 for k in range(n)))
                R[i][j] = num / (dx * dy) if dx*dy > 0 else 0
                R[j][i] = R[i][j]
    return R

def mat_inverse(M):
    """Inversa por Gauss-Jordan para matrices NxN."""
    n = len(M)
    A = [row[:] + [1.0 if i==j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for col in range(n):
        max_row = max(range(col, n), key=lambda r: abs(A[r][col]))
        A[col], A[max_row] = A[max_row], A[col]
        piv = A[col][col]
        if abs(piv) < 1e-12:
            return None
        for j in range(2*n):
            A[col][j] /= piv
        for row in range(n):
            if row != col:
                f = A[row][col]
                for j in range(2*n):
                    A[row][j] -= f * A[col][j]
    return [row[n:] for row in A]

def mat_det(M):
    """Determinante por eliminacion gaussiana."""
    n = len(M)
    A = [row[:] for row in M]
    det = 1.0
    for col in range(n):
        max_row = max(range(col, n), key=lambda r: abs(A[r][col]))
        if max_row != col:
            A[col], A[max_row] = A[max_row], A[col]
            det *= -1
        if abs(A[col][col]) < 1e-15:
            return 0.0
        det *= A[col][col]
        for row in range(col+1, n):
            f = A[row][col] / A[col][col]
            for j in range(col, n):
                A[row][j] -= f * A[col][j]
    return det

def kmo_test(R):
    """
    Kaiser-Meyer-Olkin (KMO) measure of sampling adequacy.
    KMO = sum(r_ij^2) / (sum(r_ij^2) + sum(q_ij^2))
    donde q_ij son las correlaciones parciales (anti-image).
    """
    n = len(R)
    Rinv = mat_inverse(R)
    if Rinv is None:
        return 0.0
    # Correlaciones parciales (anti-image)
    Q = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            Q[i][j] = -Rinv[i][j] / math.sqrt(Rinv[i][i] * Rinv[j][j]) if i != j else 1.0

    sum_r2 = sum(R[i][j]**2 for i in range(n) for j in range(n) if i != j)
    sum_q2 = sum(Q[i][j]**2 for i in range(n) for j in range(n) if i != j)

    if sum_r2 + sum_q2 == 0:
        return 0.0
    return sum_r2 / (sum_r2 + sum_q2)

def bartlett_test(R, n_obs):
    """
    Bartlett's test of sphericity.
    Chi2 = -((n-1) - (2p+5)/6) * ln(det(R))
    """
    p = len(R)
    det = mat_det(R)
    if det <= 0:
        return float('inf'), 0.0
    chi2 = -((n_obs - 1) - (2*p + 5)/6) * math.log(det)
    df = p * (p - 1) / 2
    # Aproximacion p-value (chi2 con df grados de libertad)
    # Para df grande, usamos aproximacion normal
    if df > 0:
        z = math.sqrt(2*chi2) - math.sqrt(2*df - 1)
        # P(Z > z) aprox
        p_value = 0.5 * math.erfc(z / math.sqrt(2)) if z < 10 else 0.0
    else:
        p_value = 1.0
    return chi2, p_value

def power_iteration_pca(cov_matrix, n_components=None, max_iter=1000, tol=1e-10):
    """
    PCA via deflation + power iteration.
    Retorna (eigenvalues, eigenvectors) ordenados descendente.
    """
    import random
    random.seed(42)
    n = len(cov_matrix)
    if n_components is None:
        n_components = n

    A = [row[:] for row in cov_matrix]
    eigenvalues = []
    eigenvectors = []

    for _ in range(n_components):
        # Vector aleatorio inicial
        v = [random.gauss(0, 1) for _ in range(n)]
        norm = math.sqrt(sum(x**2 for x in v))
        v = [x/norm for x in v]

        for iteration in range(max_iter):
            # Av
            Av = [sum(A[i][j]*v[j] for j in range(n)) for i in range(n)]
            # eigenvalue = v^T Av
            lam = sum(v[i]*Av[i] for i in range(n))
            # normalizar
            norm = math.sqrt(sum(x**2 for x in Av))
            if norm < 1e-15:
                break
            v_new = [x/norm for x in Av]
            # convergencia
            diff = math.sqrt(sum((v_new[i]-v[i])**2 for i in range(n)))
            v = v_new
            if diff < tol:
                break

        lam = sum(v[i] * sum(A[i][j]*v[j] for j in range(n)) for i in range(n))
        eigenvalues.append(lam)
        eigenvectors.append(v[:])

        # Deflacion: A = A - lam * v * v^T
        for i in range(n):
            for j in range(n):
                A[i][j] -= lam * v[i] * v[j]

    return eigenvalues, eigenvectors


def kmeans(data, k, max_iter=100):
    """K-means simple. data = lista de vectores."""
    import random
    random.seed(42)
    n = len(data)
    dim = len(data[0])

    # Inicializar centroides (k-means++)
    centroids = [data[random.randint(0, n-1)][:]]
    for _ in range(1, k):
        dists = []
        for point in data:
            min_d = min(sum((point[d]-c[d])**2 for d in range(dim)) for c in centroids)
            dists.append(min_d)
        total = sum(dists)
        if total == 0:
            centroids.append(data[random.randint(0, n-1)][:])
            continue
        probs = [d/total for d in dists]
        r = random.random()
        cumsum = 0
        for i, p in enumerate(probs):
            cumsum += p
            if cumsum >= r:
                centroids.append(data[i][:])
                break

    labels = [0] * n
    for _ in range(max_iter):
        # Asignar
        new_labels = []
        for point in data:
            dists = [sum((point[d]-c[d])**2 for d in range(dim)) for c in centroids]
            new_labels.append(dists.index(min(dists)))

        if new_labels == labels:
            break
        labels = new_labels

        # Actualizar centroides
        for c in range(k):
            members = [data[i] for i in range(n) if labels[i] == c]
            if members:
                centroids[c] = [sum(m[d] for m in members)/len(members) for d in range(dim)]

    return labels, centroids


# ═══════════════════════════════════════════════════════════════
# PASO 1: CARGAR DATOS
# ═══════════════════════════════════════════════════════════════

print("=" * 80)
print("INDICADOR COMPUESTO DE SEGURIDAD — PCA")
print("Metodologia OECD/JRC (2008)")
print("=" * 80)

script_dir = os.path.dirname(os.path.abspath(__file__))

# 1a. Datos objetivos: DAILoc.geojson
print("\n[1/9] Cargando datos objetivos (DAILoc.geojson)...")
with open(os.path.join(script_dir, 'DAILoc.geojson'), 'r', encoding='utf-8') as f:
    dailoc = json.load(f)

CRIME_FIELDS_2024 = {
    'CMH24CONT':  'homicidios',
    'CMLP24CONT': 'lesiones_personales',
    'CMHP24CONT': 'hurto_personas',
    'CMHR24CONT': 'hurto_residencias',
    'CMHA24CONT': 'hurto_automotores',
    'CMHB24CONT': 'hurto_bicicletas',
    'CMHCE24CON': 'hurto_comercio',
    'CMHM24CONT': 'hurto_motos',
    'CMHC24CONT': 'hurto_celulares',
    'CMDS24CONT': 'delitos_sexuales',
    'CMVI24CONT': 'violencia_intrafamiliar',
}

# Mapa de normalizacion de nombres de localidades
LOC_NORMALIZE = {
    'USAQUEN': 'Usaquen', 'CHAPINERO': 'Chapinero', 'SANTA FE': 'Santa Fe',
    'SAN CRISTOBAL': 'San Cristobal', 'USME': 'Usme', 'TUNJUELITO': 'Tunjuelito',
    'BOSA': 'Bosa', 'KENNEDY': 'Kennedy', 'FONTIBON': 'Fontibon',
    'ENGATIVA': 'Engativa', 'SUBA': 'Suba', 'BARRIOS UNIDOS': 'Barrios Unidos',
    'TEUSAQUILLO': 'Teusaquillo', 'LOS MARTIRES': 'Los Martires',
    'ANTONIO NARINO': 'Antonio Narino', 'PUENTE ARANDA': 'Puente Aranda',
    'LA CANDELARIA': 'La Candelaria', 'RAFAEL URIBE URIBE': 'Rafael Uribe Uribe',
    'CIUDAD BOLIVAR': 'Ciudad Bolivar',
    # Variaciones con encoding roto
    'FONTIB\u00d3N': 'Fontibon', 'ENGATIV\u00c1': 'Engativa',
    'LOS M\u00c1RTIRES': 'Los Martires', 'ANTONIO NARI\u00d1O': 'Antonio Narino',
    'USAQU\u00c9N': 'Usaquen', 'SAN CRIST\u00d3BAL': 'San Cristobal',
    'CIUDAD BOL\u00cdVAR': 'Ciudad Bolivar',
    'RAFAEL URIBE': 'Rafael Uribe Uribe',
}

obj_data = {}
for feat in dailoc['features']:
    props = feat['properties']
    raw_name = (props.get('CMNOMLOCAL') or '').strip()
    loc_name = LOC_NORMALIZE.get(raw_name.upper(), raw_name)
    if loc_name in ('', 'Sin localizacion', 'SIN LOCALIZACION'):
        continue

    crimes = {}
    for field, label in CRIME_FIELDS_2024.items():
        crimes[label] = float(props.get(field) or 0)

    # Area en km2 para tasas
    area_m2 = float(props.get('SHAPE_AREA') or 1)
    area_km2 = area_m2 / 1e6
    crimes['area_km2'] = area_km2

    obj_data[loc_name] = crimes

print(f"   Localidades con datos objetivos: {len(obj_data)}")

# 1b. Datos subjetivos: EPV 2024
print("[2/9] Cargando datos subjetivos (EPV 2024)...")
with open(os.path.join(script_dir, 'epv_2024_analisis_completo.json'), 'r', encoding='utf-8') as f:
    epv_data = json.load(f)

epv_by_loc = {}
for entry in epv_data:
    epv_by_loc[entry['localidad']] = entry

print(f"   Localidades con datos subjetivos: {len(epv_by_loc)}")

# 1c. Fusionar
print("[3/9] Fusionando datasets...")
localidades = sorted(set(obj_data.keys()) & set(epv_by_loc.keys()))
print(f"   Localidades emparejadas: {len(localidades)}")

if len(localidades) < 10:
    print("   WARN: Localidades no emparejadas (objetivas):",
          set(obj_data.keys()) - set(epv_by_loc.keys()))
    print("   WARN: Localidades no emparejadas (subjetivas):",
          set(epv_by_loc.keys()) - set(obj_data.keys()))

# ═══════════════════════════════════════════════════════════════
# PASO 2: CONSTRUIR MATRIZ DE VARIABLES
# ═══════════════════════════════════════════════════════════════

# Variables Dimension 1 — OBJETIVA (criminalidad dura)
# Usamos tasas por km2 para normalizar por tamanio de localidad
DIM1_VARS = OrderedDict([
    ('homicidios_km2',        'Homicidios / km2'),
    ('lesiones_km2',          'Lesiones personales / km2'),
    ('hurto_pers_km2',        'Hurto personas / km2'),
    ('hurto_resid_km2',       'Hurto residencias / km2'),
    ('hurto_auto_km2',        'Hurto automotores / km2'),
    ('delitos_sex_km2',       'Delitos sexuales / km2'),
    ('violencia_intraf_km2',  'Violencia intrafamiliar / km2'),
])

# Variables Dimension 2 — SUBJETIVA (percepcion + victimizacion encuestada)
DIM2_VARS = OrderedDict([
    ('pct_barrio_inseguro',     '% Barrio inseguro'),
    ('score_barrio_inv',        'Score barrio (invertido, mayor=peor)'),
    ('pct_victima_delito',      '% Victima de delito'),
    ('pct_testigo_delito',      '% Testigo de delito'),
    ('pct_inseg_aumento',       '% Percibe aumento inseguridad'),
    ('score_espacios_pub',      'Score inseg. espacios publicos (invertido)'),
    ('score_policia_inv',       'Score policia (invertido, mayor=peor)'),
    ('pct_hogar_victima',       '% Hogar victima'),
])

# Construir vectores
dim1_matrix = {var: [] for var in DIM1_VARS}
dim2_matrix = {var: [] for var in DIM2_VARS}

for loc in localidades:
    obj = obj_data[loc]
    epv = epv_by_loc[loc]
    area = obj['area_km2']

    # Dimension 1: tasas por km2
    dim1_matrix['homicidios_km2'].append(obj['homicidios'] / area)
    dim1_matrix['lesiones_km2'].append(obj['lesiones_personales'] / area)
    dim1_matrix['hurto_pers_km2'].append(obj['hurto_personas'] / area)
    dim1_matrix['hurto_resid_km2'].append(obj['hurto_residencias'] / area)
    dim1_matrix['hurto_auto_km2'].append(obj['hurto_automotores'] / area)
    dim1_matrix['delitos_sex_km2'].append(obj['delitos_sexuales'] / area)
    dim1_matrix['violencia_intraf_km2'].append(obj['violencia_intrafamiliar'] / area)

    # Dimension 2: percepcion
    dim2_matrix['pct_barrio_inseguro'].append(epv['pct_barrio_inseguro'])
    # Invertir score barrio (en EPV, 5=muy seguro, 1=muy inseguro)
    # Para que mayor = mas inseguro:
    dim2_matrix['score_barrio_inv'].append(5.0 - epv['score_barrio_1a5'])
    dim2_matrix['pct_victima_delito'].append(epv['pct_victima_delito'])
    dim2_matrix['pct_testigo_delito'].append(epv['pct_testigo_delito'])
    dim2_matrix['pct_inseg_aumento'].append(epv['pct_inseg_aumento'])

    # Score promedio de inseguridad en espacios publicos (invertir: mayor=peor)
    esp = epv['espacios_publicos']
    avg_esp = mean(list(esp.values()))
    dim2_matrix['score_espacios_pub'].append(5.0 - avg_esp)

    # Score policia invertido (mayor score policial = mejor, invertimos)
    dim2_matrix['score_policia_inv'].append(5.0 - epv['score_policia_1a5'])
    dim2_matrix['pct_hogar_victima'].append(epv['pct_hogar_victima'])


# ═══════════════════════════════════════════════════════════════
# PASO 3: NORMALIZAR (z-score)
# ═══════════════════════════════════════════════════════════════

print("[4/9] Normalizando variables (z-score)...")

dim1_z = {var: zscore(vals) for var, vals in dim1_matrix.items()}
dim2_z = {var: zscore(vals) for var, vals in dim2_matrix.items()}

n_obs = len(localidades)
var_names_d1 = list(DIM1_VARS.keys())
var_names_d2 = list(DIM2_VARS.keys())

# ═══════════════════════════════════════════════════════════════
# PASO 4: TESTS DE ADECUACION
# ═══════════════════════════════════════════════════════════════

print("[5/9] Tests de adecuacion muestral...")

def run_adequacy_tests(z_data, var_names, dim_label):
    cols = [z_data[v] for v in var_names]
    R = corr_matrix(cols)
    kmo = kmo_test(R)
    chi2, pval = bartlett_test(R, n_obs)

    kmo_label = (
        "Excelente (>0.9)" if kmo > 0.9 else
        "Bueno (>0.8)" if kmo > 0.8 else
        "Aceptable (>0.7)" if kmo > 0.7 else
        "Mediocre (>0.6)" if kmo > 0.6 else
        "Pobre (>0.5)" if kmo > 0.5 else
        "Inaceptable (<0.5)"
    )

    print(f"\n   {dim_label}:")
    print(f"   KMO = {kmo:.4f} — {kmo_label}")
    print(f"   Bartlett Chi2 = {chi2:.2f}, p-value = {pval:.6f}")
    if pval < 0.05:
        print(f"   >> Bartlett significativo (p<0.05): las variables estan correlacionadas [OK]")
    else:
        print(f"   >> Bartlett NO significativo: las variables podrian ser independientes [X]")

    return R, kmo, chi2, pval

R1, kmo1, chi2_1, pval1 = run_adequacy_tests(dim1_z, var_names_d1, "Dimension 1: Criminalidad Objetiva")
R2, kmo2, chi2_2, pval2 = run_adequacy_tests(dim2_z, var_names_d2, "Dimension 2: Percepcion Subjetiva")

# ═══════════════════════════════════════════════════════════════
# PASO 5: PCA POR DIMENSION
# ═══════════════════════════════════════════════════════════════

print("\n[6/9] Analisis de Componentes Principales...")

def run_pca(z_data, var_names, dim_label):
    p = len(var_names)
    n = len(z_data[var_names[0]])

    # Matriz de covarianza (sobre datos estandarizados = correlacion)
    cols = [z_data[v] for v in var_names]
    cov = corr_matrix(cols)

    eigenvalues, eigenvectors = power_iteration_pca(cov, n_components=p)

    total_var = sum(eigenvalues)

    print(f"\n   {dim_label}:")
    print(f"   {'PC':>4} {'Eigenvalue':>12} {'% Varianza':>12} {'% Acumulada':>12}")
    print(f"   {'-'*44}")

    cum_var = 0
    n_retain = 0
    for i, ev in enumerate(eigenvalues):
        pct = ev / total_var * 100
        cum_var += pct
        marker = " <--" if ev >= 1.0 else ""
        print(f"   PC{i+1:>2} {ev:>12.4f} {pct:>11.1f}% {cum_var:>11.1f}%{marker}")
        if ev >= 1.0:
            n_retain = i + 1

    if n_retain == 0:
        n_retain = 1

    print(f"\n   Componentes retenidos (eigenvalue >= 1): {n_retain}")
    print(f"   Varianza explicada retenida: {sum(eigenvalues[:n_retain])/total_var*100:.1f}%")

    # Loadings del PC1
    print(f"\n   Loadings PC1:")
    loadings_pc1 = eigenvectors[0]
    for i, var in enumerate(var_names):
        bar = "#" * int(abs(loadings_pc1[i]) * 20)
        sign = "+" if loadings_pc1[i] >= 0 else "-"
        print(f"   {var:>25s}  {sign}{abs(loadings_pc1[i]):.4f}  {bar}")

    # Pesos derivados de PCA (proporcion de varianza explicada por cada componente
    # ponderada por los loadings al cuadrado)
    weights = [0.0] * p
    for comp in range(n_retain):
        comp_weight = eigenvalues[comp] / total_var
        for i in range(p):
            weights[i] += comp_weight * eigenvectors[comp][i]**2

    # Normalizar pesos a suma = 1
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    print(f"\n   Pesos PCA derivados (normalizados):")
    for i, var in enumerate(var_names):
        print(f"   {var:>25s}  {weights[i]:.4f}  ({weights[i]*100:.1f}%)")

    # Calcular scores
    scores = []
    for obs in range(n):
        s = sum(weights[i] * z_data[var_names[i]][obs] for i in range(p))
        scores.append(s)

    return {
        'eigenvalues': eigenvalues,
        'eigenvectors': eigenvectors,
        'weights': weights,
        'scores': scores,
        'n_retained': n_retain,
        'var_explained': sum(eigenvalues[:n_retain]) / total_var * 100,
    }

pca1 = run_pca(dim1_z, var_names_d1, "Dimension 1: Criminalidad Objetiva")
pca2 = run_pca(dim2_z, var_names_d2, "Dimension 2: Percepcion Subjetiva")


# ═══════════════════════════════════════════════════════════════
# PASO 6: PCA GLOBAL — Combinar dimensiones
# ═══════════════════════════════════════════════════════════════

print("\n[7/9] PCA Global — Combinacion de dimensiones...")

# Estandarizar los scores de cada dimension
scores1_z = zscore(pca1['scores'])
scores2_z = zscore(pca2['scores'])

# Correlacion entre dimensiones
r_dims = sum(scores1_z[i]*scores2_z[i] for i in range(n_obs)) / (n_obs - 1)
print(f"\n   Correlacion entre Dim.Objetiva y Dim.Subjetiva: r = {r_dims:.4f}")

if abs(r_dims) > 0.7:
    print(f"   >> Correlacion FUERTE: ambas dimensiones miden constructos relacionados")
elif abs(r_dims) > 0.4:
    print(f"   >> Correlacion MODERADA: las dimensiones aportan informacion complementaria")
else:
    print(f"   >> Correlacion DEBIL: las dimensiones son relativamente independientes")

# PCA sobre las dos dimensiones
cov_global = [
    [1.0, r_dims],
    [r_dims, 1.0]
]
ev_global, evec_global = power_iteration_pca(cov_global, 2)

# Pesos globales de cada dimension
w_obj_raw = evec_global[0][0]**2 * ev_global[0]
w_sub_raw = evec_global[0][1]**2 * ev_global[0]
total_gw = w_obj_raw + w_sub_raw
w_obj = w_obj_raw / total_gw
w_sub = w_sub_raw / total_gw

print(f"\n   Peso Dimension Objetiva:  {w_obj:.4f} ({w_obj*100:.1f}%)")
print(f"   Peso Dimension Subjetiva: {w_sub:.4f} ({w_sub*100:.1f}%)")

# Score compuesto final
raw_scores = [w_obj * scores1_z[i] + w_sub * scores2_z[i] for i in range(n_obs)]

# Escalar a 0-5 (invertido: mayor score = MAS inseguro)
final_scores = minmax(raw_scores, 0, 5)

print(f"\n   Ranking ICSU (Indicador Compuesto de Seguridad Urbana):")
print(f"   {'Pos':>3} {'Localidad':<25} {'ICSU':>6} {'DimObj':>8} {'DimSub':>8}")
print(f"   {'-'*54}")

ranking = sorted(range(n_obs), key=lambda i: final_scores[i], reverse=True)
for rank, idx in enumerate(ranking, 1):
    print(f"   {rank:>3}. {localidades[idx]:<25} {final_scores[idx]:>5.2f}  "
          f"{pca1['scores'][idx]:>+7.3f}  {pca2['scores'][idx]:>+7.3f}")


# ═══════════════════════════════════════════════════════════════
# PASO 7: ANALISIS DE SENSIBILIDAD (Monte Carlo)
# ═══════════════════════════════════════════════════════════════

print("\n[8/9] Analisis de sensibilidad (Monte Carlo, 1000 iteraciones)...")

import random
random.seed(2024)

N_MC = 1000
rank_distributions = {loc: [] for loc in localidades}

for mc in range(N_MC):
    # Perturbar pesos ±30%
    perturbed_w_obj = w_obj * (1 + random.uniform(-0.3, 0.3))
    perturbed_w_sub = w_sub * (1 + random.uniform(-0.3, 0.3))
    total_pw = perturbed_w_obj + perturbed_w_sub
    perturbed_w_obj /= total_pw
    perturbed_w_sub /= total_pw

    mc_scores = [perturbed_w_obj * scores1_z[i] + perturbed_w_sub * scores2_z[i]
                 for i in range(n_obs)]
    mc_final = minmax(mc_scores, 0, 5)
    mc_ranking = sorted(range(n_obs), key=lambda i: mc_final[i], reverse=True)

    for rank, idx in enumerate(mc_ranking, 1):
        rank_distributions[localidades[idx]].append(rank)

print(f"\n   {'Localidad':<25} {'Rank medio':>10} {'Rank med.':>10} {'Min':>5} {'Max':>5} {'Estable':>8}")
print(f"   {'-'*68}")

stability_results = []
for idx in ranking:
    loc = localidades[idx]
    ranks = rank_distributions[loc]
    avg_rank = mean(ranks)
    med_rank = sorted(ranks)[len(ranks)//2]
    min_rank = min(ranks)
    max_rank = max(ranks)
    spread = max_rank - min_rank
    stable = "SI" if spread <= 4 else "PARCIAL" if spread <= 7 else "NO"
    stability_results.append({
        'localidad': loc,
        'rank_medio': avg_rank,
        'rank_mediana': med_rank,
        'rank_min': min_rank,
        'rank_max': max_rank,
        'estable': stable
    })
    print(f"   {loc:<25} {avg_rank:>9.1f} {med_rank:>9.0f} {min_rank:>5} {max_rank:>5} {stable:>8}")


# ═══════════════════════════════════════════════════════════════
# PASO 8: CLUSTERING POST-HOC (K-means sobre 2 dimensiones)
# ═══════════════════════════════════════════════════════════════

print("\n[9/9] Clustering post-hoc (K-means, k=4)...")

cluster_data = [[scores1_z[i], scores2_z[i]] for i in range(n_obs)]
labels, centroids = kmeans(cluster_data, k=4)

# Etiquetar clusters segun sus centroides
cluster_profiles = {}
for c in range(4):
    members = [i for i in range(n_obs) if labels[i] == c]
    if not members:
        continue
    avg_obj = mean([scores1_z[i] for i in members])
    avg_sub = mean([scores2_z[i] for i in members])

    obj_label = "Alta criminalidad" if avg_obj > 0 else "Baja criminalidad"
    sub_label = "Alta percepcion inseg." if avg_sub > 0 else "Baja percepcion inseg."

    cluster_profiles[c] = {
        'label': f"{obj_label} + {sub_label}",
        'avg_obj': avg_obj,
        'avg_sub': avg_sub,
        'members': [localidades[i] for i in members],
        'n': len(members)
    }

print(f"\n   Perfiles de seguridad:")
for c in sorted(cluster_profiles.keys()):
    cp = cluster_profiles[c]
    print(f"\n   Cluster {c+1}: {cp['label']} (n={cp['n']})")
    print(f"   Score obj. medio: {cp['avg_obj']:+.3f}, Score subj. medio: {cp['avg_sub']:+.3f}")
    print(f"   Localidades: {', '.join(cp['members'])}")


# ═══════════════════════════════════════════════════════════════
# EXPORTAR RESULTADOS
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 80)
print("EXPORTANDO RESULTADOS")
print("=" * 80)

output = {
    'metadata': {
        'nombre': 'Indicador Compuesto de Seguridad Urbana (ICSU)',
        'metodologia': 'PCA — OECD/JRC Handbook (2008)',
        'fuentes': [
            'DAILoc.geojson — Criminalidad 2024 (Secretaria de Seguridad)',
            'EPV 2024 — Encuesta Percepcion y Victimizacion (CCB, 19,354 encuestas Bogota)'
        ],
        'n_localidades': n_obs,
        'variables_dim1_objetiva': list(DIM1_VARS.values()),
        'variables_dim2_subjetiva': list(DIM2_VARS.values()),
        'escala': '0-5 (0=mas seguro, 5=mas inseguro)',
    },
    'tests_adecuacion': {
        'dim1_kmo': round(kmo1, 4),
        'dim1_bartlett_chi2': round(chi2_1, 2),
        'dim1_bartlett_pvalue': round(pval1, 6),
        'dim2_kmo': round(kmo2, 4),
        'dim2_bartlett_chi2': round(chi2_2, 2),
        'dim2_bartlett_pvalue': round(pval2, 6),
        'correlacion_dimensiones': round(r_dims, 4),
    },
    'pca_resultados': {
        'dim1_varianza_explicada_pct': round(pca1['var_explained'], 1),
        'dim1_componentes_retenidos': pca1['n_retained'],
        'dim1_pesos': {var_names_d1[i]: round(pca1['weights'][i], 4) for i in range(len(var_names_d1))},
        'dim2_varianza_explicada_pct': round(pca2['var_explained'], 1),
        'dim2_componentes_retenidos': pca2['n_retained'],
        'dim2_pesos': {var_names_d2[i]: round(pca2['weights'][i], 4) for i in range(len(var_names_d2))},
        'peso_global_dim_objetiva': round(w_obj, 4),
        'peso_global_dim_subjetiva': round(w_sub, 4),
    },
    'eigenvalues': {
        'dim1': [round(e, 4) for e in pca1['eigenvalues']],
        'dim2': [round(e, 4) for e in pca2['eigenvalues']],
    },
    'ranking': [],
    'sensibilidad': stability_results,
    'clusters': [],
}

for rank, idx in enumerate(ranking, 1):
    loc = localidades[idx]
    epv = epv_by_loc[loc]
    obj = obj_data[loc]

    output['ranking'].append({
        'posicion': rank,
        'localidad_id': epv['localidad_id'],
        'localidad': loc,
        'icsu_score': round(final_scores[idx], 3),
        'dim_objetiva_z': round(pca1['scores'][idx], 4),
        'dim_subjetiva_z': round(pca2['scores'][idx], 4),
        'cluster': int(labels[idx]) + 1,
        'datos_objetivos': {
            'homicidios': obj['homicidios'],
            'hurto_personas': obj['hurto_personas'],
            'delitos_sexuales': obj['delitos_sexuales'],
            'lesiones_personales': obj['lesiones_personales'],
        },
        'datos_subjetivos': {
            'pct_barrio_inseguro': epv['pct_barrio_inseguro'],
            'pct_victima_delito': epv['pct_victima_delito'],
            'pct_testigo_delito': epv['pct_testigo_delito'],
            'score_policia': epv['score_policia_1a5'],
        },
        'ipi_anterior': epv['ipi_percepcion_inseguridad'],
    })

for c in sorted(cluster_profiles.keys()):
    cp = cluster_profiles[c]
    output['clusters'].append({
        'cluster': c + 1,
        'perfil': cp['label'],
        'score_obj_medio': round(cp['avg_obj'], 4),
        'score_sub_medio': round(cp['avg_sub'], 4),
        'localidades': cp['members'],
    })

# Guardar
out_path = os.path.join(script_dir, 'icsu_indicador_compuesto.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n[OK] Guardado: icsu_indicador_compuesto.json")

# ═══════════════════════════════════════════════════════════════
# COMPARACION: ICSU (PCA) vs IPI anterior (pesos fijos)
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 80)
print("COMPARACION: ICSU (PCA) vs IPI (pesos fijos)")
print("=" * 80)

print(f"\n{'Localidad':<25} {'ICSU(PCA)':>10} {'Rank PCA':>9} {'IPI(fijo)':>10} {'Rank IPI':>9} {'Cambio':>7}")
print("-" * 75)

# IPI ranking
ipi_scores = [(i, epv_by_loc[localidades[i]]['ipi_percepcion_inseguridad']) for i in range(n_obs)]
ipi_ranking_sorted = sorted(ipi_scores, key=lambda x: x[1], reverse=True)
ipi_rank_map = {idx: rank+1 for rank, (idx, _) in enumerate(ipi_ranking_sorted)}

for rank, idx in enumerate(ranking, 1):
    loc = localidades[idx]
    ipi = epv_by_loc[loc]['ipi_percepcion_inseguridad']
    ipi_rank = ipi_rank_map[idx]
    cambio = ipi_rank - rank
    arrow = f"+{cambio}" if cambio > 0 else f"-{-cambio}" if cambio < 0 else "="
    print(f"{loc:<25} {final_scores[idx]:>9.2f} {rank:>9} {ipi:>9.2f} {ipi_rank:>9} {arrow:>7}")

# Correlacion de Spearman entre rankings
pca_ranks = [0] * n_obs
ipi_ranks = [0] * n_obs
for rank, idx in enumerate(ranking, 1):
    pca_ranks[idx] = rank
    ipi_ranks[idx] = ipi_rank_map[idx]

d2_sum = sum((pca_ranks[i] - ipi_ranks[i])**2 for i in range(n_obs))
spearman = 1 - 6 * d2_sum / (n_obs * (n_obs**2 - 1))
print(f"\nCorrelacion de Spearman (ranking PCA vs IPI): rho = {spearman:.4f}")
if abs(spearman) > 0.8:
    print(">> Correlacion FUERTE: ambos metodos producen rankings similares")
elif abs(spearman) > 0.5:
    print(">> Correlacion MODERADA: hay diferencias significativas entre metodos")
else:
    print(">> Correlacion DEBIL: los metodos producen rankings muy diferentes")

print("\n=== ANALISIS COMPLETO ===")
