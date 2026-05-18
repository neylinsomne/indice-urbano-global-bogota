"""
Router de Datos Geográficos

Endpoints para servir datos GeoJSON de localidades, barrios y capas geográficas.
Implementa caching Redis para mejorar rendimiento con datos pesados como barrios (837 features).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
import asyncpg
import json
import logging

from db.postgre import get_db_pool
from db.redis_cache import cache_get, cache_set, cache_delete

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/geo", tags=["geo"])

# Cache keys
CACHE_KEY_LOCALIDADES = "geo:localidades"
CACHE_KEY_LOCALIDADES_LISTA = "geo:localidades:lista"
CACHE_KEY_BARRIOS_ALL = "geo:barrios:all"
CACHE_KEY_BARRIOS_LOC = "geo:barrios:loc:"  # + nombre_localidad

# TTL: 1 hora para datos geográficos (cambian muy poco)
CACHE_TTL = 3600


@router.get("/localidades/lista")
async def obtener_lista_localidades(
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Lista simple de localidades para dropdowns/selects.
    Más ligero que el endpoint GeoJSON completo.
    """
    # Intentar obtener de cache
    cached = await cache_get(CACHE_KEY_LOCALIDADES_LISTA)
    if cached:
        logger.debug("Cache HIT: localidades lista")
        return cached

    try:
        async with db.acquire() as conn:
            query = """
            SELECT id_localidad, nombre
            FROM iug.localidad
            ORDER BY nombre
            """
            results = await conn.fetch(query)

            data = [
                {"id": row['id_localidad'], "nombre": row['nombre']}
                for row in results
            ]

            # Guardar en cache
            await cache_set(CACHE_KEY_LOCALIDADES_LISTA, data, CACHE_TTL)
            return data

    except Exception as e:
        logger.error(f"Error obteniendo lista de localidades: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo localidades: {str(e)}")


_TIPOS_INMUEBLE_VALIDOS = {"Apartamento", "Casa", "Lote", "Oficina", "Local", "Bodega"}


