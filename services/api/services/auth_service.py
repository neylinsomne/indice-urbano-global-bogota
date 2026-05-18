"""
Auth Service - JWT + bcrypt authentication.

Provides password hashing, JWT token management, and FastAPI dependencies
for protecting endpoints with role-based access and PDF usage limits.
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import httpx
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import asyncpg

from db.postgre import get_db_pool
from db.redis_cache import get_redis

logger = logging.getLogger(__name__)

# --- Config ---
SECRET_KEY = os.getenv('JWT_SECRET')
if not SECRET_KEY:
    raise RuntimeError(
        "FATAL: JWT_SECRET no está configurado. "
        "Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_MINUTES = 7 * 24 * 60  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# --- Password helpers ---

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


# --- JWT helpers ---

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    # JWT "sub" must be a string
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --- Token blacklist (Redis) ---

async def _is_token_blacklisted(token: str) -> bool:
    redis = await get_redis()
    if redis is None:
        return False
    try:
        return await redis.exists(f"bl:{token}") > 0
    except Exception:
        return False


async def blacklist_token(token: str):
    """Add token to blacklist in Redis with TTL matching its remaining lifetime."""
    redis = await get_redis()
    if redis is None:
        return
    try:
        payload = decode_token(token)
        exp = payload.get("exp", 0)
        ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
        await redis.setex(f"bl:{token}", ttl, "1")
    except Exception as e:
        logger.warning(f"Could not blacklist token: {e}")


# --- FastAPI dependencies ---

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Dependency: extracts and validates JWT from Authorization header.
    Returns user dict or raises 401.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check blacklist
    if await _is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado",
        )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token invalido")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token invalido")
        user_id = int(user_id)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, role, daily_pdf_limit, is_active, created_at "
            "FROM iug.users WHERE id = $1",
            user_id,
        )

    if row is None or not row['is_active']:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    return dict(row)


async def get_optional_user(
    token: str = Depends(oauth2_scheme),
    db: asyncpg.Pool = Depends(get_db_pool),
) -> dict | None:
    """Like get_current_user but returns None instead of raising 401."""
    if token is None:
        return None
    try:
        return await get_current_user(token=token, db=db)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency: requires the current user to have admin role."""
    if user['role'] != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    return user


async def check_pdf_limit(
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Dependency: verifies the user has not exceeded their daily PDF limit.
    Raises 429 if limit reached. Returns user dict on success.
    """
    # Admin or unlimited (-1) bypass
    if user['role'] == 'admin' or user['daily_pdf_limit'] == -1:
        return user

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT count FROM iug.pdf_usage "
            "WHERE user_id = $1 AND usage_date = CURRENT_DATE",
            user['id'],
        )

    current = row['count'] if row else 0
    limit = user['daily_pdf_limit']

    if current >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite diario alcanzado ({current}/{limit} PDFs). "
                   f"Contacta al administrador para aumentar tu limite.",
        )

    return user


async def increment_pdf_usage(db: asyncpg.Pool, user_id: int):
    """Increment the daily PDF usage counter for a user."""
    async with db.acquire() as conn:
        await conn.execute(
            "INSERT INTO iug.pdf_usage (user_id, usage_date, count) "
            "VALUES ($1, CURRENT_DATE, 1) "
            "ON CONFLICT (user_id, usage_date) "
            "DO UPDATE SET count = pdf_usage.count + 1",
            user_id,
        )


# ─── Cloudflare Turnstile (anti-bot captcha) ──────────────────────────
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_DEV_BYPASS_TOKEN = "dev-bypass"


async def verify_captcha(token: Optional[str], request: Optional[Request] = None) -> None:
    """
    Valida un token de Cloudflare Turnstile contra el endpoint de Cloudflare.
    Lanza HTTPException(400) si el token es inválido, expiró o falta.

    En modo desarrollo (sin TURNSTILE_SECRET_KEY configurado), acepta el
    token sintético "dev-bypass" para no bloquear el flujo local.

    Documentación oficial:
      https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
    """
    # Modo dev: si no hay secret configurada, aceptamos el bypass sintético
    if not TURNSTILE_SECRET_KEY:
        if token == TURNSTILE_DEV_BYPASS_TOKEN or not token:
            logger.warning(
                "Turnstile no configurado en backend. Saltando validación captcha (dev mode)."
            )
            return
        # Si hay un token "real" pero no podemos validarlo, igual seguimos
        # (mejor no romper si dev cambió al modo prod del frontend pero no del backend)
        logger.warning("Turnstile token recibido pero TURNSTILE_SECRET_KEY no configurada.")
        return

    if not token or token == TURNSTILE_DEV_BYPASS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="captcha_required",
        )

    payload = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token,
    }
    # IP del cliente (opcional pero recomendado por Cloudflare)
    if request is not None:
        client_ip = request.headers.get("CF-Connecting-IP") or request.client.host if request.client else None
        if client_ip:
            payload["remoteip"] = client_ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(TURNSTILE_VERIFY_URL, data=payload)
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Si Cloudflare está caído o responde mal, fail-closed (rechazar).
        # En servidor casero priorizamos seguridad sobre disponibilidad.
        logger.error(f"Error verificando Turnstile: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="captcha_verification_unavailable",
        )

    if not data.get("success"):
        codes = data.get("error-codes") or []
        logger.warning(f"Turnstile rechazó token. error_codes={codes}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="captcha_failed",
        )
