"""
Analisis completo EPV 2024 — Encuesta de Percepcion y Victimizacion
Camara de Comercio de Bogota — 26,064 encuestas (19,354 Bogota)

Cruces:
  1. Percepcion x Localidad x Estrato
  2. Percepcion x Victimizacion (quienes fueron victimas vs no)
  3. Percepcion x Genero x Edad
  4. Victimizacion x Localidad x Estrato
  5. Espacios publicos x Localidad
  6. Tendencia inseguridad x Localidad x Estrato
  7. Policia x Localidad
  8. Convivencia x Localidad
  9. Indice compuesto de percepcion por localidad
  10. Export JSON para carga en PostgreSQL
"""
import openpyxl
import json
import math
from collections import defaultdict, Counter

# ── Cargar datos ──
print("[1/10] Cargando Base EPV 2024...")
wb = openpyxl.load_workbook('Base EPV 2024 anonimizada.xlsx', read_only=True)
ws = wb['NUMERICO']

headers = None
data = []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0:
        headers = list(row)
        continue
    data.append(dict(zip(headers, row)))

wb.close()
print(f"   Total registros: {len(data)}")

# Filtrar Bogota
bogota = [r for r in data if r.get('MUNICIPIO') == 11001]
print(f"   Registros Bogota: {len(bogota)}")

LOC_MAP = {
    1: 'Usaquen', 2: 'Chapinero', 3: 'Santa Fe', 4: 'San Cristobal',
    5: 'Usme', 6: 'Tunjuelito', 7: 'Bosa', 8: 'Kennedy',
    9: 'Fontibon', 10: 'Engativa', 11: 'Suba', 12: 'Barrios Unidos',
    13: 'Teusaquillo', 14: 'Los Martires', 15: 'Antonio Narino',
    16: 'Puente Aranda', 17: 'La Candelaria', 18: 'Rafael Uribe Uribe',
    19: 'Ciudad Bolivar'
}

EDAD_MAP = {
    1: '18-24', 2: '25-35', 3: '36-45', 4: '46-55',
    5: '56-65', 6: '66-75', 7: '75+'
}

DELITOS = {
    'P2041': 'Hurto a personas', 'P2042': 'Hurto a residencias',
    'P2043': 'Lesiones personales', 'P2044': 'Hurto vehiculos',
    'P2046': 'Violencia intrafamiliar', 'P20413': 'Vandalismo',
    'P20419': 'Violencia sexual', 'P2048': 'Robo bicicleta',
    'P20420': 'Delitos ciberneticos', 'P20422': 'Extorsion',
    'P20423': 'Hurto comercial', 'P20426': 'Violencia contra mujer',
    'P20429': 'Amenazas',
}

ESPACIOS = {
    'P1101': 'Calles', 'P1102': 'Paraderos', 'P1103': 'Parques',
    'P1104': 'Potreros', 'P1105': 'Puentes peatonales',
    'P1106': 'Puentes vehiculares', 'P1107': 'Semaforos',
    'P1108': 'Ciclovias', 'P1109': 'Ciclorutas',
}

RAZONES_INSEG = {
    'P1121': 'Presencia habitantes de calle', 'P1122': 'Consumo drogas',
    'P1123': 'Falta iluminacion', 'P1124': 'Falta vigilancia policial',
    'P1125': 'Presencia pandillas', 'P1126': 'Venta drogas',
    'P1127': 'Falta camaras', 'P1128': 'Espacios abandonados',
    'P1129': 'Falta cultura ciudadana', 'P11210': 'Inmigracion',
    'P11211': 'Falta oportunidades', 'P11212': 'Otro',
}


def safe_val(r, col, valid_range=None):
    """Extrae valor numerico seguro."""
    v = r.get(col)
    if v is None or not isinstance(v, (int, float)):
        return None
    if valid_range and (v < valid_range[0] or v > valid_range[1]):
        return None
    return v


def pct(num, den):
    return round(num / den * 100, 1) if den > 0 else 0


def avg(vals):
    return round(sum(vals) / len(vals), 2) if vals else 0


# ══════════════════════════════════════════════════════════════
# CRUCE 1: Percepcion x Localidad x Estrato
# ══════════════════════════════════════════════════════════════
print("\n[2/10] Cruce: Percepcion x Localidad x Estrato...")

