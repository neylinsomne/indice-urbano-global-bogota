"""
Router ACM - Análisis Comparativo de Mercado

Endpoints para generar reportes ACM por inmueble:
  GET  /acm/{id}/data?metodo=clasico|dbscan  -> JSON con datos del estudio
  GET  /acm/{id}/pdf?metodo=clasico|dbscan   -> PDF descargable
  GET  /acm/mis-reportes                     -> Reportes guardados del usuario
  POST /acm/manual                           -> PDF desde datos manuales (todos los roles)
  POST /acm/scrape-url                       -> Extrae datos de URL (premium/admin)

Cache: si el usuario ya generó un reporte para el mismo inmueble+metodo
y aún no expiró, se sirve desde cache sin descontar del límite diario.
  - free:          1 día
  - premium/admin: 30 días
"""
import io
import os
import json
import asyncio
import datetime
import logging
import tempfile
import shutil
from datetime import timedelta
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncpg

from slowapi import Limiter
from slowapi.util import get_remote_address

from db.postgre import get_db_pool
from services.acm_service import (
    build_acm_data,
    build_acm_from_address,
)
from services.acm_pdf import generate_acm_pdf
from services.auth_service import (
    get_current_user, increment_pdf_usage,
    decode_token, oauth2_scheme, _is_token_blacklisted,
)
from services.url_scraper_service import scrape_property_url, validate_url
from jose import JWTError

logger = logging.getLogger(__name__)

# Rate limiter por IP. Generar PDFs es costoso (CPU + storage) y los
# endpoints son un vector de DoS si se abusa. Combinado con el límite
# diario por usuario (daily_pdf_limit), forma defensa en profundidad.
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/acm", tags=["acm"])

# Duración del cache por rol
CACHE_TTL = {
    'free': timedelta(days=1),
    'premium': timedelta(days=30),
    'admin': timedelta(days=30),
}


class MetodoACM(str, Enum):
    clasico = "clasico"
    dbscan = "dbscan"


# ── Auth helpers (soportan ?token= para iframe/window.open) ──

async def _get_user_from_token_or_query(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    effective_token = token or request.query_params.get("token")
    if not effective_token:
        raise HTTPException(status_code=401, detail="No autenticado")

    if await _is_token_blacklisted(effective_token):
        raise HTTPException(status_code=401, detail="Token revocado")

    try:
        payload = decode_token(effective_token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token invalido")
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, role, daily_pdf_limit, is_active, created_at "
            "FROM iug.users WHERE id = $1", user_id
        )
    if row is None or not row['is_active']:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    return dict(row)


# ── Cache helpers ──

async def _get_cached_report(conn, user_id: int, inmueble_id: int, metodo: str):
    """Retorna el JSONB data del cache si existe y no expiró, o None."""
    row = await conn.fetchrow(
        "SELECT data, created_at FROM iug.acm_reports "
        "WHERE user_id = $1 AND inmueble_id = $2 AND metodo = $3 "
        "AND expires_at > NOW()",
        user_id, inmueble_id, metodo,
    )
    if row is None:
        return None
    # asyncpg may return JSONB as str depending on codec; ensure dict
    data = row['data']
    if isinstance(data, str):
        data = json.loads(data)
    return {'data': data, 'created_at': row['created_at']}


async def _save_report_to_cache(conn, user_id: int, inmueble_id: int,
                                 metodo: str, data: dict, role: str):
    """Guarda o actualiza el reporte en cache con TTL según rol."""
    ttl = CACHE_TTL.get(role, CACHE_TTL['free'])
    await conn.execute("""
        INSERT INTO iug.acm_reports (user_id, inmueble_id, metodo, data, expires_at)
        VALUES ($1, $2, $3, $4::jsonb, NOW() + $5::interval)
        ON CONFLICT (user_id, inmueble_id, metodo)
        DO UPDATE SET data = $4::jsonb,
                      created_at = NOW(),
                      expires_at = NOW() + $5::interval
    """, user_id, inmueble_id, metodo, json.dumps(data, default=str), ttl)


async def _check_limit_or_cache(conn, user: dict, inmueble_id: int, metodo: str) -> bool:
    """
    Retorna True si hay cache válido (no descuenta).
    Si no hay cache, verifica el límite diario y lanza 429 si se excede.
    """
    # Check cache first
    cached = await _get_cached_report(conn, user['id'], inmueble_id, metodo)
    if cached:
        return True  # hay cache, no descuenta

    # No cache → verificar límite (admin/ilimitado bypass)
    if user['role'] == 'admin' or user['daily_pdf_limit'] == -1:
        return False

    row = await conn.fetchrow(
        "SELECT count FROM iug.pdf_usage "
        "WHERE user_id = $1 AND usage_date = CURRENT_DATE", user['id']
    )
    current = row['count'] if row else 0
    limit = user['daily_pdf_limit']

    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Limite diario alcanzado ({current}/{limit} PDFs)",
        )
    return False


