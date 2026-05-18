"""
Servicio de migración MongoDB → PostgreSQL.

Ejecuta la migración de documentos desde MongoDB Atlas hacia PostgreSQL
usando la función f_upsert_inmueble. Diseñado para ejecutarse dentro
del pipeline automático post-scraping.
"""
import json
import logging
import math
import os
import re
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    logger.warning("MONGO_URI no configurado — migración MongoDB deshabilitada")

# Collections que se migran automáticamente
_CIUDADES = ["bogota", "medellin", "cali", "barranquilla", "cajica", "chia", "madrid"]
_TIPOS_COL = ["apartamentos", "casas", "locales", "lotes", "bodegas", "fincas", "parqueadero", "inmuebles"]
_TXS = ["venta", "arriendo"]

COLLECTIONS = []
for ciudad in _CIUDADES:
    for tipo in _TIPOS_COL:
        for tx in _TXS:
            COLLECTIONS.append((ciudad, f"{tipo}_{tx}", "finca_raiz"))

# Colecciones legacy de bogota
COLLECTIONS.append(("bogota", "locales_venta", "finca_raiz_legacy"))
COLLECTIONS.append(("bogota", "inmuebles_venta", "finca_raiz_legacy"))
# Habi
COLLECTIONS.append(("Real_state_tesis", "habi_newera", "habi"))
# Nuevas fuentes
COLLECTIONS.append(("properati", "properati_raw", "properati"))
COLLECTIONS.append(("bancolombia_reo", "reo_raw", "bancolombia_reo"))
COLLECTIONS.append(("sae", "sae_raw", "sae"))
for _cc_ciudad in _CIUDADES:
    for _cc_tipo in _TIPOS_COL:
        for _cc_tx in _TXS:
            COLLECTIONS.append(("ciencuadras", f"{_cc_ciudad}_{_cc_tipo}_{_cc_tx}", "ciencuadras"))
# Antioquia legacy
COLLECTIONS.append(("antioquia", "casas_venta", "finca_raiz"))


# ── Utilidades de normalización ────────────────────────────────