cruce_loc_est = defaultdict(lambda: {'n': 0, 'barrio_ins': 0, 'bogota_ins': 0,
                                       'score_barrio': [], 'score_bogota': []})

for r in bogota:
    loc = r.get('LOCALIDAD')
    est = safe_val(r, 'ESTRATO', (1, 6))
    if loc not in LOC_MAP or est is None:
        continue
    key = (loc, int(est))
    s = cruce_loc_est[key]
    s['n'] += 1
    if r.get('P102') == 2: s['barrio_ins'] += 1
    if r.get('P103') == 2: s['bogota_ins'] += 1
    v1 = safe_val(r, 'P1021', (1, 5))
    if v1: s['score_barrio'].append(v1)
    v2 = safe_val(r, 'P1031', (1, 5))
    if v2: s['score_bogota'].append(v2)

print(f"\n{'Localidad':<22} {'Est':>3} {'N':>5} {'%BarIns':>7} {'ScBar':>5} {'%BogIns':>7} {'ScBog':>5}")
print("-" * 65)
for (loc, est), s in sorted(cruce_loc_est.items()):
    if s['n'] >= 20:
        print(f"{LOC_MAP[loc]:<22} {est:>3} {s['n']:>5} {pct(s['barrio_ins'], s['n']):>6.1f}% {avg(s['score_barrio']):>5.2f} {pct(s['bogota_ins'], s['n']):>6.1f}% {avg(s['score_bogota']):>5.2f}")


# ══════════════════════════════════════════════════════════════
# CRUCE 2: Percepcion x Victimizacion
# ══════════════════════════════════════════════════════════════
print("\n[3/10] Cruce: Percepcion x Victimizacion...")

victimas = [r for r in bogota if r.get('P203') == 1]
no_victimas = [r for r in bogota if r.get('P203') == 2]

for label, grupo in [("VICTIMAS", victimas), ("NO VICTIMAS", no_victimas)]:
    n = len(grupo)
    barrio_ins = sum(1 for r in grupo if r.get('P102') == 2)
    bogota_ins = sum(1 for r in grupo if r.get('P103') == 2)
    scores_b = [safe_val(r, 'P1021', (1, 5)) for r in grupo]
    scores_b = [v for v in scores_b if v]
    aumento = sum(1 for r in grupo if r.get('P106') == 3)
    testigo = sum(1 for r in grupo if r.get('P121') == 1)

    print(f"\n  {label} (n={n}):")
    print(f"    %Barrio inseguro:    {pct(barrio_ins, n)}%")
    print(f"    %Bogota insegura:    {pct(bogota_ins, n)}%")
    print(f"    Score barrio (1-5):  {avg(scores_b)}")
    print(f"    %Inseg. aumento:     {pct(aumento, n)}%")
    print(f"    %Testigo delito:     {pct(testigo, n)}%")


# ══════════════════════════════════════════════════════════════
# CRUCE 3: Percepcion x Genero x Rango de Edad
# ══════════════════════════════════════════════════════════════
print("\n[4/10] Cruce: Percepcion x Genero x Edad...")

cruce_gen_edad = defaultdict(lambda: {'n': 0, 'barrio_ins': 0, 'score': [], 'victima': 0})

for r in bogota:
    sexo = safe_val(r, 'SEXO', (1, 3))
    redad = safe_val(r, 'REDAD', (1, 7))
    if sexo is None or redad is None:
        continue
    key = (int(sexo), int(redad))
    s = cruce_gen_edad[key]
    s['n'] += 1
    if r.get('P102') == 2: s['barrio_ins'] += 1
    v = safe_val(r, 'P1021', (1, 5))
    if v: s['score'].append(v)
    if r.get('P203') == 1: s['victima'] += 1

sexo_map = {1: 'Hombre', 2: 'Mujer', 3: 'Otro'}
print(f"\n{'Genero':<10} {'Edad':<8} {'N':>5} {'%BarIns':>7} {'Score':>5} {'%Vict':>6}")
print("-" * 50)
for (sexo, redad), s in sorted(cruce_gen_edad.items()):
    if s['n'] >= 10:
        print(f"{sexo_map.get(sexo, '?'):<10} {EDAD_MAP.get(redad, '?'):<8} {s['n']:>5} {pct(s['barrio_ins'], s['n']):>6.1f}% {avg(s['score']):>5.2f} {pct(s['victima'], s['n']):>5.1f}%")