@router.get("/localidades")
async def obtener_localidades_geojson(
    incluir_estadisticas: bool = Query(True, description="Incluir estadísticas de inmuebles"),
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar promedios por tipo (Apartamento, Casa, Lote, ...)"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene GeoJSON de localidades de Bogotá con estadísticas opcionales.
    Datos cacheados en Redis por 1 hora (sólo cuando no hay filtro de tipo).

    Returns:
        GeoJSON FeatureCollection con geometrías y propiedades de cada localidad
    """
    # Validamos contra whitelist para evitar inyección en el JOIN parametrizado
    if tipo_inmueble and tipo_inmueble not in _TIPOS_INMUEBLE_VALIDOS:
        raise HTTPException(400, f"tipo_inmueble inválido. Opciones: {sorted(_TIPOS_INMUEBLE_VALIDOS)}")

    # Cache: sólo cuando es la consulta default (sin filtro de tipo)
    use_cache = incluir_estadisticas and not tipo_inmueble
    if use_cache:
        cached = await cache_get(CACHE_KEY_LOCALIDADES)
        if cached:
            logger.debug("Cache HIT: localidades GeoJSON")
            return cached

    try:
        async with db.acquire() as conn:
            if incluir_estadisticas:
                # Filtro opcional por tipo. Si no se filtra, los promedios incluyen
                # todos los inmuebles de la localidad. Si se filtra, sólo los del tipo.
                tipo_filter = ""
                params = []
                if tipo_inmueble:
                    tipo_filter = " AND i.tipo_inmueble = $1"
                    params.append(tipo_inmueble)

                query = f"""
                WITH localidad_stats AS (
                    SELECT
                        l.id_localidad,
                        l.nombre,
                        COUNT(i.id_inmueble) as inmuebles_count,
                        COALESCE(AVG(i.precio)::BIGINT, 0) as precio_promedio,
                        COALESCE(AVG(i.area), 0) as area_promedio,
                        COALESCE(AVG(i.iurb), 0) as iurb_promedio,
                        COALESCE(AVG(i.iacc), 0) as iacc_promedio,
                        COALESCE(AVG(i.iseg), 0) as iseg_promedio,
                        COALESCE(AVG(i.ihed), 0) as ihed_promedio,
                        COALESCE(AVG(i.ipnu), 0) as ipnu_promedio,
                        COALESCE(AVG(i.idot), 0) as idot_promedio
                    FROM iug.localidad l
                    LEFT JOIN iug.inmueble i
                        ON i.id_localidad = l.id_localidad{tipo_filter}
                    GROUP BY l.id_localidad, l.nombre
                )
                SELECT
                    jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(
                            jsonb_build_object(
                                'type', 'Feature',
                                'properties', jsonb_build_object(
                                    'id', ls.id_localidad,
                                    'nombre', ls.nombre,
                                    'inmuebles_count', ls.inmuebles_count,
                                    'precio_promedio', ls.precio_promedio,
                                    'area_promedio', ROUND(ls.area_promedio::numeric, 2),
                                    'iurb_promedio', ROUND(ls.iurb_promedio::numeric, 2),
                                    'iacc_promedio', ROUND(ls.iacc_promedio::numeric, 2),
                                    'iseg_promedio', ROUND(ls.iseg_promedio::numeric, 2),
                                    'ihed_promedio', ROUND(ls.ihed_promedio::numeric, 2),
                                    'ipnu_promedio', ROUND(ls.ipnu_promedio::numeric, 2),
                                    'idot_promedio', ROUND(ls.idot_promedio::numeric, 2)
                                ),
                                'geometry', ST_AsGeoJSON(ST_Simplify(l.geom, 0.0005))::jsonb
                            )
                        )
                    ) as geojson
                FROM iug.localidad l
                JOIN localidad_stats ls ON l.id_localidad = ls.id_localidad
                """
            else:
                query = """
                SELECT
                    jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(
                            jsonb_build_object(
                                'type', 'Feature',
                                'properties', jsonb_build_object(
                                    'id', id_localidad,
                                    'nombre', nombre
                                ),
                                'geometry', ST_AsGeoJSON(ST_Simplify(geom, 0.0005))::jsonb
                            )
                        )
                    ) as geojson
                FROM iug.localidad
                """
                params = []

            result = await conn.fetchval(query, *params)

            if not result:
                return {
                    "type": "FeatureCollection",
                    "features": []
                }

            # Parse JSON string to return proper dict (avoid double-encoding)
            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result

            # Cachear resultado sólo en la consulta default (sin filtro)
            if use_cache:
                await cache_set(CACHE_KEY_LOCALIDADES, data, CACHE_TTL)
                logger.debug("Cache SET: localidades GeoJSON")

            return data

    except Exception as e:
        logger.error(f"Error obteniendo localidades GeoJSON: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo datos geográficos: {str(e)}")


@router.get("/localidades/{nombre}")
async def obtener_localidad_detalle(
    nombre: str,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene detalles y GeoJSON de una localidad específica.
    """
    try:
        async with db.acquire() as conn:
            # Usar id_localidad (foreign key indexado) en lugar de ST_Contains
            query = """
            WITH localidad_stats AS (
                SELECT
                    l.id_localidad,
                    l.nombre,
                    COUNT(i.id_inmueble) as inmuebles_count,
                    AVG(i.precio)::BIGINT as precio_promedio,
                    AVG(i.iurb) as iurb_promedio,
                    AVG(i.area) as area_promedio,
                    ST_AsGeoJSON(l.geom)::jsonb as geometry
                FROM iug.localidad l
                LEFT JOIN iug.inmueble i ON i.id_localidad = l.id_localidad
                WHERE LOWER(l.nombre) = LOWER($1)
                GROUP BY l.id_localidad, l.nombre, l.geom
            )
            SELECT * FROM localidad_stats
            """

            result = await conn.fetchrow(query, nombre)

            if not result:
                raise HTTPException(404, f"Localidad '{nombre}' no encontrada")

            return {
                "id_localidad": result['id_localidad'],
                "nombre": result['nombre'],
                "inmuebles_count": result['inmuebles_count'],
                "precio_promedio": result['precio_promedio'],
                "iurb_promedio": round(float(result['iurb_promedio']) if result['iurb_promedio'] else 0, 2),
                "area_promedio": round(float(result['area_promedio']) if result['area_promedio'] else 0, 2),
                "geometry": result['geometry']
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo localidad {nombre}: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo localidad: {str(e)}")


@router.get("/barrios")
async def obtener_barrios_geojson(
    localidad: Optional[str] = Query(None, description="Filtrar por nombre de localidad"),
    incluir_estadisticas: bool = Query(True, description="Incluir estadísticas de inmuebles"),
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar promedios por tipo de inmueble"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene GeoJSON de barrios de Bogotá con estadísticas opcionales.
    Puede filtrarse por localidad y/o por tipo de inmueble.
    Datos cacheados en Redis por 1 hora (sólo cuando no hay filtro de tipo).
    """
    # Whitelist de tipos válidos
    if tipo_inmueble and tipo_inmueble not in _TIPOS_INMUEBLE_VALIDOS:
        raise HTTPException(400, f"tipo_inmueble inválido. Opciones: {sorted(_TIPOS_INMUEBLE_VALIDOS)}")

    # Determinar cache key (sólo cuando no hay filtro de tipo)
    if localidad:
        cache_key = CACHE_KEY_BARRIOS_LOC + localidad.lower()
    else:
        cache_key = CACHE_KEY_BARRIOS_ALL

    use_cache = incluir_estadisticas and not tipo_inmueble
    if use_cache:
        cached = await cache_get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: barrios ({cache_key})")
            return cached

    try:
        async with db.acquire() as conn:
            # Construir filtro de localidad + tipo de inmueble.
            # Los placeholders se asignan dinámicamente para mantener parametrización segura.
            localidad_filter = ""
            params = []

            if localidad:
                params.append(localidad)
                localidad_filter = f"WHERE LOWER(l.nombre) = LOWER(${len(params)})"

            # Filtro adicional para el LEFT JOIN del inmueble (no para el WHERE general)
            tipo_inmueble_join = ""
            if tipo_inmueble:
                params.append(tipo_inmueble)
                tipo_inmueble_join = f" AND i.tipo_inmueble = ${len(params)}"

            if incluir_estadisticas:
                # Usar id_barrio (foreign key indexado) en lugar de ST_Contains (mucho más rápido)
                query = f"""
                WITH barrio_stats AS (
                    SELECT
                        b.id_barrio,
                        b.nombre,
                        b.codigo_upz,
                        b.area_total,
                        b.poblacion_estimada,
                        l.nombre as localidad,
                        l.id_localidad,
                        COUNT(i.id_inmueble) as inmuebles_count,
                        COALESCE(AVG(i.precio)::BIGINT, 0) as precio_promedio,
                        COALESCE(AVG(i.area), 0) as area_promedio,
                        COALESCE(AVG(i.iurb), 0) as iurb_promedio,
                        COALESCE(AVG(i.iacc), 0) as iacc_promedio,
                        COALESCE(AVG(i.iseg), 0) as iseg_promedio,
                        COALESCE(AVG(i.ihed), 0) as ihed_promedio,
                        COALESCE(AVG(i.ipnu), 0) as ipnu_promedio,
                        COALESCE(AVG(i.idot), 0) as idot_promedio
                    FROM iug.barrio b
                    LEFT JOIN iug.localidad l ON b.id_localidad = l.id_localidad
                    LEFT JOIN iug.inmueble i ON i.id_barrio = b.id_barrio{tipo_inmueble_join}
                    {localidad_filter}
                    GROUP BY b.id_barrio, b.nombre, b.codigo_upz, b.area_total,
                             b.poblacion_estimada, l.nombre, l.id_localidad
                )
                SELECT
                    jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', COALESCE(jsonb_agg(
                            jsonb_build_object(
                                'type', 'Feature',
                                'properties', jsonb_build_object(
                                    'id', bs.id_barrio,
                                    'nombre', bs.nombre,
                                    'localidad', bs.localidad,
                                    'id_localidad', bs.id_localidad,
                                    'codigo_upz', bs.codigo_upz,
                                    'area_total', bs.area_total,
                                    'poblacion_estimada', bs.poblacion_estimada,
                                    'inmuebles_count', bs.inmuebles_count,
                                    'precio_promedio', bs.precio_promedio,
                                    'area_promedio', ROUND(bs.area_promedio::numeric, 2),
                                    'iurb_promedio', ROUND(bs.iurb_promedio::numeric, 2),
                                    'iacc_promedio', ROUND(bs.iacc_promedio::numeric, 2),
                                    'iseg_promedio', ROUND(bs.iseg_promedio::numeric, 2),
                                    'ihed_promedio', ROUND(bs.ihed_promedio::numeric, 2),
                                    'ipnu_promedio', ROUND(bs.ipnu_promedio::numeric, 2),
                                    'idot_promedio', ROUND(bs.idot_promedio::numeric, 2)
                                ),
                                'geometry', ST_AsGeoJSON(ST_Simplify(b.geom, 0.0003))::jsonb
                            )
                        ) FILTER (WHERE b.geom IS NOT NULL), '[]'::jsonb)
                    ) as geojson
                FROM iug.barrio b
                JOIN barrio_stats bs ON b.id_barrio = bs.id_barrio
                """
            else:
                query = f"""
                SELECT
                    jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', COALESCE(jsonb_agg(
                            jsonb_build_object(
                                'type', 'Feature',
                                'properties', jsonb_build_object(
                                    'id', b.id_barrio,
                                    'nombre', b.nombre,
                                    'localidad', l.nombre,
                                    'id_localidad', l.id_localidad
                                ),
                                'geometry', ST_AsGeoJSON(ST_Simplify(b.geom, 0.0003))::jsonb
                            )
                        ) FILTER (WHERE b.geom IS NOT NULL), '[]'::jsonb)
                    ) as geojson
                FROM iug.barrio b
                LEFT JOIN iug.localidad l ON b.id_localidad = l.id_localidad
                {localidad_filter}
                """

            result = await conn.fetchval(query, *params)

            if not result:
                return {
                    "type": "FeatureCollection",
                    "features": []
                }

            # Parse JSON string to return proper dict (avoid double-encoding)
            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result

            # Cachear resultado (solo cuando es la consulta default sin filtro de tipo)
            if use_cache:
                await cache_set(cache_key, data, CACHE_TTL)
                logger.debug(f"Cache SET: barrios ({cache_key}), {len(data.get('features', []))} features")

            return data

    except Exception as e:
        logger.error(f"Error obteniendo barrios GeoJSON: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo datos geográficos: {str(e)}")


@router.get("/inmuebles/puntos")
async def obtener_inmuebles_puntos(
    limit: int = Query(100, ge=1, le=1000, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación"),
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar por tipo"),
    localidad: Optional[str] = Query(None, description="Filtrar por localidad"),
    sort_by: Optional[str] = Query(None, description="Ordenar por: iurb, ihed, iacc, iseg, ipnu, precio"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene puntos GeoJSON de inmuebles para visualización en mapa.

    Returns:
        GeoJSON FeatureCollection con puntos de inmuebles
    """
    try:
        async with db.acquire() as conn:
            # Construir filtros
            filters = ["i.geom IS NOT NULL"]
            params = []
            param_count = 1

            if tipo_inmueble:
                filters.append(f"i.tipo_inmueble = ${param_count}")
                params.append(tipo_inmueble)
                param_count += 1

            if localidad:
                # Usar id_localidad (foreign key) en lugar de ST_Contains
                filters.append(f"""
                    EXISTS (
                        SELECT 1 FROM iug.localidad l
                        WHERE LOWER(l.nombre) = LOWER(${param_count})
                        AND i.id_localidad = l.id_localidad
                    )
                """)
                params.append(localidad)
                param_count += 1

            where_clause = " AND ".join(filters)

            # Agregar limit y offset
            params.append(limit)
            params.append(offset)

            # Determinar ORDER BY
            allowed_sort = {'iurb', 'ihed', 'iacc', 'iseg', 'ipnu', 'precio'}
            if sort_by and sort_by in allowed_sort:
                order_clause = f"i.{sort_by} DESC NULLS LAST"
            else:
                order_clause = "i.id_inmueble"

            query = f"""
            SELECT
                jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_agg(
                        jsonb_build_object(
                            'type', 'Feature',
                            'properties', jsonb_build_object(
                                'id', i.id_inmueble,
                                'ubicacion', i.ubicacion,
                                'tipo_inmueble', i.tipo_inmueble,
                                'precio', i.precio,
                                'area', i.area,
                                'iurb', ROUND(i.iurb::numeric, 2),
                                'precio_por_iurb', ROUND(i.precio_por_iurb::numeric, 2)
                            ),
                            'geometry', ST_AsGeoJSON(i.geom)::jsonb
                        )
                    )
                ) as geojson
            FROM (
                SELECT * FROM iug.inmueble i
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ${param_count} OFFSET ${param_count + 1}
            ) i
            """

            result = await conn.fetchval(query, *params)

            if not result:
                return {
                    "type": "FeatureCollection",
                    "features": []
                }

            return result

    except Exception as e:
        logger.error(f"Error obteniendo puntos de inmuebles: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo puntos: {str(e)}")


