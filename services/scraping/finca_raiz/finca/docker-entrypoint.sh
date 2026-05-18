#!/usr/bin/env bash
set -e

# Modo por defecto: correr 1 spider con parámetros
MODE="${RUN_MODE:-single}"
SPIDER="${SPIDER:-loco}"

case "$MODE" in
  matrix)
    # Corre TODAS las combinaciones (ver scrape_all.py)
    exec python -m finca.scrape_all
    ;;
  test)
    # Ejecutar test de selectores
    exec python test_selectors.py
    ;;
  test-links)
    # Probar extracción de links (2 páginas)
    exec python -c "
from links import dicc_links_paralelo
url = 'https://www.fincaraiz.com.co/venta/apartamentos/bogota'
result = dicc_links_paralelo(url, max_pages=2)
print(f'Resultados: {len(result)} paginas, {sum(len(v) for v in result.values())} links totales')
"
    ;;
  test-urls)
    # Probar scraping de URLs específicas (proyecto + individual)
    exec python test_scrape_urls.py
    ;;
  migrate)
    # Migrar datos de MongoDB a PostgreSQL
    exec python migrate_mongo_to_postgres.py
    ;;
  single|*)
    # Corre una ejecución con args por env (sin input interactivo)
    exec python -m scrapy crawl "$SPIDER" \
      -a transaccion="${TX:-venta}" \
      -a tipo="${TIPO:-apartamentos}" \
      -a sector="${SECTOR:-bogota}" \
      -a usar_previos="${USAR_PREVIOS:-n}"
    ;;
esac
