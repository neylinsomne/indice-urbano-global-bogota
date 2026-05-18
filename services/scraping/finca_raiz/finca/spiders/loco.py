from typing import Any, Iterable
import scrapy
import unicodedata
import json
import re
from datetime import datetime
from finca.links import dicc_links_paralelo

import logging, hashlib
with open(__file__, "rb") as _f:
    _md5 = hashlib.md5(_f.read()).hexdigest()
logging.getLogger(__name__).warning("LOCO loaded from %s md5=%s", __file__, _md5)


# Constantes a nivel de modulo (usadas por LocoSpider y scrape_all.py)
_TRANSACCIONES = ["venta", "arriendo"]
_SECTORES = ['bogota', 'medellin', 'cali', 'barranquilla', 'cajica', 'chia', 'madrid']
_TIPOS = ['apartamentos', 'casas', 'locales', 'lotes', 'bodegas', 'parqueadero', 'inmuebles', 'fincas']
_CIUDAD_DEPARTAMENTO = {
    'bogota': 'bogota-dc',
    'medellin': 'antioquia',
    'cali': 'valle-del-cauca',
    'barranquilla': 'atlantico',
    'cajica': 'cundinamarca',
    'chia': 'cundinamarca',
    'madrid': 'cundinamarca',
}
_ALL_COLLECTIONS = [f'{t}_{tx}' for t in _TIPOS for tx in _TRANSACCIONES]


