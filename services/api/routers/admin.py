"""
Router Admin - Gestión de usuarios y outliers (solo admin).

Endpoints:
  GET    /admin/users                   -> Listar usuarios con uso diario
  POST   /admin/users                   -> Crear usuario (saltea OTP, hashea bcrypt)
  PUT    /admin/users/{id}              -> Actualizar role / limite / activo
  DELETE /admin/users/{id}              -> Desactivar usuario (soft-delete)
  POST   /admin/outliers/classify       -> Ejecutar clasificación DBSCAN
  GET    /admin/outliers                -> Listar outliers con filtros
  PUT    /admin/outliers/{id}/review    -> Confirmar o reinstalar outlier
"""
import json
import logging
import math
import re
from typing import Optional
from pydantic import BaseModel, Field, validator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
import asyncpg

from db.postgre import get_db_pool
from services.auth_service import require_admin, hash_password
from services.outlier_service import run_outlier_classification
from services.regression_service import train_all_models, should_retrain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    daily_pdf_limit: Optional[int] = None
    is_active: Optional[bool] = None


class CreateUserRequest(BaseModel):
    """
    Crea un usuario admin-side, saltando el flujo OTP.

    El password se hashea con bcrypt (mismo cost factor que el endpoint
    público /auth/register). Se inserta también una entrada en
    iug.consent_log marcada como evento='registro' con user_agent
    'admin_panel' para mantener la trazabilidad hábeas data.
    """
    email:    str  = Field(..., min_length=5, max_length=255)
    username: str  = Field(..., min_length=3, max_length=100)
    password: str  = Field(..., min_length=8, max_length=72)
    role:     str  = Field("free", pattern="^(free|premium|admin)$")
    nombre:   str  = Field("Usuario", min_length=1, max_length=80)
    apellido: str  = Field("Trial",   min_length=1, max_length=80)
    telefono: str  = Field("", max_length=20)
    cedula:   str  = Field("", max_length=20)
    daily_pdf_limit: Optional[int] = None  # si None, deduce por role

    @validator('password')
    def validate_password_strength(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Mayuscula requerida')
        if not any(c.islower() for c in v):
            raise ValueError('Minuscula requerida')
        if not any(c.isdigit() for c in v):
            raise ValueError('Digito requerido')
        return v


@router.get("/users")
async def list_users(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Lista todos los usuarios con su uso de PDFs de hoy."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.id, u.email, u.username, u.role,
                   u.daily_pdf_limit, u.is_active, u.created_at,
                   COALESCE(p.count, 0) AS pdf_usage_today
            FROM iug.users u
            LEFT JOIN iug.pdf_usage p
                ON p.user_id = u.id AND p.usage_date = CURRENT_DATE
            ORDER BY u.created_at DESC
        """)

    return [_serialize(dict(r)) for r in rows]


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Crea un usuario admin-side. Salta OTP (email_verified=TRUE),
    hashea con bcrypt y registra el consent en iug.consent_log para
    mantener la trazabilidad hábeas data exigida por Ley 1581/2012.
    """
    # Limites por defecto según role
    if body.daily_pdf_limit is None:
        default_limit = {'admin': -1, 'premium': 50, 'free': 2}
        pdf_limit = default_limit[body.role]
    else:
        pdf_limit = body.daily_pdf_limit

    # Normalizar telefono / cedula opcionales
    tel = re.sub(r'[\s\-()]+', '', body.telefono) if body.telefono else None
    ced = re.sub(r'[\s.\-]+', '', body.cedula) if body.cedula else None
    if ced and not ced.isdigit():
        raise HTTPException(422, detail="Cedula sólo dígitos")
    if tel and not re.fullmatch(r'\+?\d{7,15}', tel):
        raise HTTPException(422, detail="Telefono inválido")

    pw_hash = hash_password(body.password)
    client_ip = request.client.host if request.client else None
    user_agent = (request.headers.get("user-agent", "")[:500] or "admin_panel")

    async with db.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM iug.users WHERE email = $1 OR username = $2",
            body.email, body.username,
        )
        if existing:
            raise HTTPException(status_code=409, detail="Email o username ya registrado")

        async with conn.transaction():
            new_id = await conn.fetchval(
                """
                INSERT INTO iug.users
                  (email, username, password_hash, role, daily_pdf_limit,
                   is_active, email_verified,
                   nombre, apellido, telefono, cedula, pais, ciudad)
                VALUES ($1, $2, $3, $4, $5, TRUE, TRUE,
                        $6, $7, $8, $9, 'Colombia', 'Bogotá')
                RETURNING id
                """,
                body.email, body.username, pw_hash, body.role, pdf_limit,
                body.nombre, body.apellido, tel, ced,
            )

            # Consent log obligatorio para trazabilidad SIC
            await conn.execute(
                """
                INSERT INTO iug.consent_log
                  (user_id, email, evento, politica_version,
                   autoriza_tratamiento, autoriza_marketing, autoriza_terceros,
                   ip_origen, user_agent, locale)
                VALUES ($1, $2, 'registro', '1.0-2026',
                        TRUE, FALSE, FALSE, $3, $4, 'es-CO')
                """,
                new_id, body.email, client_ip, f"admin_panel:{user_agent[:120]}",
            )

    logger.info("Admin %s creó usuario %s (role=%s)", admin['email'], body.email, body.role)
    return {
        "id": new_id,
        "email": body.email,
        "username": body.username,
        "role": body.role,
        "daily_pdf_limit": pdf_limit,
        "is_active": True,
        "email_verified": True,
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Actualiza role, limite diario o estado activo de un usuario."""
    # Prevent admin from deactivating themselves
    if user_id == admin['id'] and body.is_active is False:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    # Validate role
    if body.role is not None and body.role not in ('admin', 'premium', 'free'):
        raise HTTPException(status_code=422, detail="Rol invalido (admin, premium, free)")

    # Build dynamic update
    sets = []
    params = []
    idx = 1

    if body.role is not None:
        sets.append(f"role = ${idx}")
        params.append(body.role)
        idx += 1
    if body.daily_pdf_limit is not None:
        sets.append(f"daily_pdf_limit = ${idx}")
        params.append(body.daily_pdf_limit)
        idx += 1
    if body.is_active is not None:
        sets.append(f"is_active = ${idx}")
        params.append(body.is_active)
        idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="Nada que actualizar")

    params.append(user_id)
    query = (
        f"UPDATE iug.users SET {', '.join(sets)} "
        f"WHERE id = ${idx} "
        f"RETURNING id, email, username, role, daily_pdf_limit, is_active, created_at"
    )

    async with db.acquire() as conn:
        row = await conn.fetchrow(query, *params)

    if row is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return _serialize(dict(row))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Soft-delete: desactiva un usuario (is_active = false)."""
    if user_id == admin['id']:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE iug.users SET is_active = false WHERE id = $1 RETURNING id",
            user_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {"message": "Usuario desactivado"}


def _serialize(row: dict) -> dict:
    if 'created_at' in row and hasattr(row['created_at'], 'isoformat'):
        row['created_at'] = row['created_at'].isoformat()
    return row


# ── Outliers ────────────────────────────────────────────────────

class ReviewOutlierRequest(BaseModel):
    action: str  # "confirm" | "reinstate"


@router.post("/outliers/classify")
async def classify_outliers(
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Ejecuta clasificacion DBSCAN y auto-dispara regresion si los umbrales lo ameritan."""
    async with db.acquire() as conn:
        dbscan_result = await run_outlier_classification(conn, admin['id'])

        # Post-DBSCAN: evaluar 4 capas de trigger para regresion
        trigger = await should_retrain(conn)
        regression_result = None
        if trigger['trigger']:
            logger.info(
                f"Auto-trigger regresion post-DBSCAN: {trigger['reasons']}"
            )
            try:
                regression_result = await train_all_models(
                    conn, admin['id'], trigger_reason='auto_post_dbscan'
                )
            except Exception as e:
                logger.error(f"Auto-trigger regresion fallo: {e}")
                regression_result = {'error': str(e)}

    return {
        **dbscan_result,
        'regression_triggered': trigger['trigger'],
        'regression_reasons': trigger.get('reasons', []),
        'regression_new_clean': trigger.get('new_clean', 0),
        'regression': regression_result,
    }


@router.get("/outliers")
async def list_outliers(
    status_filter: Optional[str] = Query(None, alias="status"),
    tipo: Optional[str] = Query(None),
    ciudad: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Lista outliers con filtros y paginación."""
    where = ["o.id_inmueble IS NOT NULL"]
    params = []
    idx = 1

    if status_filter:
        where.append(f"o.review_status = ${idx}")
        params.append(status_filter)
        idx += 1
    if tipo:
        where.append(f"i.tipo_inmueble = ${idx}")
        params.append(tipo)
        idx += 1
    if ciudad:
        where.append(f"i.ubicacion ILIKE ${idx}")
        params.append(f"%, {ciudad},%")
        idx += 1

    where_clause = " AND ".join(where)
    offset = (page - 1) * limit

    async with db.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM iug.inmueble_outlier o "
            f"JOIN iug.inmueble i ON i.id_inmueble = o.id_inmueble "
            f"WHERE {where_clause}",
            *params,
        )

        rows = await conn.fetch(
            f"SELECT i.id_inmueble, i.tipo_inmueble, i.ubicacion, "
            f"  i.precio, i.area_construida, i.image, i.estrato, "
            f"  o.outlier_labels, o.review_status, o.classified_at, "
            f"  o.reviewed_at, o.run_id "
            f"FROM iug.inmueble_outlier o "
            f"JOIN iug.inmueble i ON i.id_inmueble = o.id_inmueble "
            f"WHERE {where_clause} "
            f"ORDER BY o.classified_at DESC "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
            *params, limit, offset,
        )

    items = []
    for r in rows:
        d = dict(r)
        # Parse JSONB if string
        if isinstance(d.get('outlier_labels'), str):
            d['outlier_labels'] = json.loads(d['outlier_labels'])
        # Serialize datetimes
        for key in ('classified_at', 'reviewed_at'):
            if d.get(key) and hasattr(d[key], 'isoformat'):
                d[key] = d[key].isoformat()
        # precio/m2 for display
        if d.get('precio') and d.get('area_construida') and float(d['area_construida']) > 0:
            d['precio_m2'] = round(float(d['precio']) / float(d['area_construida']), 0)
        items.append(d)

    return {
        'items': items,
        'total': total,
        'page': page,
        'pages': math.ceil(total / limit) if total > 0 else 0,
    }


@router.put("/outliers/{id_inmueble}/review")
async def review_outlier(
    id_inmueble: int,
    body: ReviewOutlierRequest,
    admin: dict = Depends(require_admin),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Confirma o reinstala un outlier."""
    if body.action not in ('confirm', 'reinstate'):
        raise HTTPException(status_code=422, detail="Accion invalida (confirm, reinstate)")

    new_status = 'confirmed' if body.action == 'confirm' else 'reinstated'
    new_outlier_flag = body.action == 'confirm'

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE iug.inmueble_outlier "
            "SET review_status = $1, reviewed_by = $2, reviewed_at = NOW() "
            "WHERE id_inmueble = $3 RETURNING id_inmueble",
            new_status, admin['id'], id_inmueble,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Outlier no encontrado")

        await conn.execute(
            "UPDATE iug.inmueble SET is_outlier = $1 WHERE id_inmueble = $2",
            new_outlier_flag, id_inmueble,
        )

    return {"message": f"Outlier {body.action}d", "id_inmueble": id_inmueble}
