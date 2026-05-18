"""
Router Auth - Registro, login, logout, refresh, perfil y verificación de email.

Endpoints:
  POST /auth/register             -> Crear cuenta (envía OTP, NO retorna tokens)
  POST /auth/verify-email         -> Verificar OTP -> retorna tokens
  POST /auth/resend-verification  -> Reenviar OTP (máx 3/hora)
  POST /auth/login                -> Obtener tokens JWT (bloqueado si no verificado)
  POST /auth/logout               -> Revocar token (blacklist Redis)
  POST /auth/refresh              -> Renovar access token
  GET  /auth/me                   -> Info del usuario actual + uso de PDFs hoy
"""
import logging
import os
import re
from pydantic import BaseModel, Field, validator

from fastapi import APIRouter, Depends, HTTPException, Request, status
import asyncpg
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

from db.postgre import get_db_pool
from db.redis_cache import get_redis
from services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    blacklist_token,
    _is_token_blacklisted,
    get_current_user,
    oauth2_scheme,
    verify_captcha,
)
from services.email_service import (
    generate_otp,
    send_verification_email,
    send_admin_notification,
    store_otp,
    verify_otp,
    check_resend_limit,
)

# Versión actual de la Política de Tratamiento de Datos. Incrementar cuando
# se cambien finalidades, encargados o derechos. Cada cambio invalida los
# consentimientos previos y obliga a re-aceptación.
POLITICA_VERSION = "1.0-2026"
ADMIN_NOTIFY_EMAIL = os.getenv("ADMIN_NOTIFY_EMAIL", "")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=72, description="Min 8 chars, must include uppercase, lowercase, and digit")
    captcha_token: str = Field("", max_length=2048, description="Token de Cloudflare Turnstile")

    # PII para hábeas data (todo bounded a longitudes razonables)
    nombre:   str = Field(..., min_length=1, max_length=80)
    apellido: str = Field(..., min_length=1, max_length=80)
    telefono: str = Field("", max_length=20)
    cedula:   str = Field("", max_length=20)
    pais:     str = Field("Colombia", max_length=40)
    ciudad:   str = Field("Bogotá",   max_length=60)

    # Consentimientos hábeas data (Ley 1581/2012 art. 9)
    autoriza_tratamiento: bool = Field(..., description="Obligatorio para crear la cuenta")
    autoriza_marketing:   bool = Field(False, description="Opcional. Comunicaciones comerciales")
    autoriza_terceros:    bool = Field(False, description="Opcional. Análisis con aliados académicos")
    politica_version:     str  = Field("1.0-2026", max_length=20)

    @validator('password')
    def validate_password_strength(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe incluir al menos una mayuscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe incluir al menos una minuscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe incluir al menos un numero')
        return v

    @validator('autoriza_tratamiento')
    def must_consent(cls, v):
        if not v:
            raise ValueError('Debes autorizar el tratamiento de datos para crear la cuenta')
        return v

    @validator('telefono')
    def normalize_phone(cls, v):
        if not v:
            return ""
        cleaned = re.sub(r'[\s\-()]+', '', v)
        if cleaned and not re.fullmatch(r'\+?\d{7,15}', cleaned):
            raise ValueError('Teléfono inválido')
        return cleaned

    @validator('cedula')
    def normalize_cedula(cls, v):
        if not v:
            return ""
        cleaned = re.sub(r'[\s\.\-]+', '', v)
        if cleaned and not cleaned.isdigit():
            raise ValueError('Cédula sólo números')
        if cleaned and not (4 <= len(cleaned) <= 12):
            raise ValueError('Cédula entre 4 y 12 dígitos')
        return cleaned


class LoginRequest(BaseModel):
    email: str
    password: str
    captcha_token: str = Field("", max_length=2048, description="Token de Cloudflare Turnstile (opcional en login)")


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    email: str
    code: str = Field(..., min_length=6, max_length=6)


class ResendVerificationRequest(BaseModel):
    email: str


def _user_response(row: dict) -> dict:
    """Serialize user row (exclude password_hash)."""
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"],
        "role": row["role"],
        "daily_pdf_limit": row["daily_pdf_limit"],
        "is_active": row["is_active"],
        "email_verified": row.get("email_verified", False),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
    }


# --- Endpoints ---