def _clean_nan(obj):
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _safe_int(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return int(val)
    if isinstance(val, str):
        m = re.search(r'\d+', val)
        return int(m.group()) if m else None
    return None


def _safe_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return float(val)
    if isinstance(val, str):
        cleaned = val.lower().replace('m²', '').replace('m2', '').replace(',', '.').strip()
        m = re.search(r'[\d.]+', cleaned)
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass
    return None


def _safe_coord(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _safe_precio(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return int(val)
    if isinstance(val, str):
        cleaned = val.replace('$', '').replace(' ', '').replace('.', '').replace(',', '')
        m = re.search(r'\d+', cleaned)
        if m:
            return int(m.group())
    return None


def _safe_estrato(val):
    v = _safe_int(val)
    return v if v is not None and 1 <= v <= 6 else None


TIPO_MAP = {
    'apartamento': 'Apartamento', 'apto': 'Apartamento',
    'apartaestudio': 'Apartaestudio',
    'casa': 'Casa', 'ph': 'PH', 'penthouse': 'PH',
    'lote': 'Lote', 'terreno': 'Lote',
    'bodega': 'Bodega', 'local': 'Local',
    'oficina': 'Oficina', 'finca': 'Finca',
    'parqueadero': 'Parqueadero', 'inmueble': 'Inmueble',
}

# Mapeo nombre de colección MongoDB → tipo_inmueble
COLL_TIPO_MAP = {
    'apartamentos': 'Apartamento',
    'casas': 'Casa',
    'locales': 'Local',
    'lotes': 'Lote',
    'bodegas': 'Bodega',
    'fincas': 'Finca',
    'parqueadero': 'Parqueadero',
    'inmuebles': 'Inmueble',
    'habi_newera': 'Apartamento',
}


def _tipo_from_collection(coll_name: str) -> str | None:
    """Extrae tipo_inmueble del nombre de la colección MongoDB."""
    prefix = coll_name.split('_')[0]
    return COLL_TIPO_MAP.get(prefix, COLL_TIPO_MAP.get(coll_name))


def _normalize_tipo(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    low = val_str.lower()
    for key, norm in TIPO_MAP.items():
        if key in low:
            return norm
    return val_str.title()


# ── Normalizadores por formato ────────────────────────────────

def _normalize_finca_raiz(doc):
    return {
        'pagina': doc.get('pagina', 'finca_raiz'),
        'codigo_fuente': str(doc.get('codigo_fr', '')),
        'precio': _safe_precio(doc.get('precio')),
        'area_construida': _safe_float(doc.get('area_construida')),
        'habitaciones': _safe_int(doc.get('habitaciones')),
        'banos': _safe_int(doc.get('banos')),
        'garajes': _safe_int(doc.get('garajes') or doc.get('parqueaderos')),
        'estrato': _safe_estrato(doc.get('estrato')),
        'tipo_inmueble': _normalize_tipo(doc.get('tipo_de_inmueble') or doc.get('tipo_inmueble')),
        'ubicacion': doc.get('ubicacion'),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('latitud') or doc.get('lat')),
        'lon': _safe_coord(doc.get('longitud') or doc.get('lon')),
        'image': doc.get('image'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': doc.get('inmobiliaria'),
        'proyecto': doc.get('proyecto', False),
        'caracteristicas': doc.get('caracteristicas', []),
    }


def _normalize_finca_legacy(doc):
    area = (
        _safe_float(doc.get('area_construida'))
        or _safe_float(doc.get('Área Construida'))
        or _safe_float(doc.get('area'))
    )
    estrato = _safe_estrato(doc.get('estrato')) or _safe_estrato(doc.get('Estrato'))
    banos = _safe_int(doc.get('banos')) or _safe_int(doc.get('Baños'))
    habitaciones = _safe_int(doc.get('habitaciones')) or _safe_int(doc.get('Habitaciones'))
    tipo = doc.get('tipo_de_inmueble') or doc.get('tipo_inmueble') or doc.get('Tipo de Inmueble')

    return {
        'pagina': doc.get('pagina', 'finca_raiz'),
        'codigo_fuente': str(doc.get('codigo_fr', '')),
        'precio': _safe_precio(doc.get('precio')),
        'area_construida': area,
        'habitaciones': habitaciones,
        'banos': banos,
        'garajes': _safe_int(doc.get('garajes') or doc.get('Garajes') or doc.get('parqueaderos')),
        'estrato': estrato,
        'tipo_inmueble': _normalize_tipo(tipo),
        'ubicacion': doc.get('ubicacion'),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('latitud') or doc.get('lat')),
        'lon': _safe_coord(doc.get('longitud') or doc.get('lon')),
        'image': doc.get('image'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': doc.get('inmobiliaria'),
        'proyecto': doc.get('proyecto', False),
        'caracteristicas': doc.get('caracteristicas', []),
    }


def _normalize_habi(doc):
    codigo = doc.get('codigo_habi') or doc.get('code')
    caracteristicas = []
    for campo in ['parqueadero', 'ascensor', 'vigilancia', 'gimnasio',
                   'piscina', 'zonas verdes', 'salon comunal',
                   'terraza', 'balcon', 'deposito', 'gas',
                   'porteria', 'elevadores', 'zona de lavanderia']:
        val = doc.get(campo)
        if val and str(val).lower() not in ('no', 'false', '0', 'nan', 'no tiene'):
            caracteristicas.append(campo.title())

    tipo_raw = doc.get('tipo de inmueble') or doc.get('tipo_inmueble')

    return {
        'pagina': 'habi',
        'codigo_fuente': str(codigo) if codigo else None,
        'precio': _safe_precio(doc.get('precio')),
        'area_construida': _safe_float(doc.get('area') or doc.get('area construida')),
        'habitaciones': _safe_int(doc.get('habitaciones')),
        'banos': _safe_int(doc.get('banos') or doc.get('baños')),
        'garajes': _safe_int(doc.get('garajes') or doc.get('parqueadero_count')),
        'estrato': _safe_estrato(doc.get('estrato')),
        'tipo_inmueble': _normalize_tipo(tipo_raw) if tipo_raw else 'Apartamento',
        'ubicacion': doc.get('ubicacion') or doc.get('lugar') or doc.get('ciudad'),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('latitud')),
        'lon': _safe_coord(doc.get('longitud')),
        'image': doc.get('imagen') or doc.get('image'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': 'Habi',
        'proyecto': False,
        'caracteristicas': caracteristicas,
    }


PROPERATI_TIPO_MAP = {
    'apartment': 'Apartamento', 'house': 'Casa', 'store': 'Local',
    'land': 'Lote', 'PH': 'Apartamento', 'office': 'Oficina',
}
PROPERATI_OP_MAP = {'sell': 'Venta', 'rent': 'Arriendo'}


def _normalize_properati(doc):
    price = _safe_precio(doc.get('price'))
    currency = doc.get('currency', 'COP')
    if currency == 'USD' and price:
        price = int(price * 4200)
    place = doc.get('place_with_parent_names', '')
    parts = [p.strip() for p in place.split('|')] if place else []
    ubicacion = parts[0] if parts else doc.get('place_name')
    return {
        'pagina': 'properati',
        'codigo_fuente': str(doc.get('id') or doc.get('id_properati', '')),
        'precio': price,
        'area_construida': _safe_float(doc.get('surface_covered_in_m2')),
        'habitaciones': _safe_int(doc.get('bedrooms')),
        'banos': _safe_int(doc.get('bathrooms')),
        'garajes': None,
        'estrato': None,
        'tipo_inmueble': PROPERATI_TIPO_MAP.get(doc.get('property_type', ''), None),
        'tipo_operacion': PROPERATI_OP_MAP.get(doc.get('operation', ''), 'Venta'),
        'ubicacion': ubicacion,
        'direccion': None,
        'lat': _safe_coord(doc.get('lat')),
        'lon': _safe_coord(doc.get('lon')),
        'image': doc.get('image_thumbnail'),
        'descripcion': doc.get('description'),
        'inmobiliaria': None,
        'proyecto': False,
        'caracteristicas': [],
    }


def _normalize_bancolombia_reo(doc):
    return {
        'pagina': 'bancolombia_reo',
        'codigo_fuente': str(doc.get('codigo_bancolombia') or doc.get('codigo', '')),
        'precio': _safe_precio(doc.get('precio') or doc.get('precio_venta')),
        'area_construida': _safe_float(doc.get('area')),
        'habitaciones': _safe_int(doc.get('habitaciones')),
        'banos': _safe_int(doc.get('banos')),
        'garajes': _safe_int(doc.get('garajes')),
        'estrato': _safe_estrato(doc.get('estrato')),
        'tipo_inmueble': _normalize_tipo(doc.get('tipo_inmueble') or doc.get('tipo')),
        'tipo_operacion': 'REO',
        'ubicacion': doc.get('ubicacion') or f"{doc.get('ciudad', '')}, {doc.get('barrio', '')}".strip(', '),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('lat') or doc.get('latitud')),
        'lon': _safe_coord(doc.get('lon') or doc.get('longitud')),
        'image': doc.get('image') or doc.get('imagen'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': 'Bancolombia',
        'proyecto': False,
        'caracteristicas': [],
    }


def _normalize_sae(doc):
    return {
        'pagina': 'sae',
        'codigo_fuente': str(doc.get('codigo_sae') or doc.get('codigo', '')),
        'precio': _safe_precio(doc.get('precio_base') or doc.get('precio')),
        'area_construida': _safe_float(doc.get('area')),
        'habitaciones': _safe_int(doc.get('habitaciones')),
        'banos': _safe_int(doc.get('banos')),
        'garajes': None,
        'estrato': None,
        'tipo_inmueble': _normalize_tipo(doc.get('tipo_inmueble') or doc.get('tipo')),
        'tipo_operacion': 'Subasta',
        'ubicacion': doc.get('ubicacion') or f"{doc.get('ciudad', '')}, {doc.get('departamento', '')}".strip(', '),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('lat') or doc.get('latitud')),
        'lon': _safe_coord(doc.get('lon') or doc.get('longitud')),
        'image': doc.get('image') or doc.get('imagen'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': 'SAE - Gobierno',
        'proyecto': False,
        'caracteristicas': [],
    }


def _normalize_ciencuadras(doc):
    return {
        'pagina': 'ciencuadras',
        'codigo_fuente': str(doc.get('codigo_ciencuadras') or doc.get('codigo', '')),
        'precio': _safe_precio(doc.get('precio')),
        'area_construida': _safe_float(doc.get('area_construida') or doc.get('area')),
        'habitaciones': _safe_int(doc.get('habitaciones')),
        'banos': _safe_int(doc.get('banos')),
        'garajes': _safe_int(doc.get('garajes')),
        'estrato': _safe_estrato(doc.get('estrato')),
        'tipo_inmueble': _normalize_tipo(doc.get('tipo_inmueble') or doc.get('tipo')),
        'tipo_operacion': doc.get('tipo_operacion', 'Venta'),
        'ubicacion': doc.get('ubicacion'),
        'direccion': doc.get('direccion'),
        'lat': _safe_coord(doc.get('lat') or doc.get('latitud')),
        'lon': _safe_coord(doc.get('lon') or doc.get('longitud')),
        'image': doc.get('image') or doc.get('imagen'),
        'descripcion': doc.get('descripcion'),
        'inmobiliaria': doc.get('inmobiliaria'),
        'proyecto': doc.get('proyecto', False),
        'caracteristicas': doc.get('caracteristicas', []),
    }


_NORMALIZERS = {
    'finca_raiz': _normalize_finca_raiz,
    'finca_raiz_legacy': _normalize_finca_legacy,
    'habi': _normalize_habi,
    'properati': _normalize_properati,
    'bancolombia_reo': _normalize_bancolombia_reo,
    'sae': _normalize_sae,
    'ciencuadras': _normalize_ciencuadras,
}


# ── Migración asíncrona ───────────────────────────────────────

async def _upsert_one(conn: asyncpg.Connection, normalized: dict, raw_doc: dict):
    """Ejecuta f_upsert_inmueble y retorna (id_inmueble, accion)."""
    row = await conn.fetchrow("""
        SELECT * FROM iug.f_upsert_inmueble(
            $1::TEXT, $2::TEXT, $3::NUMERIC, $4::NUMERIC,
            $5::SMALLINT, $6::SMALLINT, $7::SMALLINT, $8::TEXT,
            $9::TEXT, $10::TEXT, $11::FLOAT, $12::FLOAT,
            $13::TEXT, $14::TEXT, $15::TEXT, $16::BOOLEAN, $17::JSONB,
            $18::TEXT
        )
    """,
        _clean_nan(normalized['pagina']),
        _clean_nan(normalized['codigo_fuente']),
        _clean_nan(normalized['precio']),
        _clean_nan(normalized['area_construida']),
        _clean_nan(normalized['habitaciones']),
        _clean_nan(normalized['banos']),
        _clean_nan(normalized['estrato']),
        _clean_nan(normalized['tipo_inmueble']),
        _clean_nan(normalized['ubicacion']),
        _clean_nan(normalized['direccion']),
        _clean_nan(normalized['lat']),
        _clean_nan(normalized['lon']),
        _clean_nan(normalized['image']),
        _clean_nan(normalized['descripcion']),
        _clean_nan(normalized['inmobiliaria']),
        normalized['proyecto'] if normalized['proyecto'] is not None else False,
        json.dumps(_clean_nan(raw_doc), ensure_ascii=False, default=str),
        _clean_nan(normalized.get('tipo_operacion')),
    )
    return row


async def _insert_caracteristicas(conn: asyncpg.Connection, id_inmueble: int,
                                   caracteristicas: list, fuente: str):
    for carac in caracteristicas:
        if not carac or not isinstance(carac, str):
            continue
        carac_clean = carac.strip()
        if not carac_clean or carac_clean.lower() in ('ver más', 'ver menos'):
            continue
        try:
            await conn.execute("""
                INSERT INTO iug.inmueble_caracteristica (id_inmueble, nombre, valor_bool, fuente)
                VALUES ($1, $2, TRUE, $3)
                ON CONFLICT (id_inmueble, nombre) DO NOTHING
            """, id_inmueble, carac_clean, fuente)
        except asyncpg.UniqueViolationError:
            pass
        except Exception as e:
            logger.warning(f"Failed to insert caracteristica '{carac_clean}' for inmueble {id_inmueble}: {e}")


async def migrate_mongo_to_pg(conn: asyncpg.Connection,
                               collections: list = None) -> dict:
    """
    Migra documentos de MongoDB Atlas a PostgreSQL.

    Ejecuta en un thread separado para no bloquear el event loop
    (pymongo es síncrono).

    Returns dict con estadísticas por collection y totales.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    if collections is None:
        collections = COLLECTIONS

    # Lectura de MongoDB en thread (síncrono)
    def _read_mongo():
        from pymongo import MongoClient
        with MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000) as client:
            client.admin.command('ping')

            all_docs = []
            for db_name, coll_name, formato in collections:
                db = client[db_name]
                coll = db[coll_name]
                docs = list(coll.find({}))
                for doc in docs:
                    if '_id' in doc:
                        doc['_id'] = str(doc['_id'])
                all_docs.append({
                    'db': db_name,
                    'collection': coll_name,
                    'formato': formato,
                    'docs': docs,
                })
                logger.info(f"MongoDB: {db_name}.{coll_name} → {len(docs)} docs leídos")

            return all_docs

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        all_batches = await loop.run_in_executor(pool, _read_mongo)

    # Migración a PostgreSQL (asíncrona)
    report = {
        'collections': [],
        'total_inserted': 0,
        'total_updated': 0,
        'total_unchanged': 0,
        'total_errors': 0,
        'total_skipped': 0,
    }

    for batch in all_batches:
        normalize = _NORMALIZERS[batch['formato']]
        fuente = 'habi' if batch['formato'] == 'habi' else 'finca_raiz'

        stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'errors': 0, 'skipped': 0}

        # Inferir tipo y operación desde nombre de colección
        coll_name = batch['collection']
        tipo_from_coll = _tipo_from_collection(coll_name)
        op_from_coll = 'Arriendo' if 'arriendo' in coll_name else 'Venta'

        for doc in batch['docs']:
            normalized = normalize(doc)
            if not normalized.get('codigo_fuente'):
                stats['skipped'] += 1
                continue

            # Usar colección como fallback para tipo_inmueble
            if not normalized.get('tipo_inmueble') and tipo_from_coll:
                normalized['tipo_inmueble'] = tipo_from_coll
            if not normalized.get('tipo_operacion'):
                normalized['tipo_operacion'] = op_from_coll

            try:
                row = await _upsert_one(conn, normalized, doc)
                if row:
                    accion = row[1]  # 'inserted', 'updated', 'unchanged'
                    stats[accion] = stats.get(accion, 0) + 1
                    if accion == 'inserted':
                        await _insert_caracteristicas(
                            conn, row[0],
                            normalized.get('caracteristicas', []),
                            fuente,
                        )
            except Exception as e:
                stats['errors'] += 1
                if stats['errors'] <= 3:
                    logger.warning(f"Migration error {normalized.get('codigo_fuente')}: {e}")

        coll_key = f"{batch['db']}.{batch['collection']}"
        logger.info(f"Migrated {coll_key}: ins={stats['inserted']} upd={stats['updated']} "
                     f"unch={stats['unchanged']} err={stats['errors']}")

        report['collections'].append({
            'name': coll_key,
            'formato': batch['formato'],
            'total_docs': len(batch['docs']),
            **stats,
        })
        for k in ('inserted', 'updated', 'unchanged', 'errors', 'skipped'):
            report[f'total_{k}'] += stats[k]

    return report
