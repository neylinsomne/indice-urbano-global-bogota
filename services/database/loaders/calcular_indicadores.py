"""
Calcula todos los indicadores urbanísticos para inmuebles en PostgreSQL.
Se ejecuta después de cargar datos geoespaciales y migrar inmuebles.

Indicadores:
  iacc - Accesibilidad (distancia a TransMilenio)
  iseg - Seguridad (masa crimen por localidad)
  idot - Dotaciones (POIs cercanos en 1km)
  ihed - Hedónico (habitaciones, baños, área)
  ipnu - Potencial normativo (POT: tratamiento + edificabilidad + área actividad)
  iug  - IUG Global (promedio ponderado de los 5)
"""
import os
import sys
import psycopg2

CARMAGBOG_SRID = 900001
CARMAGBOG_PROJ4 = (
    "+proj=tmerc +lat_0=4.680486111 +lon_0=-74.14659167 +k=1.0 "
    "+x_0=92334.879 +y_0=109320.965 +ellps=GRS80 +a=6380687.0 "
    "+rf=298.257222101 +units=m +no_defs"
)
CARMAGBOG_SRTEXT = (
    'PROJCS["PCS_CarMAGBOG",GEOGCS["GCS_CarMAGBOG",'
    'DATUM["CGS_CarMAGBOG",SPHEROID["GRS80_Mod",6380687.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",92334.879],'
    'PARAMETER["False_Northing",109320.965],'
    'PARAMETER["Central_Meridian",-74.14659167],'
    'PARAMETER["Scale_Factor",1.0],'
    'PARAMETER["Latitude_Of_Origin",4.680486111],'
    'UNIT["Meter",1.0]]'
)


def get_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5434')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )


def ensure_carmagbog_srid(cur):
    """Registra CarMAGBOG si no existe."""
    cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (CARMAGBOG_SRID,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext) "
            "VALUES (%s, 'CUSTOM', %s, %s, %s)",
            (CARMAGBOG_SRID, CARMAGBOG_SRID, CARMAGBOG_PROJ4, CARMAGBOG_SRTEXT)
        )
        print("   [CRS] CarMAGBOG registrado")


