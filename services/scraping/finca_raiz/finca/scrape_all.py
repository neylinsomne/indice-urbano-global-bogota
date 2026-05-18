# scrape_all.py  –  Ejecuta cada combinación en un subproceso separado
# para liberar memoria (Playwright/Chromium) entre cada spider.
# Al finalizar, llama POST /pipeline/complete para migrar MongoDB→PG + DBSCAN + Regresión.
import os
import sys
import subprocess
import time
import requests
from itertools import product

def csv_env(key, default):
    return [s.strip() for s in os.getenv(key, default).split(",") if s.strip()]

def fmt_duration(seconds):
    """Formatea segundos a 'Xh Ym Zs' legible."""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def main():
    txs      = csv_env("TXS", "venta,arriendo")
    tipos    = csv_env("TIPOS", "apartamentos,casas,locales,lotes,bodegas,parqueadero,inmuebles,fincas")
    sectores = csv_env("SECTORES", "bogota,medellin,cali,barranquilla,cajica,chia,madrid")
    usar_previos = os.getenv("USAR_PREVIOS", "n").strip().lower()

    combos = list(product(txs, tipos, sectores))
    total = len(combos)
    ok, fail = 0, 0
    combo_times = []

    global_start = time.time()
    print(f"🚀 Iniciando scrape_all: {total} combinaciones")
    print(f"   TXS={txs}, TIPOS={tipos}, SECTORES={sectores}")
    sys.stdout.flush()

    for i, (tx, tipo, sector) in enumerate(combos, 1):
        label = f"{tx}/{tipo}/{sector}"
        print(f"\n{'='*60}")
        print(f"[{i}/{total}] {label}")
        elapsed_global = fmt_duration(time.time() - global_start)
        print(f"   Progreso: {ok} OK, {fail} fallidos | Tiempo total: {elapsed_global}")
        print(f"{'='*60}")
        sys.stdout.flush()

        cmd = [
            sys.executable, "-m", "scrapy", "crawl", "loco",
            "-a", f"transaccion={tx}",
            "-a", f"tipo={tipo}",
            "-a", f"sector={sector}",
            "-a", f"usar_previos={usar_previos}",
        ]

        combo_start = time.time()
        try:
            result = subprocess.run(cmd, timeout=3600)  # 60 min max por combo
            combo_dur = time.time() - combo_start
            combo_times.append(combo_dur)
            if result.returncode == 0:
                ok += 1
                print(f"✅ [{i}/{total}] {label} completado en {fmt_duration(combo_dur)}")
            else:
                fail += 1
                print(f"⚠️ [{i}/{total}] {label} exit code {result.returncode} ({fmt_duration(combo_dur)})")
        except subprocess.TimeoutExpired:
            combo_dur = time.time() - combo_start
            combo_times.append(combo_dur)
            fail += 1
            print(f"⏰ [{i}/{total}] {label} timeout (60 min)")
        except Exception as e:
            combo_dur = time.time() - combo_start
            combo_times.append(combo_dur)
            fail += 1
            print(f"❌ [{i}/{total}] {label} error: {e}")

        # Resumen parcial cada 7 combos (1 ciudad completa por tipo)
        if i % 7 == 0 or i == total:
            avg_time = sum(combo_times) / len(combo_times) if combo_times else 0
            remaining = (total - i) * avg_time
            print(f"\n📈 Checkpoint [{i}/{total}]: {ok} OK, {fail} fallidos")
            print(f"   Promedio por combo: {fmt_duration(avg_time)}")
            print(f"   Tiempo restante estimado: {fmt_duration(remaining)}")
        sys.stdout.flush()

    total_dur = time.time() - global_start
    print(f"\n{'='*60}")
    print(f"📊 Resumen final: {ok} OK, {fail} fallidos de {total} combinaciones")
    print(f"   Duracion total: {fmt_duration(total_dur)}")
    if combo_times:
        print(f"   Promedio por combo: {fmt_duration(sum(combo_times)/len(combo_times))}")
    print(f"{'='*60}")
    sys.stdout.flush()

    # ── Trigger pipeline completo (MongoDB→PG + DBSCAN + Regresión) ──
    api_url = os.getenv("API_URL", "http://api:8000")
    pipeline_secret = os.getenv("PIPELINE_SECRET", "")
    if pipeline_secret and ok > 0:
        print(f"\n🔄 Llamando pipeline completo: {api_url}/pipeline/complete")
        sys.stdout.flush()
        try:
            resp = requests.post(
                f"{api_url}/pipeline/complete",
                headers={"X-Pipeline-Secret": pipeline_secret},
                timeout=600,
            )
            if resp.ok:
                data = resp.json()
                mig = data.get('migration', {})
                print(f"✅ Pipeline completo:")
                print(f"   Migración: {mig.get('total_inserted', 0)} insertados, "
                      f"{mig.get('total_updated', 0)} actualizados")
                print(f"   DBSCAN: {'ejecutado' if data.get('dbscan_triggered') else 'no necesario'}")
                print(f"   Regresión: {'ejecutada' if data.get('regression_triggered') else 'no necesaria'}")
            else:
                print(f"⚠️ Pipeline respondió {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"⚠️ Error llamando pipeline: {e}")
        sys.stdout.flush()
    elif not pipeline_secret:
        print("⚠️ PIPELINE_SECRET no configurado, pipeline no ejecutado")
    else:
        print("⚠️ Ningún combo exitoso, pipeline no ejecutado")

    # Salir con código 0 si al menos la mitad completó
    sys.exit(0 if ok > total // 2 else 1)

if __name__ == "__main__":
    main()
