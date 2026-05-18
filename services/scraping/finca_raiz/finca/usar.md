scrape all:

# Todas las combinaciones por defecto

docker build -t finca_scraper .
docker run --rm --network=gisnet \
 -e RUN_MODE=matrix \
 -e TXS="venta" \
 -e TIPOS="apartamentos,casas" \
 -e SECTORES="bogota,medellin" \
 finca_scraper

docker entrypoint:

chmod +x docker-entrypoint.sh

Correr código:
#para scrapear todo:
docker compose -f compose.selenium.yml exec scraper sh -lc "python /app/scrape_all.py"

#para scrapear una opción específica (ejemplo: docker compose -f compose.selenium.yml run --rm scraper \
 sh -lc "scrapy crawl loco -a transaccion=venta -a tipo=apartamentos -a sector=bogota -a usar_previos=n"
)
