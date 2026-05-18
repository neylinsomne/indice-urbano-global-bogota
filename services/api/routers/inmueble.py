"""
Router de Inmuebles - CRUD completo

Endpoints:
- GET /inmueble/buscar: Búsqueda normal con filtros
- GET /inmueble/{id}: Obtener inmueble por ID
- POST /inmueble: Insertar inmueble manual
- PUT /inmueble/{id}: Actualizar inmueble
- DELETE /inmueble/{id}: Eliminar inmueble
- GET /inmueble/tipos: Obtener tipos disponibles
- GET /inmueble/estadisticas: Estadísticas generales
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, validator
from datetime import datetime
import asyncpg
from enum import Enum

from db.postgre import get_db_pool
from services.auth_service import require_admin

router = APIRouter(prefix="/inmueble", tags=["inmuebles"])


# ============================================
# Modelos Pydantic
# ============================================

class TipoInmueble(str, Enum):
    """Tipos de inmueble soportados"""
    apartamento = "Apartamento"
    casa = "Casa"
    local = "Local"
    oficina = "Oficina"
    bodega = "Bodega"
    lote = "Lote"
    finca = "Finca"


class TipoOperacion(str, Enum):
    """Tipo de operación"""
    venta = "Venta"
    arriendo = "Arriendo"


class InmuebleCreate(BaseModel):
    """Modelo para crear inmueble"""
    tipo_inmueble: TipoInmueble
    tipo_operacion: TipoOperacion
    precio: float = Field(..., gt=0, description="Precio en pesos colombianos")
    ubicacion: str = Field(..., min_length=10, max_length=500)
    area: Optional[float] = Field(None, gt=0, description="Área en m²")
    habitaciones: Optional[int] = Field(None, ge=0, le=20)
    banos: Optional[int] = Field(None, ge=0, le=10)
    garajes: Optional[int] = Field(None, ge=0, le=10)
    estrato: Optional[int] = Field(None, ge=1, le=6)
    antiguedad: Optional[int] = Field(None, ge=0)
    piso: Optional[int] = Field(None, ge=-3, le=100)
    administracion: Optional[float] = Field(None, ge=0)

    # Coordenadas (requeridas para calcular indicadores)
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)

    # Características adicionales
    ascensor: Optional[bool] = None
    conjunto_cerrado: Optional[bool] = None
    vigilancia: Optional[bool] = None
    piscina: Optional[bool] = None
    gym: Optional[bool] = None
    salon_social: Optional[bool] = None
    zona_bbq: Optional[bool] = None
    cancha_deportiva: Optional[bool] = None

    # Metadata
    descripcion: Optional[str] = Field(None, max_length=2000)
    url_inmueble: Optional[str] = Field(None, max_length=500)
    nombre_contacto: Optional[str] = Field(None, max_length=200)
    telefono_contacto: Optional[str] = Field(None, max_length=50)

    @validator('precio')
    def validate_precio(cls, v):
        if v < 10000000:  # Mínimo 10M COP
            raise ValueError('Precio mínimo: 10.000.000 COP')
        if v > 100000000000:  # Máximo 100.000M COP
            raise ValueError('Precio máximo: 100.000.000.000 COP')
        return v


class InmuebleUpdate(BaseModel):
    """Modelo para actualizar inmueble (todos los campos opcionales)"""
    precio: Optional[float] = Field(None, gt=0)
    ubicacion: Optional[str] = None
    area: Optional[float] = Field(None, gt=0)
    habitaciones: Optional[int] = Field(None, ge=0, le=20)
    banos: Optional[int] = Field(None, ge=0, le=10)
    garajes: Optional[int] = Field(None, ge=0, le=10)
    descripcion: Optional[str] = None
    url_inmueble: Optional[str] = None
    nombre_contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None


class InmuebleResponse(BaseModel):
    """Respuesta de inmueble con indicadores"""
    id_inmueble: int
    tipo_inmueble: str
    tipo_operacion: str
    precio: float
    ubicacion: str
    area: Optional[float]
    habitaciones: Optional[int]
    banos: Optional[int]

    # Indicadores
    iurb: Optional[float]
    iacc: Optional[float]
    iseg: Optional[float]
    ihed: Optional[float]
    ipnu: Optional[float]

    # Análisis
    precio_por_iurb: Optional[float]
    precio_m2: Optional[float]

    # Metadata
    fecha_publicacion: Optional[datetime]
    fuente: Optional[str]


class BusquedaFiltros(BaseModel):
    """Filtros para búsqueda normal"""
    tipo_inmueble: Optional[TipoInmueble] = None
    tipo_operacion: Optional[TipoOperacion] = None

    precio_min: Optional[float] = Field(None, ge=0)
    precio_max: Optional[float] = Field(None, ge=0)

    area_min: Optional[float] = Field(None, ge=0)
    area_max: Optional[float] = Field(None, ge=0)

    habitaciones_min: Optional[int] = Field(None, ge=0)
    habitaciones_max: Optional[int] = Field(None, ge=0, le=20)

    banos_min: Optional[int] = Field(None, ge=0)

    # Indicadores
    iurb_min: Optional[float] = Field(None, ge=0, le=5)
    iacc_min: Optional[float] = Field(None, ge=0, le=5)
    iseg_min: Optional[float] = Field(None, ge=0, le=5)

    # Ubicación
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)
    radio_metros: Optional[int] = Field(None, ge=100, le=50000)

    # Ordenamiento
    ordenar_por: str = Field("fecha_publicacion", pattern="^(precio|area|iurb|fecha_publicacion|precio_por_iurb)$")
    orden: str = Field("desc", pattern="^(asc|desc)$")

    # Paginación
    limite: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


# ============================================
# Endpoints
# ============================================

@router.get("/buscar", response_model=List[InmuebleResponse])
async def buscar_inmuebles(
    tipo_inmueble: Optional[str] = Query(None),
    tipo_operacion: Optional[str] = Query(None),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
    area_min: Optional[float] = Query(None, ge=0),
    area_max: Optional[float] = Query(None, ge=0),
    habitaciones_min: Optional[int] = Query(None, ge=0),
    banos_min: Optional[int] = Query(None, ge=0),
    iurb_min: Optional[float] = Query(None, ge=0, le=5),
    iacc_min: Optional[float] = Query(None, ge=0, le=5),
    iseg_min: Optional[float] = Query(None, ge=0, le=5),
    latitud: Optional[float] = Query(None, ge=-90, le=90),
    longitud: Optional[float] = Query(None, ge=-180, le=180),
    radio_metros: int = Query(5000, ge=100, le=50000),
    ordenar_por: str = Query("fecha_publicacion", regex="^(precio|area|iurb|fecha_publicacion|precio_por_iurb)$"),
    orden: str = Query("desc", regex="^(asc|desc)$"),
    limite: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Búsqueda normal de inmuebles con filtros estándar

    Filtros disponibles:
    - Tipo de inmueble y operación
    - Rango de precio
    - Área, habitaciones, baños
    - Indicadores mínimos (I_URB, I_ACC, I_SEG)
    - Ubicación (radio desde coordenadas)

    Ordenamiento:
    - precio, area, iurb, fecha_publicacion, precio_por_iurb
    - asc (ascendente) o desc (descendente)
    """
    # Construir query dinámica
    where_clauses = []
    params = []
    param_count = 0

    # Filtros básicos
    if tipo_inmueble:
        param_count += 1
        where_clauses.append(f"tipo_inmueble = ${param_count}")
        params.append(tipo_inmueble)

    if tipo_operacion:
        param_count += 1
        where_clauses.append(f"tipo_operacion = ${param_count}")
        params.append(tipo_operacion)

    if precio_min:
        param_count += 1
        where_clauses.append(f"precio >= ${param_count}")
        params.append(precio_min)

    if precio_max:
        param_count += 1
        where_clauses.append(f"precio <= ${param_count}")
        params.append(precio_max)

    if area_min:
        param_count += 1
        where_clauses.append(f"area >= ${param_count}")
        params.append(area_min)

    if area_max:
        param_count += 1
        where_clauses.append(f"area <= ${param_count}")
        params.append(area_max)

    if habitaciones_min:
        param_count += 1
        where_clauses.append(f"habitaciones >= ${param_count}")
        params.append(habitaciones_min)

    if banos_min:
        param_count += 1
        where_clauses.append(f"banos >= ${param_count}")
        params.append(banos_min)

    # Filtros de indicadores
    if iurb_min:
        param_count += 1
        where_clauses.append(f"iurb >= ${param_count}")
        params.append(iurb_min)

    if iacc_min:
        param_count += 1
        where_clauses.append(f"iacc >= ${param_count}")
        params.append(iacc_min)

    if iseg_min:
        param_count += 1
        where_clauses.append(f"iseg >= ${param_count}")
        params.append(iseg_min)

    # Filtro geográfico
    if latitud is not None and longitud is not None:
        param_count += 1
        point_param = param_count
        param_count += 1
        radius_param = param_count

        where_clauses.append(f"""
            ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_Point(${point_param}, ${point_param + 1}), 4326)::geography,
                ${radius_param}
            )
        """)
        params.extend([longitud, latitud, radio_metros])
        param_count += 1  # Ya usamos 2 params extra

    # Excluir outliers
    where_clauses.append("is_outlier = FALSE")

    # Query base
    where_sql = " AND ".join(where_clauses)

    # Validar ordenamiento
    valid_order_by = {
        'precio': 'precio',
        'area': 'area',
        'iurb': 'iurb',
        'fecha_publicacion': 'fecha_publicacion',
        'precio_por_iurb': 'precio_por_iurb'
    }
    order_col = valid_order_by.get(ordenar_por, 'fecha_publicacion')
    order_dir = 'ASC' if orden == 'asc' else 'DESC'

    query = f"""
        SELECT
            id_inmueble,
            tipo_inmueble,
            tipo_operacion,
            precio,
            ubicacion,
            area,
            habitaciones,
            banos,
            ROUND(iurb::numeric, 2) as iurb,
            ROUND(iacc::numeric, 2) as iacc,
            ROUND(iseg::numeric, 2) as iseg,
            ROUND(ihed::numeric, 2) as ihed,
            ROUND(ipnu::numeric, 2) as ipnu,
            ROUND(precio_por_iurb::numeric, 2) as precio_por_iurb,
            ROUND((precio / NULLIF(area, 0))::numeric, 0) as precio_m2,
            fecha_publicacion,
            fuente
        FROM iug.inmueble
        WHERE {where_sql}
        ORDER BY {order_col} {order_dir}
        LIMIT ${param_count + 1}
        OFFSET ${param_count + 2}
    """

    params.extend([limite, offset])

    async with db.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [dict(row) for row in rows]