# ══════════════════════════════════════════════════════════════
# CRUCE 4: Victimizacion x Localidad x Estrato
# ══════════════════════════════════════════════════════════════
print("\n[5/10] Cruce: Victimizacion x Localidad x Estrato...")

vict_loc_est = defaultdict(lambda: {'n': 0, 'victima': 0, 'testigo': 0, 'hogar_victima': 0, 'delitos': Counter()})

for r in bogota:
    loc = r.get('LOCALIDAD')
    est = safe_val(r, 'ESTRATO', (1, 6))
    if loc not in LOC_MAP or est is None:
        continue
    key = (loc, int(est))
    s = vict_loc_est[key]
    s['n'] += 1
    if r.get('P203') == 1: s['victima'] += 1
    if r.get('P121') == 1: s['testigo'] += 1
    if r.get('P230') == 1: s['hogar_victima'] += 1
    for col, nombre in DELITOS.items():
        if r.get(col) == 1:
            s['delitos'][nombre] += 1

print(f"\n{'Localidad':<22} {'Est':>3} {'N':>5} {'%Vict':>6} {'%Test':>6} {'%Hogar':>6} {'Delito #1':<25}")
print("-" * 80)
for (loc, est), s in sorted(vict_loc_est.items()):
    if s['n'] >= 20:
        top_d = s['delitos'].most_common(1)
        top_str = f"{top_d[0][0]} ({top_d[0][1]})" if top_d else "—"
        print(f"{LOC_MAP[loc]:<22} {est:>3} {s['n']:>5} {pct(s['victima'], s['n']):>5.1f}% {pct(s['testigo'], s['n']):>5.1f}% {pct(s['hogar_victima'], s['n']):>5.1f}% {top_str:<25}")


# ══════════════════════════════════════════════════════════════
# CRUCE 5: Espacios publicos x Localidad
# ══════════════════════════════════════════════════════════════
print("\n[6/10] Cruce: Espacios publicos x Localidad...")

esp_loc = defaultdict(lambda: defaultdict(list))

for r in bogota:
    loc = r.get('LOCALIDAD')
    if loc not in LOC_MAP:
        continue
    for col, nombre in ESPACIOS.items():
        v = safe_val(r, col, (1, 5))
        if v:
            esp_loc[loc][nombre].append(v)

# TransMilenio
for r in bogota:
    loc = r.get('LOCALIDAD')
    if loc not in LOC_MAP:
        continue
    v = safe_val(r, 'P111', (1, 5))
    if v:
        esp_loc[loc]['TransMilenio'].append(v)

print(f"\n{'Localidad':<18}", end='')
espacios_nombres = list(ESPACIOS.values()) + ['TransMilenio']
for e in espacios_nombres:
    print(f" {e[:6]:>6}", end='')
print()
print("-" * (18 + 7 * len(espacios_nombres)))

for loc in sorted(LOC_MAP.keys()):
    print(f"{LOC_MAP[loc]:<18}", end='')
    for nombre in espacios_nombres:
        vals = esp_loc[loc].get(nombre, [])
        print(f" {avg(vals):>6.2f}", end='')
    print()


# ══════════════════════════════════════════════════════════════
# CRUCE 6: Razones de inseguridad x Localidad
# ══════════════════════════════════════════════════════════════
print("\n[7/10] Cruce: Razones de inseguridad x Localidad...")

razones_loc = defaultdict(lambda: {'n': 0, 'razones': Counter()})

for r in bogota:
    loc = r.get('LOCALIDAD')
    if loc not in LOC_MAP:
        continue
    razones_loc[loc]['n'] += 1
    for col, nombre in RAZONES_INSEG.items():
        if r.get(col) == 1:
            razones_loc[loc]['razones'][nombre] += 1

print(f"\n{'Localidad':<22} Top 3 razones de inseguridad")
print("-" * 80)
for loc in sorted(LOC_MAP.keys()):
    s = razones_loc[loc]
    top3 = s['razones'].most_common(3)
    top_str = " | ".join(f"{n} ({pct(c, s['n'])}%)" for n, c in top3)
    print(f"{LOC_MAP[loc]:<22} {top_str}")