# ── Endpoints ──

@router.get("/mis-reportes")
async def get_mis_reportes(
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Lista los reportes ACM guardados (no expirados) del usuario."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.id, r.inmueble_id, r.metodo, r.created_at, r.expires_at,
                   (r.data->'subject'->>'ubicacion') AS ubicacion,
                   (r.data->'subject'->>'tipo_inmueble') AS tipo_inmueble,
                   (r.data->'subject'->>'precio')::numeric AS precio
            FROM iug.acm_reports r
            WHERE r.user_id = $1 AND r.expires_at > NOW()
            ORDER BY r.created_at DESC
        """, user['id'])

    return [
        {
            **dict(r),
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/{id_inmueble}/data")
async def get_acm_data(
    id_inmueble: int,
    metodo: MetodoACM = Query(MetodoACM.clasico, description="Metodo de seleccion de comparables"),
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Retorna los datos del ACM como JSON.
    Si hay un reporte cacheado no expirado, lo retorna directamente.
    """
    async with db.acquire() as conn:
        # Check cache
        cached = await _get_cached_report(conn, user['id'], id_inmueble, metodo.value)
        if cached:
            data = cached['data']  # JSONB ya viene como dict
            data['_cached'] = True
            data['_cached_at'] = cached['created_at'].isoformat()
            return data

        # Generate fresh
        try:
            data = await build_acm_data(conn, id_inmueble, metodo=metodo.value)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    _serialize_dates(data)
    data['_cached'] = False
    return data


@router.get("/{id_inmueble}/pdf")
@limiter.limit("10/minute")
async def get_acm_pdf(
    id_inmueble: int,
    request: Request,
    metodo: MetodoACM = Query(MetodoACM.clasico, description="Metodo de seleccion de comparables"),
    token: str = Depends(oauth2_scheme),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Genera y retorna el PDF del ACM.
    Si hay cache válido, regenera PDF desde cache SIN descontar del límite.
    Si no hay cache, genera nuevo, guarda en cache, y descuenta 1 crédito.
    Acepta token via header o query param (?token=).
    """
    user = await _get_user_from_token_or_query(request, token, db)

    async with db.acquire() as conn:
        from_cache = await _check_limit_or_cache(conn, user, id_inmueble, metodo.value)

        if from_cache:
            # Servir desde cache - NO descuenta
            cached = await _get_cached_report(conn, user['id'], id_inmueble, metodo.value)
            data = cached['data']
            logger.info(f"ACM cache hit: user={user['id']} inmueble={id_inmueble} metodo={metodo.value}")
        else:
            # Generar nuevo
            try:
                data = await build_acm_data(conn, id_inmueble, metodo=metodo.value)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

            _serialize_dates(data)

            # Guardar en cache
            await _save_report_to_cache(
                conn, user['id'], id_inmueble, metodo.value, data, user['role']
            )

            # Descontar del límite diario
            await increment_pdf_usage(db, user['id'])
            logger.info(f"ACM generated: user={user['id']} inmueble={id_inmueble} metodo={metodo.value}")

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(None, generate_acm_pdf, data)

    barrio = (data['subject'].get('ubicacion') or 'inmueble').replace(' ', '_')[:30]
    metodo_tag = metodo.value.upper()
    filename = f"ACM_{metodo_tag}_{barrio}_{data.get('generated_at', '')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _serialize_dates(obj):
    """Convierte recursivamente objetos date/datetime a strings ISO."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if hasattr(v, 'isoformat'):
                obj[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                _serialize_dates(v)
    elif isinstance(obj, list):
        for item in obj:
            _serialize_dates(item)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas para endpoints manuales
# ─────────────────────────────────────────────────────────────────────────────

class SujetoManual(BaseModel):
    tipo_inmueble: str = "Apartamento"
    ubicacion: str = ""
    ciudad: str = ""
    estado: Optional[str] = None
    edad: Optional[str] = None
    area_construida: float
    estrato: Optional[int] = None
    precio: float
    image: Optional[str] = None
    url_anuncio: Optional[str] = None
    observaciones: Optional[str] = None


class ScrapeUrlRequest(BaseModel):
    url: str


# ── Directorio para logos de usuario ──
_app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_DIR = os.path.join(_app_root, 'uploads', 'logos')
try:
    os.makedirs(LOGO_DIR, exist_ok=True)
except PermissionError:
    LOGO_DIR = os.path.join(tempfile.gettempdir(), 'inmu_logos')
    os.makedirs(LOGO_DIR, exist_ok=True)

MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints manuales / scraping
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Sube el logo del negocio del usuario. Se usa en el header de los informes PDF.
    Formatos: PNG, JPG. Máximo 2MB.
    """
    if file.content_type not in ('image/png', 'image/jpeg', 'image/jpg'):
        raise HTTPException(400, "Solo se aceptan imágenes PNG o JPG")

    data = await file.read()
    if len(data) > MAX_LOGO_SIZE:
        raise HTTPException(400, "El logo no puede pesar más de 2MB")

    ext = '.png' if 'png' in file.content_type else '.jpg'
    logo_filename = f"logo_user_{user['id']}{ext}"
    logo_path = os.path.join(LOGO_DIR, logo_filename)

    with open(logo_path, 'wb') as f:
        f.write(data)

    return {"message": "Logo guardado", "filename": logo_filename}


@router.delete("/logo")
async def delete_logo(user: dict = Depends(get_current_user)):
    """Elimina el logo del usuario."""
    for ext in ('.png', '.jpg'):
        path = os.path.join(LOGO_DIR, f"logo_user_{user['id']}{ext}")
        if os.path.exists(path):
            os.unlink(path)
    return {"message": "Logo eliminado"}


def _get_user_logo(user_id: int) -> str:
    """Busca el logo del usuario. Retorna path o None."""
    for ext in ('.png', '.jpg'):
        path = os.path.join(LOGO_DIR, f"logo_user_{user_id}{ext}")
        if os.path.exists(path):
            return path
    return None


@router.post("/manual")
@limiter.limit("10/minute")
async def acm_manual(
    request: Request,
    body: SujetoManual,
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Genera un PDF del ACM a partir de los datos del inmueble sujeto.
    Los comparables se buscan automáticamente en la base de datos scrapeada.
    Disponible para todos los roles autenticados.
    Descuenta 1 crédito del límite diario.
    Incluye mapa de zona con indicadores e indicadores urbanos.
    Si el usuario tiene un logo subido, se muestra en el header del PDF.
    """
    # Verificar límite diario (admin tiene -1 = ilimitado)
    async with db.acquire() as conn:
        if user["role"] != "admin" and user["daily_pdf_limit"] != -1:
            usage_row = await conn.fetchrow(
                "SELECT count FROM iug.pdf_usage "
                "WHERE user_id = $1 AND usage_date = CURRENT_DATE",
                user["id"],
            )
            current = usage_row["count"] if usage_row else 0
            if current >= user["daily_pdf_limit"]:
                raise HTTPException(
                    status_code=429,
                    detail=f"Limite diario alcanzado ({current}/{user['daily_pdf_limit']} PDFs)",
                )

        # Construir ACM buscando comparables automáticamente en la DB
        subject_dict = body.dict()
        observaciones = subject_dict.pop("observaciones", None)

        try:
            acm_data = await build_acm_from_address(conn, subject_dict)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if observaciones:
        acm_data["observaciones"] = observaciones

    _serialize_dates(acm_data)

    # Logo del usuario
    logo_path = _get_user_logo(user["id"])

    # Generar PDF con mapa + logo
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None, generate_acm_pdf, acm_data, logo_path,
    )

    # Descontar crédito
    await increment_pdf_usage(db, user["id"])
    logger.info(f"ACM manual generado: user={user['id']}")

    barrio = (body.ubicacion or "inmueble").replace(" ", "_")[:30]
    filename = f"ACM_{barrio}_{acm_data.get('generated_at', '')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/scrape-url")
@limiter.limit("5/minute")
async def acm_scrape_url(
    request: Request,
    body: ScrapeUrlRequest,
    user: dict = Depends(get_current_user),
):
    """
    [Beta — solo premium/admin] Extrae datos de un inmueble desde su URL.
    Sitios soportados: fincaraiz.com.co, habi.co, metrocuadrado.com

    Control de concurrencia:
      - Un solo scraping por usuario a la vez (429 si ya hay uno activo)
      - Máximo 5 scrapers simultáneos globalmente
    """
    if user["role"] not in ("premium", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Esta función está disponible solo para usuarios premium.",
        )

    # Validar dominio antes de intentar scrape
    try:
        validate_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        data = await scrape_property_url(body.url, user["id"])
    except RuntimeError as e:
        if str(e) == "user_busy":
            raise HTTPException(
                status_code=429,
                detail="Ya tienes un análisis en progreso. Espera a que termine.",
            )
        raise HTTPException(status_code=500, detail=f"Error de scraping: {e}")
    except Exception as e:
        logger.warning(f"Scrape URL falló para user={user['id']} url={body.url}: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"No se pudieron extraer datos de la URL. Verifica que sea un anuncio válido.",
        )

    return {
        "status": "ok",
        "beta_notice": "Funcionalidad en desarrollo — los resultados pueden ser incompletos.",
        "data": data,
    }
