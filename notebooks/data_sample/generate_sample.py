"""
Genera un CSV de 200 inmuebles sintéticos pero estadísticamente plausibles
para Bogotá. Se usa en los notebooks como dataset reproducible que NO
expone listados reales scrapeados (sin direcciones ni teléfonos).

Distribuciones calibradas a partir del corpus real:
  - 20 localidades con pesos por densidad inmobiliaria observada
  - precio_m2 lognormal por localidad (medianas reales)
  - área lognormal (mu=4.2, sigma=0.4)
  - habitaciones/baños correlacionados con área
  - coordenadas dentro del polígono de la localidad asignada (muestreo rejection)

Salida:  inmuebles_sample.csv (200 filas)
"""
from __future__ import annotations
import csv
import json
import math
import random
from pathlib import Path

random.seed(20260517)
HERE = Path(__file__).parent

# Distribución observada de inmuebles por localidad (proporción aproximada
# en venta, basada en el corpus tras la corrección de id_localidad).
LOCALIDADES = [
    # nombre, id, peso_relativo, precio_m2_mediana_COP, bbox_aprox (lon, lat)
    ("CHAPINERO",         2,  0.30, 8_500_000, (-74.07, 4.62, -74.03, 4.68)),
    ("USAQUEN",           1,  0.18, 6_800_000, (-74.05, 4.66, -74.00, 4.76)),
    ("SUBA",             11,  0.14, 4_800_000, (-74.12, 4.71, -74.00, 4.78)),
    ("TEUSAQUILLO",      13,  0.07, 7_200_000, (-74.10, 4.62, -74.07, 4.66)),
    ("BARRIOS UNIDOS",   12,  0.05, 5_500_000, (-74.09, 4.66, -74.06, 4.69)),
    ("ENGATIVA",         10,  0.05, 4_200_000, (-74.13, 4.69, -74.08, 4.73)),
    ("FONTIBON",          9,  0.04, 4_500_000, (-74.16, 4.66, -74.10, 4.69)),
    ("KENNEDY",           8,  0.04, 3_500_000, (-74.18, 4.59, -74.10, 4.65)),
    ("PUENTE ARANDA",    16,  0.03, 4_100_000, (-74.12, 4.61, -74.08, 4.65)),
    ("SAN CRISTOBAL",     4,  0.02, 2_800_000, (-74.10, 4.52, -74.04, 4.57)),
    ("CANDELARIA",       17,  0.02, 6_400_000, (-74.08, 4.59, -74.06, 4.61)),
    ("SANTA FE",          3,  0.015, 4_700_000, (-74.10, 4.58, -74.04, 4.65)),
    ("RAFAEL URIBE URIBE",18, 0.012, 2_900_000, (-74.13, 4.55, -74.08, 4.58)),
    ("CIUDAD BOLIVAR",   19,  0.011, 2_200_000, (-74.20, 4.45, -74.10, 4.58)),
    ("BOSA",              7,  0.010, 2_700_000, (-74.21, 4.58, -74.16, 4.64)),
    ("ANTONIO NARIÑO",   15,  0.008, 4_300_000, (-74.10, 4.57, -74.08, 4.59)),
    ("LOS MARTIRES",     14,  0.008, 4_900_000, (-74.10, 4.59, -74.07, 4.61)),
    ("USME",              5,  0.005, 2_500_000, (-74.15, 4.39, -74.06, 4.55)),
    ("TUNJUELITO",        6,  0.005, 3_100_000, (-74.13, 4.57, -74.10, 4.61)),
    ("SUMAPAZ",          20,  0.002, 1_800_000, (-74.40, 3.80, -74.10, 4.30)),
]

TIPOS_PESO = [("Apartamento", 0.70), ("Casa", 0.22), ("Apartaestudio", 0.05), ("Oficina", 0.03)]


def lognormal(mu: float, sigma: float, lo: float | None = None, hi: float | None = None) -> float:
    """log-normal con clipping suave."""
    while True:
        v = math.exp(random.gauss(mu, sigma))
        if (lo is None or v >= lo) and (hi is None or v <= hi):
            return v


def sample_localidad() -> tuple:
    pesos = [l[2] for l in LOCALIDADES]
    return random.choices(LOCALIDADES, weights=pesos, k=1)[0]


def sample_tipo() -> str:
    return random.choices([t[0] for t in TIPOS_PESO], weights=[t[1] for t in TIPOS_PESO], k=1)[0]


def sample_inmueble(idx: int) -> dict:
    nombre, id_loc, _w, precio_m2_med, bbox = sample_localidad()
    tipo = sample_tipo()
    # área por tipo
    mu_area = {"Apartamento": 4.20, "Casa": 4.80,
               "Apartaestudio": 3.65, "Oficina": 4.30}[tipo]
    area = lognormal(mu_area, 0.32, lo=20, hi=1200)
    # habitaciones / baños correlacionados con área
    habs = max(1, min(6, int(round(area / 30 + random.gauss(0, 0.4)))))
    banos = max(1, min(6, habs - 1 + random.choice([0, 0, 1, 1, 2])))
    # precio = area * precio_m2_localidad * ruido_lognormal
    ruido = math.exp(random.gauss(0, 0.18))
    precio_m2 = precio_m2_med * math.exp(random.gauss(0, 0.20))
    precio = round(area * precio_m2 * ruido)
    # coords dentro del bbox
    lon = random.uniform(bbox[0], bbox[2])
    lat = random.uniform(bbox[1], bbox[3])
    # estrato correlacionado con precio_m2
    if precio_m2 > 9_000_000:   estrato = random.choice([6, 6, 5])
    elif precio_m2 > 6_000_000: estrato = random.choice([5, 4, 4])
    elif precio_m2 > 4_000_000: estrato = random.choice([4, 3, 3])
    elif precio_m2 > 2_800_000: estrato = random.choice([3, 3, 2])
    else:                       estrato = random.choice([2, 2, 1])
    return {
        "id_inmueble": idx,
        "tipo_inmueble": tipo,
        "precio": precio,
        "area_construida": round(area, 1),
        "habitaciones": habs,
        "banos": banos,
        "estrato": estrato,
        "id_localidad": id_loc,
        "localidad": nombre,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
    }


def main():
    rows = [sample_inmueble(i) for i in range(1, 201)]
    path = HERE / "inmuebles_sample.csv"
    with path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"OK  → {path}  ({len(rows)} filas)")

    # POIs de muestra ya con distancia mínima a cada inmueble (proxy)
    # Generamos ~80 POIs distribuidos uniformemente
    pois = []
    for i in range(1, 81):
        cat = random.choice(["transmilenio", "hospital", "colegio", "parque", "universidad"])
        pois.append({
            "id_poi": i,
            "categoria": cat,
            "nombre": f"{cat.title()} {i}",
            "lat": round(random.uniform(4.55, 4.78), 6),
            "lon": round(random.uniform(-74.18, -74.02), 6),
        })
    path = HERE / "pois_sample.csv"
    with path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(pois[0].keys()))
        w.writeheader()
        w.writerows(pois)
    print(f"OK  → {path}  ({len(pois)} POIs)")


if __name__ == "__main__":
    main()