class LocoSpider(scrapy.Spider):
    name = "loco"
    error_scrapeo = []
    transacciones = _TRANSACCIONES
    sectores_a_scrapear = _SECTORES
    tipo_inmueble = _TIPOS
    CIUDAD_DEPARTAMENTO = _CIUDAD_DEPARTAMENTO
    coneccion = {ciudad: _ALL_COLLECTIONS for ciudad in _SECTORES}

    def closed(self, reason):
        print(f"\nSpider cerrado. Motivo: {reason}")
        if self.error_scrapeo:
            print(f"URLs con error: {len(self.error_scrapeo)}")

    def __init__(self, transaccion="venta", tipo="apartamentos", sector="bogota", usar_previos="n", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaccion = transaccion.strip().lower()
        self.tipo = tipo.strip().lower()
        self.sector = sector.strip().lower()
        self.usar_resultados_previos = usar_previos.strip().lower() in {"s", "si", "y", "yes", "true", "1"}

        if self.transaccion not in self.transacciones:
            raise ValueError(f"Transaccion no valida: {self.transaccion}")
        if self.tipo not in self.tipo_inmueble:
            raise ValueError(f"Tipo no valido: {self.tipo}")
        if self.sector not in self.sectores_a_scrapear:
            raise ValueError(f"Sector no valido: {self.sector}")

        departamento = self.CIUDAD_DEPARTAMENTO.get(self.sector)
        if departamento:
            self.search_url = f"https://www.fincaraiz.com.co/{self.transaccion}/{self.tipo}/{self.sector}/{departamento}"
        else:
            self.search_url = f"https://www.fincaraiz.com.co/{self.transaccion}/{self.tipo}/{self.sector}"
        self.trans_completa = f"{self.tipo}_{self.transaccion}"
        self.items_insertados = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        spider.settings = crawler.settings
        mongo_cfg = spider.settings.get("MONGO_CONEXION", {})
        if spider.sector not in mongo_cfg or spider.trans_completa not in mongo_cfg.get(spider.sector, {}):
            spider.logger.warning(
                f"[MONGO] No hay mapeo para {spider.sector}/{spider.trans_completa}."
            )
        return spider

    def _fallback_paginas(self, max_pages=10):
        base = {1: [self.search_url]}
        for i in range(2, max_pages + 1):
            base[i] = [f"{self.search_url}/pagina{i}"]
        return base

    def start_requests(self):
        paginas = dicc_links_paralelo(self.search_url, opp=self.usar_resultados_previos)
        if not paginas:
            self.logger.warning("dicc_links_paralelo no devolvio resultados; usando fallback.")
            paginas = self._fallback_paginas(max_pages=10)
        total_urls = sum(len(v) for v in paginas.values())
        self.logger.info(f"Semillas de paginacion: {len(paginas)} paginas, total URLs={total_urls}")

        for pagina, urls in paginas.items():
            for url in urls:
                # Scrapy puro - sin Playwright. Los datos vienen en __NEXT_DATA__
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={'keyword': self.sector, 'page': pagina},
                    errback=self.errback,
                )

    def errback(self, failure):
        self.logger.error(f"Error on {failure.request.url}: {failure.value}")
        self.error_scrapeo.append(failure.request.url)

    def _get_next_data(self, response):
        """Extrae y parsea __NEXT_DATA__ del HTML."""
        raw = response.css('script#__NEXT_DATA__::text').get()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def parse(self, response):
        url = response.url
        self.logger.info(f"Procesando URL: {url}")

        next_data = self._get_next_data(response)
        if not next_data:
            self.logger.warning(f"No __NEXT_DATA__ en {url}")
            self.error_scrapeo.append(url)
            return

        data = next_data.get('props', {}).get('pageProps', {}).get('data', {})
        if not data:
            self.logger.warning(f"Sin data en __NEXT_DATA__ de {url}")
            self.error_scrapeo.append(url)
            return

        codigo_fr = url.rstrip('/').split('/')[-1]
        fecha = datetime.now().strftime("%d-%m-%Y")

        # Ubicacion
        locations = data.get('locations', {})
        ubicacion = None
        ubicacion_asociada = None
        loc_main = locations.get('location_main', {})
        if isinstance(loc_main, dict):
            ubicacion = loc_main.get('name')
        city_list = locations.get('city', [])
        if isinstance(city_list, list) and city_list:
            ubicacion_asociada = city_list[0].get('name') if isinstance(city_list[0], dict) else None

        # Facilities / caracteristicas
        facilities = data.get('facilities', [])
        caracteristicas = []
        for f in facilities:
            if isinstance(f, dict):
                name = f.get('name', '')
                if name:
                    caracteristicas.append(name)
            elif isinstance(f, str):
                caracteristicas.append(f)

        # Inmobiliaria
        agent = data.get('agent', {}) or data.get('landlord', {}) or {}
        inmobiliaria = agent.get('name') if isinstance(agent, dict) else None

        # Imagen
        image_url = data.get('image')
        if not image_url:
            images = data.get('images', [])
            if images and isinstance(images[0], dict):
                image_url = images[0].get('image')

        # Campos comunes
        base = {
            "pagina": "finca_raiz",
            "ubicacion": ubicacion,
            "ubicacion_asociada": ubicacion_asociada,
            "codigo_fr": codigo_fr,
            "image": image_url,
            "direccion": data.get('address'),
            "latitud": data.get('latitude'),
            "longitud": data.get('longitude'),
            "inmobiliaria": inmobiliaria,
            "descripcion": data.get('description'),
            "fecha": fecha,
            "caracteristicas": caracteristicas,
        }

        if "proyectos" in url:
            yield from self._parse_proyecto(data, base, url)
        else:
            yield from self._parse_propiedad(data, base, url)

    def _parse_proyecto(self, data, base, url):
        """Parsea un proyecto con multiples unidades desde __NEXT_DATA__."""
        base["proyecto"] = True
        base["antiguedad"] = "nuevo"
        base["estado"] = data.get('construction_state_name', 'En construccion')
        base["estrato"] = data.get('stratum')

        units = data.get('commercial_units', [])
        if not units:
            # Fallback: yield el proyecto como un solo item
            price_data = data.get('price', {})
            base["precio"] = price_data.get('amount') if isinstance(price_data, dict) else None
            base["area_construida"] = data.get('m2')
            base["habitaciones"] = data.get('bedrooms')
            base["banos"] = data.get('bathrooms')
            self.logger.info(f"Proyecto sin unidades: {url}")
            self.items_insertados += 1
            yield base
            return

        self.logger.info(f"Proyecto con {len(units)} unidades")
        for unit in units:
            if not isinstance(unit, dict):
                continue
            item = base.copy()
            item["area_construida"] = unit.get('m2') or unit.get('area')
            item["area_privada"] = unit.get('m2apto') or unit.get('m2_private')
            item["habitaciones"] = unit.get('bedrooms')
            item["banos"] = unit.get('bathrooms')
            item["tipo_de_inmueble"] = unit.get('property_type_name') or unit.get('type')

            # Precio de la unidad
            price_data = unit.get('price', {})
            if isinstance(price_data, dict):
                item["precio"] = price_data.get('amount')
            elif isinstance(price_data, (int, float)):
                item["precio"] = price_data
            else:
                item["precio"] = unit.get('price')

            self.items_insertados += 1
            yield item

    def _parse_propiedad(self, data, base, url):
        """Parsea una propiedad individual desde __NEXT_DATA__."""
        base["proyecto"] = False

        # Precio
        price_data = data.get('price', {})
        base["precio"] = price_data.get('amount') if isinstance(price_data, dict) else None

        # Campos directos
        base["habitaciones"] = data.get('bedrooms')
        base["banos"] = data.get('bathrooms')
        base["area_construida"] = data.get('m2') or data.get('m2Built')
        base["area_privada"] = data.get('m2apto')
        base["estrato"] = data.get('stratum')
        base["parqueaderos"] = data.get('garage')

        # Ficha tecnica (campos adicionales)
        tech_sheet = data.get('technicalSheet', [])
        for entry in tech_sheet:
            if not isinstance(entry, dict):
                continue
            label = entry.get('label', '')
            value = entry.get('value', '')
            if label and value:
                key = normalizar_texto(label)
                # No sobreescribir campos ya extraidos
                if key not in base:
                    base[key] = value

        self.logger.info(f"Propiedad extraida: {base.get('codigo_fr')} con {len(base.get('caracteristicas', []))} caracteristicas")
        self.items_insertados += 1
        yield base


def normalizar_texto(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    texto = texto.replace(" ", "_")
    return texto