# ══════════════════════════════════════════════════════════════
# CRUCE 7: Policia x Localidad
# ══════════════════════════════════════════════════════════════
print("\n[8/10] Cruce: Policia x Localidad...")

pol_loc = defaultdict(lambda: {'score_servicio': [], 'conoce_cuadrante': 0,
                                 'ha_visto_policia': 0, 'acudio_policia': 0, 'n': 0})

for r in bogota:
    loc = r.get('LOCALIDAD')
    if loc not in LOC_MAP:
        continue
    s = pol_loc[loc]
    s['n'] += 1
    v = safe_val(r, 'P4011', (1, 5))
    if v: s['score_servicio'].append(v)
    if r.get('P405') == 1: s['conoce_cuadrante'] += 1
    if r.get('P4071') == 1: s['ha_visto_policia'] += 1
    if r.get('P417') == 1: s['acudio_policia'] += 1

print(f"\n{'Localidad':<22} {'ScPol':>5} {'%Conoce':>7} {'%Visto':>7} {'%Acudio':>7}")
print("-" * 55)
for loc in sorted(LOC_MAP.keys()):
    s = pol_loc[loc]
    n = s['n']
    print(f"{LOC_MAP[loc]:<22} {avg(s['score_servicio']):>5.2f} {pct(s['conoce_cuadrante'], n):>6.1f}% {pct(s['ha_visto_policia'], n):>6.1f}% {pct(s['acudio_policia'], n):>6.1f}%")


# ══════════════════════════════════════════════════════════════
# CRUCE 8: Convivencia x Localidad
# ══════════════════════════════════════════════════════════════
print("\n[9/10] Cruce: Convivencia x Localidad...")

PROBLEMAS_CONV = {
    'P2341': 'Arrojar basuras', 'P2342': 'Ruido excesivo',
    'P2344': 'Invasion espacio publico', 'P2345': 'Consumo drogas via publica',
    'P2346': 'Riñas callejeras', 'P23411': 'Maltrato animal',
    'P23414': 'Acoso callejero', 'P23417': 'Conduccion peligrosa',
    'P23418': 'Ventas ambulantes', 'P23419': 'Indigencia',
}

conv_loc = defaultdict(lambda: {'n': 0, 'afecto_conv': 0, 'problemas': Counter()})

for r in bogota:
    loc = r.get('LOCALIDAD')
    if loc not in LOC_MAP:
        continue
    s = conv_loc[loc]
    s['n'] += 1
    if r.get('P233') == 1: s['afecto_conv'] += 1
    for col, nombre in PROBLEMAS_CONV.items():
        if r.get(col) == 1:
            s['problemas'][nombre] += 1

print(f"\n{'Localidad':<22} {'%Afectado':>9} Top problema")
print("-" * 65)
for loc in sorted(LOC_MAP.keys()):
    s = conv_loc[loc]
    top1 = s['problemas'].most_common(1)
    top_str = f"{top1[0][0]} ({pct(top1[0][1], s['n'])}%)" if top1 else "—"
    print(f"{LOC_MAP[loc]:<22} {pct(s['afecto_conv'], s['n']):>8.1f}% {top_str}")


# ══════════════════════════════════════════════════════════════
# CRUCE 9: Estrato global
# ══════════════════════════════════════════════════════════════
print("\n[9b] Cruce global: Estrato...")

est_stats = defaultdict(lambda: {'n': 0, 'barrio_ins': 0, 'score': [],
                                   'victima': 0, 'testigo': 0, 'aumento': 0,
                                   'pol_score': []})
for r in bogota:
    est = safe_val(r, 'ESTRATO', (1, 6))
    if est is None:
        continue
    s = est_stats[int(est)]
    s['n'] += 1
    if r.get('P102') == 2: s['barrio_ins'] += 1
    v = safe_val(r, 'P1021', (1, 5))
    if v: s['score'].append(v)
    if r.get('P203') == 1: s['victima'] += 1
    if r.get('P121') == 1: s['testigo'] += 1
    if r.get('P106') == 3: s['aumento'] += 1
    vp = safe_val(r, 'P4011', (1, 5))
    if vp: s['pol_score'].append(vp)

