"""
API Client para Ciencuadras.
Intenta descubrir una API no documentada (Next.js /_next/data, REST, GraphQL)
y extraer datos estructurados sin necesidad de Selenium.
"""
import json
import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    BASE_URL, API_CANDIDATES, HEADERS,
    REQUEST_DELAY, MAX_PAGES, FIELDS,
)

log = logging.getLogger(__name__)


class CiencuadrasAPIClient:
    """Cliente que intenta usar APIs internas de Ciencuadras."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._api_base: Optional[str] = None
        self._build_id: Optional[str] = None

    # ── Descubrimiento ────────────────────────────────────────────────

    def discover(self) -> bool:
        """
        Intenta descubrir un endpoint de API funcional.
        Retorna True si encuentra uno utilizable.
        """
        log.info("Descubriendo API de Ciencuadras...")

        # 1. Intentar descubrir buildId de Next.js
        if self._discover_nextjs():
            return True

        # 2. Probar endpoints candidatos directamente
        if self._probe_api_endpoints():
            return True

        # 3. Buscar en __NEXT_DATA__ del HTML
        if self._discover_from_html():
            return True

        log.warning("No se encontro API utilizable, se usara scraper web")
        return False

    def _discover_nextjs(self) -> bool:
        """Busca el buildId de Next.js en la pagina principal."""
        try:
            resp = self.session.get(BASE_URL, timeout=15)
            resp.raise_for_status()

            # Buscar buildId en el script __NEXT_DATA__
            match = re.search(
                r'"buildId"\s*:\s*"([^"]+)"', resp.text
            )
            if match:
                self._build_id = match.group(1)
                log.info(f"Next.js buildId encontrado: {self._build_id}")

                # Verificar que /_next/data/{buildId}/ funciona
                test_url = (
                    f"{BASE_URL}/_next/data/{self._build_id}/index.json"
                )
                try:
                    test_resp = self.session.get(test_url, timeout=10)
                    if test_resp.ok and "json" in test_resp.headers.get(
                        "content-type", ""
                    ):
                        self._api_base = (
                            f"{BASE_URL}/_next/data/{self._build_id}"
                        )
                        log.info(f"API Next.js confirmada: {self._api_base}")
                        return True
                except Exception:
                    pass

            # Buscar buildId en scripts de la pagina
            soup = BeautifulSoup(resp.text, "lxml")
            for script in soup.find_all("script", src=True):
                src = script["src"]
                if "/_next/static/" in src:
                    parts = src.split("/_next/static/")
                    if len(parts) > 1:
                        candidate_id = parts[1].split("/")[0]
                        if len(candidate_id) > 10:
                            self._build_id = candidate_id
                            log.info(
                                f"buildId candidato desde script: "
                                f"{self._build_id}"
                            )
                            break

        except Exception as e:
            log.debug(f"Error descubriendo Next.js: {e}")
        return False

    def _probe_api_endpoints(self) -> bool:
        """Prueba endpoints API candidatos."""
        for url in API_CANDIDATES:
            if "/_next/data/" in url:
                continue  # Ya probado en _discover_nextjs

            try:
                resp = self.session.get(url, timeout=10)
                content_type = resp.headers.get("content-type", "")

                if resp.ok and "json" in content_type:
                    log.info(f"API encontrada: {url} (status {resp.status_code})")
                    self._api_base = url
                    return True

                # GraphQL: probar con introspection query
                if "graphql" in url.lower():
                    gql_resp = self.session.post(
                        url,
                        json={"query": "{ __schema { types { name } } }"},
                        timeout=10,
                    )
                    if gql_resp.ok and "data" in gql_resp.text:
                        log.info(f"GraphQL endpoint encontrado: {url}")
                        self._api_base = url
                        return True

            except Exception as e:
                log.debug(f"Endpoint {url} no disponible: {e}")

        return False

    def _discover_from_html(self) -> bool:
        """Busca datos JSON embebidos en el HTML (e.g. __NEXT_DATA__)."""
        try:
            # Probar una pagina de listados real
            test_url = f"{BASE_URL}/venta/apartamentos/bogota"
            resp = self.session.get(test_url, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data and next_data.string:
                data = json.loads(next_data.string)
                props = data.get("props", {}).get("pageProps", {})
                if props:
                    log.info(
                        "__NEXT_DATA__ encontrado con pageProps "
                        f"(keys: {list(props.keys())[:5]})"
                    )
                    self._api_base = "__NEXT_DATA__"
                    return True

            # Buscar fetch/XHR endpoints en scripts inline
            for script in soup.find_all("script"):
                if script.string and "fetch(" in (script.string or ""):
                    urls = re.findall(
                        r'fetch\(["\']([^"\']+)["\']', script.string
                    )
                    for u in urls:
                        if "/api/" in u or "/search" in u:
                            log.info(f"Endpoint fetch encontrado en script: {u}")
                            full_url = (
                                u if u.startswith("http")
                                else f"{BASE_URL}{u}"
                            )
                            self._api_base = full_url
                            return True

        except Exception as e:
            log.debug(f"Error buscando en HTML: {e}")
        return False

    # ── Extraccion de datos ───────────────────────────────────────────

    def fetch_listings(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """
        Obtiene listings usando la API descubierta.
        Retorna lista de dicts con datos de propiedades.
        """
        if not self._api_base:
            return []

        if self._api_base == "__NEXT_DATA__":
            return self._fetch_via_next_data(ciudad, tipo, transaccion)
        elif "graphql" in self._api_base.lower():
            return self._fetch_via_graphql(ciudad, tipo, transaccion)
        elif "/_next/data/" in self._api_base:
            return self._fetch_via_next_api(ciudad, tipo, transaccion)
        else:
            return self._fetch_via_rest(ciudad, tipo, transaccion)

    def _fetch_via_next_data(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """Extrae datos del script __NEXT_DATA__ embebido en cada pagina."""
        all_listings = []
        page = 1

        while page <= MAX_PAGES:
            url = f"{BASE_URL}/{transaccion}/{tipo}/{ciudad}"
            if page > 1:
                url += f"?pagina={page}"

            try:
                resp = self.session.get(url, timeout=15)
                if not resp.ok:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                next_data = soup.find("script", id="__NEXT_DATA__")
                if not next_data or not next_data.string:
                    break

                data = json.loads(next_data.string)
                props = data.get("props", {}).get("pageProps", {})

                # Buscar la lista de propiedades en diferentes keys comunes
                listings = self._extract_listings_from_props(props)

                if not listings:
                    log.info(
                        f"Sin mas resultados en pagina {page} "
                        f"({ciudad}/{tipo}/{transaccion})"
                    )
                    break

                parsed = [self._normalize(item) for item in listings]
                all_listings.extend([p for p in parsed if p])

                log.info(
                    f"API __NEXT_DATA__ pag {page}: "
                    f"{len(listings)} listings "
                    f"({ciudad}/{tipo}/{transaccion})"
                )

                page += 1
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                log.error(f"Error en __NEXT_DATA__ pag {page}: {e}")
                break

        return all_listings

    def _fetch_via_next_api(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """Usa la API /_next/data/{buildId}/... para obtener datos JSON."""
        all_listings = []
        page = 1

        while page <= MAX_PAGES:
            path = f"/{transaccion}/{tipo}/{ciudad}.json"
            params = {}
            if page > 1:
                params["pagina"] = page

            url = f"{self._api_base}{path}"

            try:
                resp = self.session.get(url, params=params, timeout=15)
                if not resp.ok:
                    break

                data = resp.json()
                props = data.get("pageProps", {})
                listings = self._extract_listings_from_props(props)

                if not listings:
                    break

                parsed = [self._normalize(item) for item in listings]
                all_listings.extend([p for p in parsed if p])

                log.info(
                    f"API Next.js pag {page}: "
                    f"{len(listings)} listings "
                    f"({ciudad}/{tipo}/{transaccion})"
                )

                page += 1
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                log.error(f"Error en Next.js API pag {page}: {e}")
                break

        return all_listings

    def _fetch_via_graphql(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """Consulta via GraphQL si disponible."""
        all_listings = []
        offset = 0
        limit = 50

        while offset < MAX_PAGES * limit:
            query = """
            query SearchProperties($input: SearchInput!) {
                searchProperties(input: $input) {
                    results {
                        id code price area rooms bathrooms
                        stratum type location address
                        latitude longitude images description
                        agency features
                    }
                    total
                    hasMore
                }
            }
            """
            variables = {
                "input": {
                    "city": ciudad,
                    "propertyType": tipo,
                    "transactionType": transaccion,
                    "offset": offset,
                    "limit": limit,
                }
            }

            try:
                resp = self.session.post(
                    self._api_base,
                    json={"query": query, "variables": variables},
                    timeout=15,
                )
                if not resp.ok:
                    break

                data = resp.json()
                results = (
                    data.get("data", {})
                    .get("searchProperties", {})
                    .get("results", [])
                )

                if not results:
                    break

                parsed = [self._normalize(item) for item in results]
                all_listings.extend([p for p in parsed if p])

                has_more = (
                    data.get("data", {})
                    .get("searchProperties", {})
                    .get("hasMore", False)
                )
                if not has_more:
                    break

                offset += limit
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                log.error(f"Error en GraphQL offset {offset}: {e}")
                break

        return all_listings

    def _fetch_via_rest(
        self,
        ciudad: str,
        tipo: str,
        transaccion: str,
    ) -> list[dict]:
        """Consulta via REST API generica."""
        all_listings = []
        page = 1

        while page <= MAX_PAGES:
            params = {
                "city": ciudad,
                "type": tipo,
                "transaction": transaccion,
                "page": page,
                "limit": 50,
            }

            try:
                resp = self.session.get(
                    self._api_base, params=params, timeout=15
                )
                if not resp.ok:
                    break

                data = resp.json()

                # Intentar diferentes estructuras de respuesta
                if isinstance(data, list):
                    listings = data
                elif isinstance(data, dict):
                    listings = (
                        data.get("results")
                        or data.get("data")
                        or data.get("properties")
                        or data.get("items")
                        or []
                    )
                else:
                    break

                if not listings:
                    break

                parsed = [self._normalize(item) for item in listings]
                all_listings.extend([p for p in parsed if p])

                log.info(
                    f"REST API pag {page}: "
                    f"{len(listings)} listings "
                    f"({ciudad}/{tipo}/{transaccion})"
                )

                page += 1
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                log.error(f"Error en REST API pag {page}: {e}")
                break

        return all_listings

    # ── Helpers ───────────────────────────────────────────────────────

    def _extract_listings_from_props(self, props: dict) -> list:
        """
        Busca la lista de propiedades en diferentes keys de pageProps.
        Ciencuadras puede usar diferentes estructuras.
        """
        # Keys comunes donde se guardan los resultados
        candidate_keys = [
            "properties", "results", "listings", "items",
            "searchResults", "data", "offers", "inmuebles",
            "propiedades", "avisos",
        ]

        for key in candidate_keys:
            val = props.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val
            # Un nivel mas profundo
            if isinstance(val, dict):
                for inner_key in candidate_keys:
                    inner_val = val.get(inner_key)
                    if isinstance(inner_val, list) and len(inner_val) > 0:
                        return inner_val

        # Buscar recursivamente la primera lista grande
        for key, val in props.items():
            if isinstance(val, list) and len(val) >= 5:
                # Verificar que parecen ser propiedades (tienen precio/area)
                sample = val[0] if val else {}
                if isinstance(sample, dict) and any(
                    k in str(sample.keys()).lower()
                    for k in ["price", "precio", "area", "code", "codigo"]
                ):
                    return val

        return []

    def _normalize(self, item: dict) -> Optional[dict]:
        """
        Normaliza un item de la API al formato estandar del proyecto.
        Mapea diferentes nombres de campos al esquema comun.
        """
        if not isinstance(item, dict):
            return None

        # Mapeo de nombres de campos (API -> estandar)
        field_map = {
            "codigo": ["code", "codigo", "id", "propertyId", "reference"],
            "precio": ["price", "precio", "salePrice", "rentPrice", "value"],
            "area": ["area", "builtArea", "totalArea", "size", "m2"],
            "habitaciones": ["rooms", "bedrooms", "habitaciones", "alcobas"],
            "banos": ["bathrooms", "banos", "bathCount"],
            "estrato": ["stratum", "estrato", "socioEconomicLevel"],
            "tipo": ["type", "propertyType", "tipo", "tipoInmueble"],
            "ubicacion": [
                "location", "neighborhood", "barrio", "ubicacion", "zone",
            ],
            "direccion": ["address", "direccion", "street"],
            "lat": ["latitude", "lat", "latitud"],
            "lon": ["longitude", "lon", "lng", "longitud"],
            "image": ["image", "mainImage", "thumbnail", "photo", "imagen"],
            "descripcion": ["description", "descripcion", "detail"],
            "inmobiliaria": [
                "agency", "realEstate", "inmobiliaria", "company",
            ],
            "caracteristicas": [
                "features", "amenities", "caracteristicas", "extras",
            ],
        }

        normalized = {}
        for target, sources in field_map.items():
            for src in sources:
                val = item.get(src)
                if val is not None:
                    normalized[target] = val
                    break

        # Manejar imagenes como lista
        images = item.get("images") or item.get("photos") or item.get("imagenes")
        if images and isinstance(images, list) and not normalized.get("image"):
            normalized["image"] = images[0] if images else None

        # Solo retornar si tiene al menos codigo o precio
        if normalized.get("codigo") or normalized.get("precio"):
            return normalized

        return None