@router.get("/{id_inmueble}")
async def obtener_inmueble(
    id_inmueble: int,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """Obtiene un inmueble específico por ID con detalle completo"""
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                i.id_inmueble,
                i.tipo_inmueble,
                i.tipo_operacion,
                i.precio,
                i.ubicacion,
                i.area,
                i.habitaciones,
                i.banos,
                i.garajes,
                i.estrato,
                i.descripcion,
                i.image,
                ST_Y(i.geom) as latitud,
                ST_X(i.geom) as longitud,
                ROUND(i.iurb::numeric, 2) as iurb,
                ROUND(i.iacc::numeric, 2) as iacc,
                ROUND(i.iseg::numeric, 2) as iseg,
                ROUND(i.ihed::numeric, 2) as ihed,
                ROUND(i.ipnu::numeric, 2) as ipnu,
                ROUND(i.idot::numeric, 2) as idot,
                ROUND(i.precio_por_iurb::numeric, 2) as precio_por_iurb,
                ROUND((i.precio / NULLIF(i.area, 0))::numeric, 0) as precio_m2,
                i.fecha_publicacion,
                i.fuente,
                l.nombre as nombre_localidad,
                b.nombre as nombre_barrio
            FROM iug.inmueble i
            LEFT JOIN iug.localidad l ON i.id_localidad = l.id_localidad
            LEFT JOIN iug.barrio b ON i.id_barrio = b.id_barrio
            WHERE i.id_inmueble = $1
        """, id_inmueble)

    if not row:
        raise HTTPException(404, f"Inmueble {id_inmueble} no encontrado")

    result = dict(row)

    # Obtener características del inmueble
    async with db.acquire() as conn:
        caract_rows = await conn.fetch("""
            SELECT nombre, valor_bool
            FROM iug.inmueble_caracteristica
            WHERE id_inmueble = $1 AND valor_bool = TRUE
            ORDER BY nombre
        """, id_inmueble)
        result['caracteristicas'] = [r['nombre'] for r in caract_rows]

    return result


@router.get("/{id_inmueble}/pois-cercanos")
async def obtener_pois_cercanos(
    id_inmueble: int,
    radio: int = Query(1000, ge=100, le=5000, description="Radio en metros"),
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Obtiene POIs cercanos a un inmueble dentro de un radio dado.
    Incluye dotaciones (salud, educación, recreación, etc.) y estaciones de transporte.
    """
    async with db.acquire() as conn:
        # Verificar que el inmueble existe y tiene geometría
        inmueble = await conn.fetchrow("""
            SELECT ST_Y(geom) as lat, ST_X(geom) as lng
            FROM iug.inmueble
            WHERE id_inmueble = $1 AND geom IS NOT NULL
        """, id_inmueble)

        if not inmueble:
            raise HTTPException(404, f"Inmueble {id_inmueble} no encontrado o sin coordenadas")

        # Dotaciones cercanas
        dotaciones = await conn.fetch("""
            SELECT
                d.id,
                d.nombre,
                d.categoria,
                ST_Y(d.geom) as latitud,
                ST_X(d.geom) as longitud,
                ROUND(ST_Distance(d.geom::geography, i.geom::geography)::numeric, 0) as distancia_m
            FROM iug.dotaciones_poi d, iug.inmueble i
            WHERE i.id_inmueble = $1
              AND d.geom IS NOT NULL
              AND ST_DWithin(d.geom::geography, i.geom::geography, $2)
            ORDER BY d.categoria, distancia_m
        """, id_inmueble, radio)

        # Estaciones de TransMilenio cercanas
        transmilenio = await conn.fetch("""
            SELECT
                e.id_estacion as id,
                e.nombre,
                'transmilenio' as categoria,
                ST_Y(e.geom) as latitud,
                ST_X(e.geom) as longitud,
                ROUND(ST_Distance(e.geom::geography, i.geom::geography)::numeric, 0) as distancia_m
            FROM iug.estacion_transmilenio e, iug.inmueble i
            WHERE i.id_inmueble = $1
              AND e.geom IS NOT NULL
              AND ST_DWithin(e.geom::geography, i.geom::geography, $2)
            ORDER BY distancia_m
        """, id_inmueble, radio)

    # Combinar resultados
    pois = [dict(r) for r in dotaciones] + [dict(r) for r in transmilenio]

    # Agrupar por categoría para el resumen
    resumen = {}
    for poi in pois:
        cat = poi['categoria']
        if cat not in resumen:
            resumen[cat] = 0
        resumen[cat] += 1

    return {
        "inmueble": {"lat": float(inmueble['lat']), "lng": float(inmueble['lng'])},
        "radio": radio,
        "total": len(pois),
        "resumen": resumen,
        "pois": pois
    }


@router.post("/", response_model=InmuebleResponse, status_code=201)
async def crear_inmueble(
    inmueble: InmuebleCreate,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Crea un inmueble manualmente

    Los indicadores (I_URB, I_ACC, etc.) se calculan automáticamente mediante triggers.
    """
    async with db.acquire() as conn:
        # Insertar inmueble
        row = await conn.fetchrow("""
            INSERT INTO iug.inmueble (
                tipo_inmueble,
                tipo_operacion,
                precio,
                ubicacion,
                area,
                habitaciones,
                banos,
                garajes,
                estrato,
                antiguedad,
                piso,
                administracion,
                ascensor,
                conjunto_cerrado,
                vigilancia,
                piscina,
                gym,
                salon_social,
                zona_bbq,
                cancha_deportiva,
                descripcion,
                url_inmueble,
                nombre_contacto,
                telefono_contacto,
                geom,
                fuente,
                fecha_publicacion
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24,
                ST_SetSRID(ST_Point($25, $26), 4326),
                'manual',
                NOW()
            )
            RETURNING
                id_inmueble,
                tipo_inmueble,
                tipo_operacion,
                precio,
                ubicacion,
                area,
                habitaciones,
                banos,
                iurb,
                iacc,
                iseg,
                ihed,
                ipnu,
                precio_por_iurb,
                fecha_publicacion,
                fuente
        """,
            inmueble.tipo_inmueble.value,
            inmueble.tipo_operacion.value,
            inmueble.precio,
            inmueble.ubicacion,
            inmueble.area,
            inmueble.habitaciones,
            inmueble.banos,
            inmueble.garajes,
            inmueble.estrato,
            inmueble.antiguedad,
            inmueble.piso,
            inmueble.administracion,
            inmueble.ascensor,
            inmueble.conjunto_cerrado,
            inmueble.vigilancia,
            inmueble.piscina,
            inmueble.gym,
            inmueble.salon_social,
            inmueble.zona_bbq,
            inmueble.cancha_deportiva,
            inmueble.descripcion,
            inmueble.url_inmueble,
            inmueble.nombre_contacto,
            inmueble.telefono_contacto,
            inmueble.longitud,
            inmueble.latitud
        )

    result = dict(row)
    result['precio_m2'] = round(result['precio'] / result['area'], 0) if result.get('area') else None

    return result


@router.put("/{id_inmueble}", response_model=InmuebleResponse)
async def actualizar_inmueble(
    id_inmueble: int,
    inmueble: InmuebleUpdate,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Actualiza un inmueble existente (solo campos proporcionados)"""
    # Construir SET clauses dinámicamente
    updates = []
    params = [id_inmueble]
    param_count = 1

    update_dict = inmueble.dict(exclude_unset=True)

    for field, value in update_dict.items():
        if value is not None:
            param_count += 1
            updates.append(f"{field} = ${param_count}")
            params.append(value)

    if not updates:
        raise HTTPException(400, "No hay campos para actualizar")

    set_clause = ", ".join(updates)

    async with db.acquire() as conn:
        row = await conn.fetchrow(f"""
            UPDATE iug.inmueble
            SET {set_clause}
            WHERE id_inmueble = $1
            RETURNING
                id_inmueble,
                tipo_inmueble,
                tipo_operacion,
                precio,
                ubicacion,
                area,
                habitaciones,
                banos,
                iurb,
                iacc,
                iseg,
                ihed,
                ipnu,
                precio_por_iurb,
                fecha_publicacion,
                fuente
        """, *params)

    if not row:
        raise HTTPException(404, f"Inmueble {id_inmueble} no encontrado")

    result = dict(row)
    result['precio_m2'] = round(result['precio'] / result['area'], 0) if result.get('area') else None

    return result


@router.delete("/{id_inmueble}")
async def eliminar_inmueble(
    id_inmueble: int,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Elimina un inmueble"""
    async with db.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM iug.inmueble WHERE id_inmueble = $1",
            id_inmueble
        )

    if result == "DELETE 0":
        raise HTTPException(404, f"Inmueble {id_inmueble} no encontrado")

    return {"message": f"Inmueble {id_inmueble} eliminado exitosamente"}


@router.get("/tipos/disponibles")
async def obtener_tipos():
    """Obtiene tipos de inmuebles y operaciones disponibles"""
    return {
        "tipos_inmueble": [t.value for t in TipoInmueble],
        "tipos_operacion": [t.value for t in TipoOperacion]
    }


@router.get("/estadisticas/generales")
async def estadisticas_generales(
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Estadísticas generales de inmuebles.

    `total` cuenta sólo inmuebles del alcance del estudio (bogotanos con
    iurb computado). `total_multiciudad` incluye Medellín/Cali/Barranquilla
    que están en la BD pero fuera del alcance del IUG.
    También incluye los conteos de localidades y barrios para el frontend.
    """
    async with db.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE iurb IS NOT NULL) as total,
                COUNT(*) as total_multiciudad,
                COUNT(DISTINCT tipo_inmueble) FILTER (WHERE iurb IS NOT NULL) as tipos_unicos,
                ROUND(AVG(precio) FILTER (WHERE iurb IS NOT NULL)::numeric, 0) as precio_promedio,
                ROUND(AVG(area) FILTER (WHERE iurb IS NOT NULL)::numeric, 1) as area_promedio,
                ROUND(AVG(iurb)::numeric, 2) as iurb_promedio,
                MIN(precio) FILTER (WHERE iurb IS NOT NULL) as precio_min,
                MAX(precio) FILTER (WHERE iurb IS NOT NULL) as precio_max
            FROM iug.inmueble
            WHERE is_outlier = FALSE
        """)

        # Por tipo (sólo alcance bogotano)
        por_tipo = await conn.fetch("""
            SELECT
                tipo_inmueble,
                COUNT(*) as cantidad,
                ROUND(AVG(precio)::numeric, 0) as precio_promedio
            FROM iug.inmueble
            WHERE is_outlier = FALSE AND iurb IS NOT NULL
            GROUP BY tipo_inmueble
            ORDER BY cantidad DESC
        """)

        # Conteos auxiliares para el frontend
        total_localidades = await conn.fetchval(
            "SELECT COUNT(*) FROM iug.localidad"
        )
        total_barrios = await conn.fetchval(
            "SELECT COUNT(*) FROM iug.barrio WHERE geom IS NOT NULL"
        )

    response = {
        "generales": dict(stats),
        "por_tipo": [dict(row) for row in por_tipo],
        # Compatibilidad con el frontend que lee total_inmuebles / total_localidades
        # / total_barrios directamente del root del objeto.
        "total_inmuebles": stats["total"],
        "total_inmuebles_multiciudad": stats["total_multiciudad"],
        "total_localidades": total_localidades,
        "total_barrios": total_barrios,
    }
    return response