@router.get("/dotaciones")
async def obtener_dotaciones_geojson(
    categoria: Optional[str] = Query(None, description="Categoría de dotación (ips, colegio, etc.)"),
    limit: int = Query(500, ge=1, le=5000),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene puntos GeoJSON de dotaciones (POIs) para capas del mapa.
    """
    try:
        async with db.acquire() as conn:
            params = [limit]
            where_clause = ""

            if categoria:
                where_clause = "WHERE categoria = $2"
                params.append(categoria)

            query = f"""
            SELECT
                jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_agg(
                        jsonb_build_object(
                            'type', 'Feature',
                            'properties', jsonb_build_object(
                                'id', id,
                                'nombre', nombre,
                                'categoria', categoria
                            ),
                            'geometry', ST_AsGeoJSON(geom)::jsonb
                        )
                    )
                ) as geojson
            FROM (
                SELECT * FROM iug.dotaciones_poi
                {where_clause}
                LIMIT $1
            ) d
            """

            result = await conn.fetchval(query, *params)

            if not result:
                return {
                    "type": "FeatureCollection",
                    "features": []
                }

            return result

    except Exception as e:
        logger.error(f"Error obteniendo dotaciones: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo dotaciones: {str(e)}")


@router.get("/indicadores/por-localidad")
async def obtener_indicadores_por_localidad(
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar por tipo de inmueble (Apartamento, Casa, Lote, etc.)"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene promedios de todos los indicadores agrupados por localidad.
    Opcionalmente filtrado por tipo de inmueble.
    """
    try:
        async with db.acquire() as conn:
            params = []
            tipo_filter = ""
            min_count = 50

            if tipo_inmueble:
                tipo_filter = "AND i.tipo_inmueble = $1"
                params.append(tipo_inmueble)
                min_count = 10

            query = f"""
            SELECT
                l.nombre as localidad,
                COUNT(i.id_inmueble) as inmuebles_count,
                ROUND(AVG(i.iurb)::numeric, 2) as iurb,
                ROUND(AVG(i.iacc)::numeric, 2) as iacc,
                ROUND(AVG(i.iseg)::numeric, 2) as iseg,
                ROUND(AVG(i.ihed)::numeric, 2) as ihed,
                ROUND(AVG(i.ipnu)::numeric, 2) as ipnu,
                ROUND(AVG(i.idot)::numeric, 2) as idot
            FROM iug.localidad l
            LEFT JOIN iug.inmueble i ON i.id_localidad = l.id_localidad {tipo_filter}
            GROUP BY l.id_localidad, l.nombre
            HAVING COUNT(i.id_inmueble) >= {min_count}
            ORDER BY l.nombre
            """

            results = await conn.fetch(query, *params)

            return [
                {
                    "localidad": row['localidad'],
                    "inmuebles_count": row['inmuebles_count'],
                    "indicadores": {
                        "iurb": float(row['iurb']) if row['iurb'] else 0,
                        "iacc": float(row['iacc']) if row['iacc'] else 0,
                        "iseg": float(row['iseg']) if row['iseg'] else 0,
                        "ihed": float(row['ihed']) if row['ihed'] else 0,
                        "ipnu": float(row['ipnu']) if row['ipnu'] else 0,
                        "idot": float(row['idot']) if row['idot'] else 0
                    }
                }
                for row in results
            ]

    except Exception as e:
        logger.error(f"Error obteniendo indicadores por localidad: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo indicadores: {str(e)}")