print(f"\n{'Estrato':>7} {'N':>6} {'%BarIns':>7} {'Score':>5} {'%Vict':>6} {'%Test':>6} {'%Aum':>6} {'ScPol':>5}")
print("-" * 55)
for est in range(1, 7):
    s = est_stats[est]
    if s['n'] > 0:
        print(f"      {est} {s['n']:>6} {pct(s['barrio_ins'], s['n']):>6.1f}% {avg(s['score']):>5.2f} {pct(s['victima'], s['n']):>5.1f}% {pct(s['testigo'], s['n']):>5.1f}% {pct(s['aumento'], s['n']):>5.1f}% {avg(s['pol_score']):>5.2f}")


# ══════════════════════════════════════════════════════════════
# 10: Indice compuesto + Export JSON
# ══════════════════════════════════════════════════════════════
print("\n[10/10] Calculando indice compuesto de percepcion...")

# Indice de Percepcion de Inseguridad (IPI) por localidad
# Componentes (todos normalizados 0-1, donde 1 = mas inseguro):
#   - pct_barrio_inseguro (30%)
#   - score_barrio invertido: (5-score)/4 (25%)
#   - pct_victimizacion (20%)
#   - pct_inseg_aumento (15%)
#   - pct_testigo (10%)

localidad_final = []

for loc in sorted(LOC_MAP.keys()):
    loc_rows = [r for r in bogota if r.get('LOCALIDAD') == loc]
    n = len(loc_rows)
    if n == 0:
        continue

    # Metricas base
    barrio_ins = sum(1 for r in loc_rows if r.get('P102') == 2)
    bogota_ins = sum(1 for r in loc_rows if r.get('P103') == 2)
    scores_b = [safe_val(r, 'P1021', (1, 5)) for r in loc_rows]
    scores_b = [v for v in scores_b if v]
    scores_bog = [safe_val(r, 'P1031', (1, 5)) for r in loc_rows]
    scores_bog = [v for v in scores_bog if v]
    victima = sum(1 for r in loc_rows if r.get('P203') == 1)
    testigo = sum(1 for r in loc_rows if r.get('P121') == 1)
    hogar_vict = sum(1 for r in loc_rows if r.get('P230') == 1)
    aumento = sum(1 for r in loc_rows if r.get('P106') == 3)
    igual = sum(1 for r in loc_rows if r.get('P106') == 2)
    disminuyo = sum(1 for r in loc_rows if r.get('P106') == 1)
    convivencia = sum(1 for r in loc_rows if r.get('P233') == 1)

    # Policia
    pol_scores = [safe_val(r, 'P4011', (1, 5)) for r in loc_rows]
    pol_scores = [v for v in pol_scores if v]

    # Espacios publicos promedio
    esp_scores = {}
    for col, nombre in ESPACIOS.items():
        vals = [safe_val(r, col, (1, 5)) for r in loc_rows]
        vals = [v for v in vals if v]
        esp_scores[nombre] = avg(vals)

    # TransMilenio
    tm_vals = [safe_val(r, 'P111', (1, 5)) for r in loc_rows]
    tm_vals = [v for v in tm_vals if v]

    # Delitos
    delitos_count = {}
    for col, nombre in DELITOS.items():
        cnt = sum(1 for r in loc_rows if r.get(col) == 1)
        if cnt > 0:
            delitos_count[nombre] = cnt

    # Razones de inseguridad
    razones_count = {}
    for col, nombre in RAZONES_INSEG.items():
        cnt = sum(1 for r in loc_rows if r.get(col) == 1)
        if cnt > 0:
            razones_count[nombre] = cnt

    # Estrato promedio
    estratos = [safe_val(r, 'ESTRATO', (1, 6)) for r in loc_rows]
    estratos = [v for v in estratos if v]

    # Por genero
    hombres = [r for r in loc_rows if r.get('SEXO') == 1]
    mujeres = [r for r in loc_rows if r.get('SEXO') == 2]

    # Indice de Percepcion de Inseguridad (IPI) 0-5
    pct_bi = barrio_ins / n  # 0-1
    score_inv = (5 - avg(scores_b)) / 4 if scores_b else 0.5  # 0-1
    pct_v = victima / n  # 0-1, normalizar a max ~0.25
    pct_a = aumento / n  # 0-1
    pct_t = testigo / n  # 0-1

    ipi_raw = (pct_bi * 0.30 + score_inv * 0.25 + min(pct_v * 4, 1) * 0.20 +
               pct_a * 0.15 + min(pct_t * 2, 1) * 0.10)
    ipi = round(ipi_raw * 5, 2)  # Escala 0-5

    entry = {
        'localidad_id': loc,
        'localidad': LOC_MAP[loc],
        'encuestas': n,
        'estrato_promedio': avg(estratos),

        # Percepcion
        'pct_barrio_inseguro': pct(barrio_ins, n),
        'pct_bogota_insegura': pct(bogota_ins, n),
        'score_barrio_1a5': avg(scores_b),
        'score_bogota_1a5': avg(scores_bog),

        # Tendencia
        'pct_inseg_aumento': pct(aumento, n),
        'pct_inseg_igual': pct(igual, n),
        'pct_inseg_disminuyo': pct(disminuyo, n),

        # Victimizacion
        'pct_victima_delito': pct(victima, n),
        'pct_testigo_delito': pct(testigo, n),
        'pct_hogar_victima': pct(hogar_vict, n),
        'tasa_victimizacion_x1000': round(victima / n * 1000, 1),

        # Convivencia
        'pct_afecto_convivencia': pct(convivencia, n),

        # Policia
        'score_policia_1a5': avg(pol_scores),

        # Espacios publicos (score 1-5)
        'espacios_publicos': esp_scores,
        'score_transmilenio': avg(tm_vals),

        # Delitos (conteo)
        'delitos_top5': dict(Counter(delitos_count).most_common(5)),

        # Razones top 5
        'razones_inseg_top5': dict(Counter(razones_count).most_common(5)),

        # Por genero
        'pct_barrio_ins_hombres': pct(
            sum(1 for r in hombres if r.get('P102') == 2), len(hombres)
        ) if hombres else 0,
        'pct_barrio_ins_mujeres': pct(
            sum(1 for r in mujeres if r.get('P102') == 2), len(mujeres)
        ) if mujeres else 0,
        'pct_victima_hombres': pct(
            sum(1 for r in hombres if r.get('P203') == 1), len(hombres)
        ) if hombres else 0,
        'pct_victima_mujeres': pct(
            sum(1 for r in mujeres if r.get('P203') == 1), len(mujeres)
        ) if mujeres else 0,

        # Indice compuesto
        'ipi_percepcion_inseguridad': ipi,
    }
    localidad_final.append(entry)