def main():
    print("=" * 80)
    print("CALCULANDO INDICADORES URBANISTICOS")
    print("=" * 80)

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()

    ensure_carmagbog_srid(cur)

    # Desactivar triggers para updates masivos
    cur.execute("ALTER TABLE iug.inmueble DISABLE TRIGGER ALL")

    # Contar inmuebles
    cur.execute("SELECT COUNT(*) FROM iug.inmueble WHERE geom IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"\n   Inmuebles con geometría: {total}")

    if total == 0:
        print("   [WARNING] No hay inmuebles con geometría, omitiendo cálculo")
        cur.execute("ALTER TABLE iug.inmueble ENABLE TRIGGER ALL")
        conn.close()
        return

    # 1. IACC - Accesibilidad (distancia a TransMilenio)
    print("\n[1/6] Accesibilidad (iacc) - Distancia a TransMilenio...")
    cur.execute("SELECT COUNT(*) FROM iug.estacion_transmilenio")
    n_tm = cur.fetchone()[0]
    if n_tm > 0:
        cur.execute("""
            UPDATE iug.inmueble i SET iacc = sub.score FROM (
                SELECT i.id_inmueble,
                    LEAST(5, GREATEST(0, 5 - (MIN(ST_Distance(i.geom::geography, t.geom::geography)) / 500.0)))::numeric(4,2) as score
                FROM iug.inmueble i
                CROSS JOIN LATERAL (
                    SELECT geom FROM iug.estacion_transmilenio ORDER BY i.geom <-> geom LIMIT 1
                ) t
                WHERE i.geom IS NOT NULL
                GROUP BY i.id_inmueble
            ) sub WHERE i.id_inmueble = sub.id_inmueble
        """)
        print(f"   [OK] {cur.rowcount} inmuebles actualizados")
    else:
        print("   [SKIP] No hay estaciones de TransMilenio")

    # 2. ISEG - Seguridad (masa crimen por localidad)
    print("\n[2/6] Seguridad (iseg) - Masa crimen por localidad...")
    cur.execute("SELECT COUNT(*) FROM iug.criminalidad_localidad")
    n_crim = cur.fetchone()[0]
    if n_crim > 0:
        # Calcular masa_crimen con pesos AHP si no existe
        cur.execute("SELECT COUNT(*) FROM iug.criminalidad_localidad WHERE masa_crimen IS NOT NULL")
        if cur.fetchone()[0] == 0:
            print("   [AHP] Calculando masa_crimen...")
            cur.execute("""
                WITH max_vals AS (
                    SELECT MAX(homicidios_2024) as max_h, MAX(hurto_personas_2024) as max_hu,
                        MAX(delitos_sexuales_2024) as max_ds, MAX(otros_delitos_2024) as max_o
                    FROM iug.criminalidad_localidad
                )
                UPDATE iug.criminalidad_localidad c SET masa_crimen = ROUND((
                    0.45 * COALESCE(c.homicidios_2024::numeric / NULLIF(m.max_h, 0), 0) +
                    0.25 * COALESCE(c.hurto_personas_2024::numeric / NULLIF(m.max_hu, 0), 0) +
                    0.20 * COALESCE(c.delitos_sexuales_2024::numeric / NULLIF(m.max_ds, 0), 0) +
                    0.10 * COALESCE(c.otros_delitos_2024::numeric / NULLIF(m.max_o, 0), 0)
                )::numeric, 4)
                FROM max_vals m
            """)
        cur.execute("""
            UPDATE iug.inmueble i SET iseg = sub.score FROM (
                SELECT i.id_inmueble,
                    LEAST(5, GREATEST(0, 5 * (1 - COALESCE(c.masa_crimen, 0.5))))::numeric(4,2) as score
                FROM iug.inmueble i
                LEFT JOIN iug.localidad l ON i.id_localidad = l.id_localidad
                LEFT JOIN iug.criminalidad_localidad c ON l.nombre ILIKE c.nombre_localidad
                WHERE i.geom IS NOT NULL
            ) sub WHERE i.id_inmueble = sub.id_inmueble
        """)
        print(f"   [OK] {cur.rowcount} inmuebles actualizados")
    else:
        print("   [SKIP] No hay datos de criminalidad")

    # 3. IDOT - Dotaciones (POIs en radio 1km)
    print("\n[3/6] Dotaciones (idot) - POIs cercanos...")
    cur.execute("SELECT COUNT(*) FROM iug.dotaciones_poi")
    n_dot = cur.fetchone()[0]
    if n_dot > 0:
        cur.execute("""
            UPDATE iug.inmueble i SET idot = sub.score FROM (
                SELECT i.id_inmueble,
                    LEAST(5, COUNT(d.*) * 0.05)::numeric(4,2) as score
                FROM iug.inmueble i
                LEFT JOIN iug.dotaciones_poi d ON ST_DWithin(i.geom::geography, d.geom::geography, 1000)
                WHERE i.geom IS NOT NULL
                GROUP BY i.id_inmueble
            ) sub WHERE i.id_inmueble = sub.id_inmueble
        """)
        print(f"   [OK] {cur.rowcount} inmuebles actualizados")
    else:
        print("   [SKIP] No hay dotaciones")

    # 4. IHED - Hedónico (características físicas)
    print("\n[4/6] Hedónico (ihed) - Características físicas...")
    cur.execute("""
        UPDATE iug.inmueble SET ihed = LEAST(5, GREATEST(0,
            COALESCE(habitaciones, 0) * 0.4 + COALESCE(banos, 0) * 0.5 +
            LEAST(COALESCE(area_construida, 0) / 50.0, 3)
        ))::numeric(4,2)
        WHERE geom IS NOT NULL
    """)
    print(f"   [OK] {cur.rowcount} inmuebles actualizados")

    # 5. IPNU - Potencial normativo (POT)
    print("\n[5/6] Potencial (ipnu) - Cruce con POT 555...")
    cur.execute("SELECT COUNT(*) FROM iug.pot_tratamiento")
    n_pot = cur.fetchone()[0]
    if n_pot > 0:
        # Verificar que las funciones de scoring existen
        cur.execute("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid WHERE n.nspname='iug' AND p.proname='score_tratamiento'")
        if cur.fetchone():
            cur.execute("""
                WITH scores AS (
                    SELECT i.id_inmueble,
                        COALESCE(MAX(iug.score_tratamiento(t.nombre)), 2.5) as s_trat,
                        COALESCE(MAX(iug.score_edificabilidad(e.rango)), 2.5) as s_alt,
                        COALESCE(MAX(iug.score_area_actividad(a.codigo)), 3.0) as s_uso
                    FROM iug.inmueble i
                    LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
                    LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
                    LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
                    WHERE i.geom IS NOT NULL
                    GROUP BY i.id_inmueble
                )
                UPDATE iug.inmueble i
                SET ipnu = LEAST(5.0, GREATEST(0.0,
                    (0.4 * s.s_trat) + (0.4 * s.s_alt) + (0.2 * s.s_uso)
                ))
                FROM scores s
                WHERE i.id_inmueble = s.id_inmueble
            """)
            print(f"   [OK] {cur.rowcount} inmuebles actualizados")
        else:
            print("   [SKIP] Funciones de scoring POT no encontradas (ejecute calcular_ipnu.sql)")
    else:
        print("   [SKIP] No hay datos POT")

    # 6. IUG - Global (promedio ponderado)
    print("\n[6/6] IUG Global (promedio ponderado)...")
    cur.execute("""
        UPDATE iug.inmueble SET
            iug = ROUND((
                COALESCE(iacc, 0) * 0.20 + COALESCE(iseg, 0) * 0.20 +
                COALESCE(idot, 0) * 0.20 + COALESCE(ihed, 0) * 0.20 +
                COALESCE(ipnu, 0) * 0.20
            )::numeric, 2),
            iurb = ROUND((
                COALESCE(iacc, 0) * 0.20 + COALESCE(iseg, 0) * 0.20 +
                COALESCE(idot, 0) * 0.20 + COALESCE(ihed, 0) * 0.20 +
                COALESCE(ipnu, 0) * 0.20
            )::numeric, 2)
        WHERE geom IS NOT NULL
    """)
    print(f"   [OK] {cur.rowcount} inmuebles actualizados")

    # Reactivar triggers
    cur.execute("ALTER TABLE iug.inmueble ENABLE TRIGGER ALL")

    # Resumen
    cur.execute("""
        SELECT
            ROUND(AVG(iacc)::numeric, 2), ROUND(AVG(iseg)::numeric, 2),
            ROUND(AVG(idot)::numeric, 2), ROUND(AVG(ihed)::numeric, 2),
            ROUND(AVG(ipnu)::numeric, 2), ROUND(AVG(iug)::numeric, 2),
            ROUND(MIN(ipnu)::numeric, 2), ROUND(MAX(ipnu)::numeric, 2)
        FROM iug.inmueble WHERE geom IS NOT NULL
    """)
    r = cur.fetchone()
    print(f"\n{'=' * 80}")
    print(f"RESUMEN DE INDICADORES")
    print(f"{'=' * 80}")
    print(f"   iacc (Accesibilidad):  {r[0]}")
    print(f"   iseg (Seguridad):      {r[1]}")
    print(f"   idot (Dotaciones):     {r[2]}")
    print(f"   ihed (Hedónico):       {r[3]}")
    print(f"   ipnu (Potencial):      {r[4]} (min={r[6]}, max={r[7]})")
    print(f"   iug  (Global):         {r[5]}")
    print(f"{'=' * 80}")
    print(f"[OK] CALCULO DE INDICADORES COMPLETADO")
    print(f"{'=' * 80}")

    conn.close()


if __name__ == '__main__':
    main()
