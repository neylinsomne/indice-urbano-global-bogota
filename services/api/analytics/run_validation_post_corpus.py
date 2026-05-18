"""
Re-ejecuta validar_iurb_completo() sobre el corpus actualizado
(post-carga de colegios, universidades, parques, teatros, escenarios).

Uso (desde container api):
    docker compose exec api python /app/analytics/run_validation_post_corpus.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras

# Permite importar desde /app/analytics/ tanto si se ejecuta como script
# directo como si se importa relativo.
sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.iurb_validation import validar_iurb_completo


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "postgres"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


def fetch_data_inmuebles(conn) -> dict:
    """
    Inmuebles bogotanos (con indicadores y precio) listos para análisis OLS.
    Filtramos los registros con iurb=NULL (los que aislamos por estar fuera
    de Bogotá), área plausible y precio plausible.
    """
    query = """
    SELECT
        i.id_inmueble,
        i.id_localidad      AS id_zona,
        i.precio,
        LN(i.precio)        AS log_precio,
        i.iacc, i.iseg, i.idot, i.ihed, i.ipnu, i.iurb AS iug,
        i.area_construida, i.habitaciones, i.banos,
        COALESCE(i.estrato, 3) AS estrato
    FROM iug.inmueble i
    WHERE i.iurb IS NOT NULL
      AND i.precio BETWEEN 50000000 AND 5000000000
      AND i.area_construida BETWEEN 20 AND 1500
      AND i.iacc IS NOT NULL AND i.iseg IS NOT NULL
      AND i.idot IS NOT NULL AND i.ihed IS NOT NULL AND i.ipnu IS NOT NULL
    """
    cols = [
        "id_inmueble", "id_zona", "precio", "log_precio",
        "iacc", "iseg", "idot", "ihed", "ipnu", "iug",
        "area_construida", "habitaciones", "banos", "estrato",
    ]
    data = {c: [] for c in cols}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur:
            for c, v in zip(cols, row):
                data[c].append(float(v) if v is not None else np.nan)
    for c in cols:
        data[c] = np.array(data[c], dtype=float)
    return data


def fetch_data_zonas(conn) -> dict:
    """Promedios de los 5 subíndices a nivel de localidad bogotana."""
    query = """
    SELECT
        l.id_localidad AS id_zona,
        ROUND(AVG(i.iacc)::numeric, 4)::float AS iacc,
        ROUND(AVG(i.iseg)::numeric, 4)::float AS iseg,
        ROUND(AVG(i.idot)::numeric, 4)::float AS idot,
        ROUND(AVG(i.ihed)::numeric, 4)::float AS ihed,
        ROUND(AVG(i.ipnu)::numeric, 4)::float AS ipnu
    FROM iug.localidad l
    JOIN iug.inmueble i ON i.id_localidad = l.id_localidad
    WHERE i.iurb IS NOT NULL
    GROUP BY l.id_localidad
    HAVING COUNT(*) >= 50
    """
    cols = ["id_zona", "iacc", "iseg", "idot", "ihed", "ipnu"]
    data = {c: [] for c in cols}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur:
            for c, v in zip(cols, row):
                data[c].append(float(v) if v is not None else 0.0)
    for c in cols:
        data[c] = np.array(data[c], dtype=float)
    return data


def main() -> None:
    print("=" * 80)
    print("VALIDACIÓN DEL IUG · CORPUS POST-AMPLIACIÓN")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    print("=" * 80)

    conn = get_conn()

    print("\n[1/3] Cargando inmuebles bogotanos...")
    data_inm = fetch_data_inmuebles(conn)
    n_inm = len(data_inm["id_inmueble"])
    print(f"   N = {n_inm:,} inmuebles válidos")

    print("\n[2/3] Cargando promedios por localidad...")
    data_zon = fetch_data_zonas(conn)
    n_zon = len(data_zon["id_zona"])
    print(f"   N = {n_zon} localidades con masa crítica (>= 50 inmuebles)")

    if n_inm < 100:
        print("\n[ERROR] Muestra insuficiente; abortando")
        return

    print("\n[3/3] Ejecutando validar_iurb_completo()...")
    print("       (modelos anidados + commonality + estabilidad ranking MC)")
    res = validar_iurb_completo(data_inm, data_zon)

    print("\n" + "=" * 80)
    print("RESULTADOS")
    print("=" * 80)

    # Tabla resumen
    print("\n┌─ Tabla resumen de pruebas ─────────────────────────────")
    for fila in res.get("tabla_resumen", []):
        print(f"│  {fila['prueba']:<35} {str(fila['valor']):<10} "
              f"umbral={fila['umbral_ok']:<10} → {fila['estado']}")
    print("└─────────────────────────────────────────────────────────")

    # Veredicto global
    print(f"\nVeredicto global : {res.get('veredicto_global')}")
    print(f"Mensaje          : {res.get('mensaje_global')}")

    # Detalles modelos anidados
    if "modelos_anidados" in res and "error" not in res["modelos_anidados"]:
        m = res["modelos_anidados"]
        print(f"\n— Modelos anidados —")
        print(f"   R² reducido (control + IUG)        : {m.get('r2_reducido', 0):.4f}")
        print(f"   R² completo  (control + 5 subs)     : {m.get('r2_completo', 0):.4f}")
        print(f"   ΔR² (completo - reducido)           : {m.get('delta_r2', 0):+.4f}")
        print(f"   ΔAIC                                 : {m.get('delta_aic', 0):+.2f}")

    # Commonality
    if "commonality" in res and "error" not in res["commonality"]:
        c = res["commonality"]
        print(f"\n— Análisis de commonality —")
        print(f"   Varianza común (entre subindicadores): {c.get('pct_comun', 0):.1f}%")
        print(f"   Varianza única total                  : {c.get('pct_unique_total', 0):.1f}%")

    # Estabilidad ranking
    if "estabilidad_ranking" in res and "error" not in res["estabilidad_ranking"]:
        e = res["estabilidad_ranking"]
        print(f"\n— Estabilidad de ranking (MC) —")
        sp = e.get("spearman", {})
        print(f"   ρ Spearman (mediana)               : {sp.get('mediana', 0):.3f}")
        print(f"   IC 90% [p5, p95]                    : [{sp.get('p5', 0):.3f}, {sp.get('p95', 0):.3f}]")

    # Persistir JSON
    out = Path("/app/analytics/results_post_corpus.json")
    out.write_text(json.dumps(res, default=str, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Resultados crudos guardados en: {out}")

    conn.close()


if __name__ == "__main__":
    main()
