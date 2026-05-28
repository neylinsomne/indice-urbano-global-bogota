-- ============================================================================
-- Extrae todos los estadísticos del corpus v2.0 que necesitan los TikZ inline
-- de la presentación. Corre así:
--
--   docker exec -i iug-postgres psql -U postgres -d postgres \
--     < scripts/dump_v2_stats_for_figures.sql > scripts/stats_v2.txt 2>&1
--
-- Luego me pasas el archivo stats_v2.txt y reescribo cada figura como TikZ
-- inline en Presentacion_grado.tex (sin dependencias de PDFs externos).
-- ============================================================================

\echo === HIST_IACC: histograma de I_ACC en 20 bins ===
SELECT
  width_bucket(iacc, 0, 5, 20) AS bin,
  ROUND(MIN(iacc)::numeric, 2) AS lo,
  ROUND(MAX(iacc)::numeric, 2) AS hi,
  COUNT(*) AS n
FROM iug.inmueble
WHERE iacc IS NOT NULL AND id_localidad IS NOT NULL  -- solo Bogotá
GROUP BY bin ORDER BY bin;

\echo
\echo === HIST_SUBINDICES: medianas y cuartiles de cada subíndice ===
SELECT
  'iurb' AS dim,
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY iurb)::numeric, 2) AS q1,
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY iurb)::numeric, 2) AS median,
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY iurb)::numeric, 2) AS q3,
  ROUND(AVG(iurb)::numeric, 2) AS mean
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND iurb IS NOT NULL
UNION ALL SELECT 'iacc',
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY iacc)::numeric, 2),
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY iacc)::numeric, 2),
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY iacc)::numeric, 2),
  ROUND(AVG(iacc)::numeric, 2)
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND iacc IS NOT NULL
UNION ALL SELECT 'iseg',
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY iseg)::numeric, 2),
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY iseg)::numeric, 2),
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY iseg)::numeric, 2),
  ROUND(AVG(iseg)::numeric, 2)
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND iseg IS NOT NULL
UNION ALL SELECT 'ihed',
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY ihed)::numeric, 2),
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY ihed)::numeric, 2),
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY ihed)::numeric, 2),
  ROUND(AVG(ihed)::numeric, 2)
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND ihed IS NOT NULL
UNION ALL SELECT 'idot',
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY idot)::numeric, 2),
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY idot)::numeric, 2),
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY idot)::numeric, 2),
  ROUND(AVG(idot)::numeric, 2)
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND idot IS NOT NULL
UNION ALL SELECT 'ipnu',
  ROUND(percentile_cont(0.25) WITHIN GROUP (ORDER BY ipnu)::numeric, 2),
  ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY ipnu)::numeric, 2),
  ROUND(percentile_cont(0.75) WITHIN GROUP (ORDER BY ipnu)::numeric, 2),
  ROUND(AVG(ipnu)::numeric, 2)
FROM iug.inmueble WHERE id_localidad IS NOT NULL AND ipnu IS NOT NULL
ORDER BY dim;

\echo
\echo === HEATMAP_CORR: matriz de correlaciones Pearson entre subíndices ===
SELECT
  ROUND(corr(iacc, iseg)::numeric, 3) AS r_acc_seg,
  ROUND(corr(iacc, ihed)::numeric, 3) AS r_acc_hed,
  ROUND(corr(iacc, idot)::numeric, 3) AS r_acc_dot,
  ROUND(corr(iacc, ipnu)::numeric, 3) AS r_acc_pnu,
  ROUND(corr(iseg, ihed)::numeric, 3) AS r_seg_hed,
  ROUND(corr(iseg, idot)::numeric, 3) AS r_seg_dot,
  ROUND(corr(iseg, ipnu)::numeric, 3) AS r_seg_pnu,
  ROUND(corr(ihed, idot)::numeric, 3) AS r_hed_dot,
  ROUND(corr(ihed, ipnu)::numeric, 3) AS r_hed_pnu,
  ROUND(corr(idot, ipnu)::numeric, 3) AS r_dot_pnu
FROM iug.inmueble
WHERE id_localidad IS NOT NULL
  AND iacc IS NOT NULL AND iseg IS NOT NULL AND ihed IS NOT NULL
  AND idot IS NOT NULL AND ipnu IS NOT NULL;

\echo
\echo === SCATTER_SEG: nube I_SEG vs I_HED, 30 puntos representativos ===
SELECT
  ROUND(iseg::numeric, 2) AS x_iseg,
  ROUND(ihed::numeric, 2) AS y_ihed
FROM iug.inmueble
WHERE id_localidad IS NOT NULL AND iseg IS NOT NULL AND ihed IS NOT NULL
ORDER BY random()
LIMIT 60;

\echo
\echo === POI_CATEGORIAS: conteo por categoría tras v2.0 ===
SELECT 'Salud · centros' AS cat, COUNT(*) AS n FROM iug.centro_salud
UNION ALL SELECT 'Salud · dotación', COUNT(*) FROM iug.dotacion_salud
UNION ALL SELECT 'Colegios', COUNT(*) FROM iug.colegio
UNION ALL SELECT 'Universidades', COUNT(*) FROM iug.universidad
UNION ALL SELECT 'Centros comerciales', COUNT(*) FROM iug.centro_comercial
UNION ALL SELECT 'Cuadrantes policía', COUNT(*) FROM iug.cuadrante_policia
ORDER BY n DESC;

\echo
\echo === MAPA_IUG_V2: IUG promedio por localidad (para coroplético) ===
SELECT l.nombre,
       ROUND(AVG(i.iurb)::numeric, 2) AS iug_mean,
       COUNT(*) AS n
FROM iug.localidad l
LEFT JOIN iug.inmueble i ON i.id_localidad = l.id_localidad AND i.iurb IS NOT NULL
GROUP BY l.id_localidad, l.nombre
ORDER BY iug_mean DESC NULLS LAST;