# Ordenar por IPI
localidad_final.sort(key=lambda x: x['ipi_percepcion_inseguridad'], reverse=True)

print(f"\n{'Localidad':<22} {'IPI':>5} {'%BarIns':>7} {'Score':>5} {'%Vict':>6} {'%Aum':>6} {'ScPol':>5}")
print("-" * 60)
for e in localidad_final:
    print(f"{e['localidad']:<22} {e['ipi_percepcion_inseguridad']:>5.2f} {e['pct_barrio_inseguro']:>6.1f}% {e['score_barrio_1a5']:>5.2f} {e['pct_victima_delito']:>5.1f}% {e['pct_inseg_aumento']:>5.1f}% {e['score_policia_1a5']:>5.2f}")

# Guardar JSON completo
with open('epv_2024_analisis_completo.json', 'w', encoding='utf-8') as f:
    json.dump(localidad_final, f, ensure_ascii=False, indent=2)
print(f"\n[OK] Guardado: epv_2024_analisis_completo.json")

# Guardar resumen por estrato
est_export = []
for est in range(1, 7):
    s = est_stats[est]
    if s['n'] > 0:
        est_export.append({
            'estrato': est,
            'encuestas': s['n'],
            'pct_barrio_inseguro': pct(s['barrio_ins'], s['n']),
            'score_barrio_1a5': avg(s['score']),
            'pct_victima': pct(s['victima'], s['n']),
            'pct_testigo': pct(s['testigo'], s['n']),
            'pct_inseg_aumento': pct(s['aumento'], s['n']),
            'score_policia': avg(s['pol_score']),
        })

with open('epv_2024_por_estrato.json', 'w', encoding='utf-8') as f:
    json.dump(est_export, f, ensure_ascii=False, indent=2)
print("[OK] Guardado: epv_2024_por_estrato.json")

print("\n=== ANALISIS COMPLETO ===")