@router.post("/register")
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Crea una cuenta nueva con role 'free'.
    NO retorna tokens — el usuario debe verificar su email primero.
    Envía un OTP de 6 dígitos al correo registrado.

    Requiere captcha de Cloudflare Turnstile válido (anti-bot).
    """
    # Validación captcha — bloquea bots ANTES de hashear y crear cuenta
    await verify_captcha(body.captcha_token, request)

    pw_hash = hash_password(body.password)
    client_ip = (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent", "")[:500]
    locale = request.headers.get("accept-language", "")[:20]

    async with db.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM iug.users WHERE email = $1 OR username = $2",
            body.email, body.username,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El email o nombre de usuario ya esta registrado",
            )

        async with conn.transaction():
            new_user_id = await conn.fetchval(
                "INSERT INTO iug.users "
                "(email, username, password_hash, nombre, apellido, telefono, cedula, pais, ciudad) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                "RETURNING id",
                body.email, body.username, pw_hash,
                body.nombre, body.apellido, body.telefono or None,
                body.cedula or None, body.pais, body.ciudad,
            )

            # Log inmutable del consentimiento — ART. 9 Ley 1581/2012
            await conn.execute(
                "INSERT INTO iug.consent_log "
                "(user_id, email, evento, politica_version, "
                " autoriza_tratamiento, autoriza_marketing, autoriza_terceros, "
                " ip_origen, user_agent, locale) "
                "VALUES ($1, $2, 'registro', $3, $4, $5, $6, $7, $8, $9)",
                new_user_id, body.email, body.politica_version or POLITICA_VERSION,
                body.autoriza_tratamiento, body.autoriza_marketing, body.autoriza_terceros,
                client_ip, user_agent, locale,
            )

    otp = generate_otp()
    redis = await get_redis()
    if redis:
        await store_otp(redis, body.email, otp)
    await send_verification_email(body.email, otp)

    # Notificación al admin (best-effort: no bloquea el registro si falla)
    if ADMIN_NOTIFY_EMAIL:
        try:
            await send_admin_notification(
                to_email=ADMIN_NOTIFY_EMAIL,
                subject=f"[INMU] Nuevo registro: {body.nombre} {body.apellido}",
                payload={
                    "Nombre completo": f"{body.nombre} {body.apellido}",
                    "Email": body.email,
                    "Usuario": body.username,
                    "Teléfono": body.telefono or "(no aportado)",
                    "Cédula": body.cedula or "(no aportada)",
                    "Ciudad": f"{body.ciudad}, {body.pais}",
                    "Marketing": "Sí" if body.autoriza_marketing else "No",
                    "Terceros académicos": "Sí" if body.autoriza_terceros else "No",
                    "IP origen": client_ip or "(desconocida)",
                    "Política aceptada": body.politica_version or POLITICA_VERSION,
                },
            )
        except Exception as e:
            logger.warning("No se pudo notificar al admin de %s: %s", body.email, e)

    logger.info(f"Usuario registrado (pendiente verificación): {body.email}")
    return {
        "message": "Cuenta creada. Revisa tu correo e ingresa el código de verificación.",
        "email": body.email,
    }


@router.post("/verify-email")
@limiter.limit("10/minute")
async def verify_email_endpoint(
    request: Request,
    body: VerifyEmailRequest,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Verifica el OTP enviado al correo.
    Si es correcto, activa la cuenta y retorna tokens JWT.
    """
    redis = await get_redis()
    if redis is None:
        raise HTTPException(status_code=503, detail="Servicio de verificacion no disponible")

    valid = await verify_otp(redis, body.email, body.code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto o expirado",
        )

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE iug.users SET email_verified = TRUE "
            "WHERE email = $1 AND is_active = TRUE "
            "RETURNING id, email, username, role, daily_pdf_limit, is_active, email_verified, created_at",
            body.email,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    logger.info(f"Email verificado: {body.email}")
    tokens = _make_tokens(row["id"])
    return {"user": _user_response(dict(row)), **tokens}


@router.post("/resend-verification")
@limiter.limit("5/minute")
async def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Reenvía el OTP de verificación.
    Límite: máx 3 reenvíos por hora por email.
    """
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email_verified, is_active FROM iug.users WHERE email = $1",
            body.email,
        )

    if row is None or not row["is_active"]:
        return {"message": "Si el correo existe, recibirás un nuevo código."}

    if row["email_verified"]:
        return {"message": "Este correo ya está verificado."}

    redis = await get_redis()
    if redis is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible")

    can_resend = await check_resend_limit(redis, body.email)
    if not can_resend:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Espera antes de solicitar otro código.",
        )

    otp = generate_otp()
    await store_otp(redis, body.email, otp)
    await send_verification_email(body.email, otp)

    return {"message": "Código reenviado. Revisa tu correo."}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: asyncpg.Pool = Depends(get_db_pool)):
    """Autentica con email + password, retorna tokens JWT."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password_hash, role, "
            "daily_pdf_limit, is_active, email_verified, created_at "
            "FROM iug.users WHERE email = $1",
            body.email,
        )

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )

    if not row["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        )

    tokens = _make_tokens(row["id"])
    return {"user": _user_response(dict(row)), **tokens}


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/logout")
async def logout(
    body: LogoutRequest = LogoutRequest(),
    token: str = Depends(oauth2_scheme),
):
    """Revoca access + refresh tokens (blacklist Redis)."""
    if token:
        await blacklist_token(token)
    if body.refresh_token:
        await blacklist_token(body.refresh_token)
    return {"message": "Sesion cerrada"}


@router.post("/refresh")
async def refresh(body: RefreshRequest, db: asyncpg.Pool = Depends(get_db_pool)):
    """Genera un nuevo access token usando un refresh token valido."""
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token de refresh invalido")
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalido o expirado",
        )

    # Check if refresh token was blacklisted (e.g. after logout)
    if await _is_token_blacklisted(body.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revocado",
        )

    # Verify user still exists and is active
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, is_active FROM iug.users WHERE id = $1", user_id
        )

    if row is None or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    access_token = create_access_token({"sub": user_id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def me(
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Retorna info del usuario actual + uso de PDFs hoy."""
    async with db.acquire() as conn:
        usage_row = await conn.fetchrow(
            "SELECT count FROM iug.pdf_usage "
            "WHERE user_id = $1 AND usage_date = CURRENT_DATE",
            user["id"],
        )

    user_data = _user_response(user)
    user_data["pdf_usage_today"] = usage_row["count"] if usage_row else 0
    return user_data


# --- Helpers ---

def _make_tokens(user_id: int) -> dict:
    return {
        "access_token": create_access_token({"sub": user_id}),
        "refresh_token": create_refresh_token({"sub": user_id}),
        "token_type": "bearer",
    }