@router.get("/indicadores/por-barrio")
async def obtener_indicadores_por_barrio(
    localidad: Optional[str] = Query(None, description="Filtrar por localidad"),
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar por tipo de inmueble (Apartamento, Casa, Lote, etc.)"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene promedios de todos los indicadores agrupados por barrio.
    Opcionalmente filtrado por localidad y/o tipo de inmueble.
    """
    try:
        async with db.acquire() as conn:
            conditions = []
            params = []
            param_count = 1

            if localidad:
                conditions.append(f"""
                    EXISTS (
                        SELECT 1 FROM iug.localidad loc
                        WHERE LOWER(loc.nombre) = LOWER(${param_count})
                        AND b.id_localidad = loc.id_localidad
                    )
                """)
                params.append(localidad)
                param_count += 1

            tipo_filter = ""
            if tipo_inmueble:
                tipo_filter = f"AND i.tipo_inmueble = ${param_count}"
                params.append(tipo_inmueble)
                param_count += 1

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            min_count = 10 if tipo_inmueble else 50

            query = f"""
            SELECT
                b.nombre as barrio,
                l.nombre as localidad,
                COUNT(i.id_inmueble) as inmuebles_count,
                ROUND(AVG(i.iurb)::numeric, 2) as iurb,
                ROUND(AVG(i.iacc)::numeric, 2) as iacc,
                ROUND(AVG(i.iseg)::numeric, 2) as iseg,
                ROUND(AVG(i.ihed)::numeric, 2) as ihed,
                ROUND(AVG(i.ipnu)::numeric, 2) as ipnu,
                ROUND(AVG(i.idot)::numeric, 2) as idot
            FROM iug.barrio b
            LEFT JOIN iug.localidad l ON b.id_localidad = l.id_localidad
            LEFT JOIN iug.inmueble i ON i.id_barrio = b.id_barrio {tipo_filter}
            {where_clause}
            GROUP BY b.id_barrio, b.nombre, l.nombre
            HAVING COUNT(i.id_inmueble) >= {min_count}
            ORDER BY l.nombre, b.nombre
            """

            results = await conn.fetch(query, *params)

            return [
                {
                    "barrio": row['barrio'],
                    "localidad": row['localidad'],
                    "inmuebles_count": row['inmuebles_count'],
                    "indicadores": {
                        "iurb": float(row['iurb']) if row['iurb'] else 0,
                        "iacc": float(row['iacc']) if row['iacc'] else 0,
                        "iseg": float(row['iseg']) if row['iseg'] else 0,
                        "ihed": float(row['ihed']) if row['ihed'] else 0,
                        "ipnu": float(row['ipnu']) if row['ipnu'] else 0,
                        "idot": float(row['idot']) if row['idot'] else 0
                    }
                }
                for row in results
            ]

    except Exception as e:
        logger.error(f"Error obteniendo indicadores por barrio: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo indicadores: {str(e)}")


@router.get("/categorias-dotaciones")
async def obtener_categorias_dotaciones(
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Lista todas las categorías de dotaciones disponibles.
    """
    try:
        async with db.acquire() as conn:
            query = """
            SELECT DISTINCT categoria, COUNT(*) as count
            FROM iug.dotaciones_poi
            GROUP BY categoria
            ORDER BY count DESC
            """

            results = await conn.fetch(query)

            return [
                {
                    "categoria": row['categoria'],
                    "count": row['count']
                }
                for row in results
            ]

    except Exception as e:
        logger.error(f"Error obteniendo categorías: {e}", exc_info=True)
        raise HTTPException(500, f"Error obteniendo categorías: {str(e)}")


# ─── Capas POI puntuales / poligonales para los toggles del mapa ──────
# Whitelist explícita: el cliente sólo puede pedir capas que estén aquí.
# Cada entrada describe la consulta SQL idempotente que devuelve geometría
# + atributos para pintar el marker / el polígono en Leaflet.
#
# `requires_auth: True` señala capas premium. El endpoint las protege
# detrás de un usuario autenticado (vía Depends(get_current_user)).
_CAPAS_PERMITIDAS = {
    # ── Capas públicas (sin login) ─────────────────
    "transmilenio": {
        "sql": (
            "SELECT id_estacion AS id, nombre, geom "
            "FROM iug.estacion_transmilenio "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Point",
        "requires_auth": False,
    },
    "cai": {
        "sql": (
            "SELECT id_cai AS id, nombre, geom "
            "FROM iug.cai_policia "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Point",
        "requires_auth": False,
    },

    # ── Capas premium (requieren autenticación) ─────────────────
    "ips": {
        "sql": (
            "SELECT id AS id, nombre, geom "
            "FROM iug.dotaciones_poi "
            "WHERE categoria = 'ips' AND geom IS NOT NULL"
        ),
        "geom_type": "Point",
        "requires_auth": True,
    },
    "farmacias": {
        # Hay 8.129 farmacias — limitamos a 800 muestreadas espacialmente
        # para no saturar el navegador. PostGIS no tiene LIMIT semántico
        # de muestreo, así que usamos ORDER BY hashtext + ctid.
        "sql": (
            "SELECT id AS id, nombre, geom "
            "FROM iug.dotaciones_poi "
            "WHERE categoria = 'farmacia' AND geom IS NOT NULL "
            "ORDER BY id LIMIT 800"
        ),
        "geom_type": "Point",
        "requires_auth": True,
    },
    "centros_comerciales": {
        "sql": (
            "SELECT id AS id, nombre, geom "
            "FROM iug.dotaciones_poi "
            "WHERE categoria = 'centro_comercial' AND geom IS NOT NULL"
        ),
        "geom_type": "Point",
        "requires_auth": True,
    },
    "bibliotecas": {
        "sql": (
            "SELECT id AS id, nombre, geom "
            "FROM iug.dotaciones_poi "
            "WHERE categoria = 'biblioteca' AND geom IS NOT NULL"
        ),
        "geom_type": "Point",
        "requires_auth": True,
    },
    "sectores_priorizados": {
        # Polígonos de sectores priorizados de la Sec. de Seguridad
        "sql": (
            "SELECT id_sector AS id, nombre, geom "
            "FROM iug.sector_priorizado "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Polygon",
        "requires_auth": True,
    },
    "pot_tratamiento": {
        # POT 555 — tratamientos urbanísticos (renovación, consolidación, …).
        # 5.703 polígonos: simplificamos geometría server-side para evitar
        # saturar el frontend.
        "sql": (
            "SELECT id_tratamiento AS id, "
            "       COALESCE(nombre, codigo) AS nombre, "
            "       ST_Simplify(geom, 0.0002) AS geom "
            "FROM iug.pot_tratamiento "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Polygon",
        "requires_auth": True,
    },
    "pot_edificabilidad": {
        # POT 555 — alturas permitidas. 2.748 polígonos.
        "sql": (
            "SELECT id_edificabilidad AS id, "
            "       COALESCE(rango, codigo) AS nombre, "
            "       ST_Simplify(geom, 0.0002) AS geom "
            "FROM iug.pot_edificabilidad "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Polygon",
        "requires_auth": True,
    },
    "pot_areas_actividad": {
        # POT 555 — uso del suelo (residencial, mixto, comercial). 1.135 polígonos.
        "sql": (
            "SELECT id_area AS id, "
            "       COALESCE(nombre, codigo) AS nombre, "
            "       ST_Simplify(geom, 0.0002) AS geom "
            "FROM iug.pot_area_actividad "
            "WHERE geom IS NOT NULL"
        ),
        "geom_type": "Polygon",
        "requires_auth": True,
    },
}


@router.get("/capas")
async def listar_capas():
    """
    Devuelve el catálogo de capas POI disponibles. Cada capa indica si
    requiere autenticación. El frontend usa esto para pintar candados
    sobre las capas premium en la landing pública.
    """
    return [
        {
            "key": k,
            "requires_auth": v.get("requires_auth", False),
            "geom_type": v.get("geom_type", "Point"),
        }
        for k, v in _CAPAS_PERMITIDAS.items()
    ]


@router.get("/capa/{nombre}")
async def obtener_capa_geojson(
    nombre: str,
    request: Request,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    GeoJSON de capas POI para los toggles del mapa.
    Capas públicas: transmilenio, cai.
    Capas premium (requieren login): ips, farmacias, centros_comerciales,
    bibliotecas, sectores_priorizados.
    """
    capa = _CAPAS_PERMITIDAS.get(nombre)
    if not capa:
        raise HTTPException(
            404,
            f"Capa '{nombre}' no permitida. Disponibles: {list(_CAPAS_PERMITIDAS)}",
        )

    # Capas premium: validamos token JWT manualmente (no usamos Depends
    # para que el listado no requiera login pero los datos sí).
    if capa.get("requires_auth"):
        from services.auth_service import decode_token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(401, "Capa premium: requiere iniciar sesión")
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            if payload.get("type") not in (None, "access"):
                raise HTTPException(401, "Token inválido para esta capa")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "Token inválido o expirado")

    try:
        async with db.acquire() as conn:
            query = f"""
            SELECT jsonb_build_object(
                'type', 'FeatureCollection',
                'features', COALESCE(jsonb_agg(
                    jsonb_build_object(
                        'type', 'Feature',
                        'properties', jsonb_build_object(
                            'id', id,
                            'nombre', nombre
                        ),
                        'geometry', ST_AsGeoJSON(geom)::jsonb
                    )
                ), '[]'::jsonb)
            ) AS geojson
            FROM ({capa['sql']}) src
            """
            result = await conn.fetchval(query)
            if not result:
                return {"type": "FeatureCollection", "features": []}
            # asyncpg devuelve jsonb como str — lo parseamos para que
            # FastAPI lo serialice como objeto y no como string escapado.
            if isinstance(result, str):
                import json as _json
                return _json.loads(result)
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error obteniendo capa %s: %s", nombre, e, exc_info=True)
        raise HTTPException(500, f"Error obteniendo capa {nombre}")


@router.on_event("startup")
async def startup_geo():
    """Limpiar cache geo al arrancar para evitar datos obsoletos."""
    deleted = await cache_delete("geo:*")
    if deleted:
        logger.info(f"Cache geo limpiado al arrancar: {deleted} claves eliminadas")


@router.post("/cache/invalidar")
async def invalidar_cache_geo():
    """Limpia manualmente todo el cache de datos geográficos."""
    deleted = await cache_delete("geo:*")
    return {"message": f"Cache geo invalidado: {deleted} claves eliminadas"}
