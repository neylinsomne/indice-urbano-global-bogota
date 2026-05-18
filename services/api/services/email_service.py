"""
Servicio de Email — OTP para verificación de cuenta.

Usa smtplib (built-in) con Gmail STARTTLS.
Los OTPs se almacenan en Redis con TTL de 15 minutos.

Configuración (.env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=tu_cuenta@gmail.com
    SMTP_PASSWORD=tu_app_password_16_chars
    SMTP_FROM=noreply@estudioinmobiliario.co  (opcional, usa SMTP_USER si falta)

Nota Gmail: Requiere "Contraseña de aplicación" (2FA habilitado).
"""
import asyncio
import os
import secrets
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER

OTP_TTL = 900        # 15 minutos
RESEND_TTL = 3600    # 1 hora para contador de reenvíos
MAX_RESENDS = 3      # Máximo reenvíos por hora


def generate_otp() -> str:
    """Genera un código OTP de 6 dígitos criptográficamente seguro."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _build_html(otp: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:30px">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:8px;
              border:1px solid #e0e0e0;padding:32px">
    <h2 style="color:#1e3a1e;margin-bottom:8px">Verifica tu correo</h2>
    <p style="color:#555;margin-bottom:24px">
      Ingresa el siguiente código para activar tu cuenta en
      <strong>Estudio Inmobiliario INMU</strong>:
    </p>
    <div style="background:#f0faf0;border:2px solid #2e7d32;border-radius:8px;
                padding:20px;text-align:center;margin-bottom:24px">
      <span style="font-size:36px;font-weight:bold;letter-spacing:10px;
                   color:#2e7d32;font-family:monospace">{otp}</span>
    </div>
    <p style="color:#777;font-size:13px">
      Este código es válido por <strong>15 minutos</strong>.<br>
      Si no creaste esta cuenta, ignora este mensaje.
    </p>
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
    <p style="color:#aaa;font-size:11px;text-align:center">
      INMU — Estudio Inmobiliario
    </p>
  </div>
</body>
</html>"""


def _send_sync(to_email: str, subject: str, html_body: str) -> None:
    """Envío sincrónico — se llama desde run_in_executor."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado — OTP no enviado por email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
    logger.info(f"OTP enviado a {to_email}")


async def send_verification_email(to_email: str, otp: str) -> None:
    """Envía el OTP por email sin bloquear el event loop."""
    html = _build_html(otp)
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, _send_sync, to_email, "Código de verificación — INMU", html
        )
    except Exception as e:
        # No lanzar error — el OTP sigue guardado en Redis
        logger.error(f"Error enviando email a {to_email}: {e}")


def _build_admin_html(payload: dict) -> str:
    """HTML simple para la notificación al admin con clave-valor escapado."""
    from html import escape

    rows = "".join(
        f"<tr><td style='padding:6px 12px;color:#555;border-bottom:1px solid #eee'>"
        f"<strong>{escape(str(k))}</strong></td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #eee'>"
        f"{escape(str(v))}</td></tr>"
        for k, v in payload.items()
    )
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:30px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;
              border:1px solid #e0e0e0;padding:32px">
    <h2 style="color:#0A2540;margin-bottom:8px">Nuevo registro en INMU</h2>
    <p style="color:#555;margin-bottom:24px">
      Un usuario nuevo creó una cuenta y aún no ha verificado su correo.
      El consentimiento hábeas data quedó registrado en
      <code>iug.consent_log</code>.
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      {rows}
    </table>
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
    <p style="color:#aaa;font-size:11px;text-align:center">
      Notificación automática · INMU Estudio Inmobiliario
    </p>
  </div>
</body></html>"""


async def send_admin_notification(to_email: str, subject: str, payload: dict) -> None:
    """
    Envía notificación administrativa (e.g. nuevo registro) al correo del admin.
    No bloquea el flujo si falla — sólo loggea.
    """
    if not to_email:
        return
    html = _build_admin_html(payload)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_sync, to_email, subject, html)


async def store_otp(redis, email: str, otp: str) -> None:
    """Guarda OTP en Redis: key=otp:verify:{email}, TTL=15min."""
    await redis.set(f"otp:verify:{email}", otp, ex=OTP_TTL)


async def verify_otp(redis, email: str, code: str) -> bool:
    """
    Verifica el OTP. Si es correcto, lo elimina (single-use).
    Retorna True si válido, False si incorrecto/expirado.
    """
    stored = await redis.get(f"otp:verify:{email}")
    if stored is None:
        return False
    stored_str = stored.decode() if isinstance(stored, bytes) else stored
    if stored_str == code:
        await redis.delete(f"otp:verify:{email}")
        return True
    return False


async def check_resend_limit(redis, email: str) -> bool:
    """
    Verifica si el usuario puede reenviar el OTP.
    Permite máx MAX_RESENDS reenvíos por hora.
    Retorna True si puede reenviar, False si superó el límite.
    """
    key = f"otp:resend:{email}"
    count = await redis.get(key)
    if count is None:
        await redis.set(key, 1, ex=RESEND_TTL)
        return True
    count_int = int(count)
    if count_int >= MAX_RESENDS:
        return False
    await redis.incr(key)
    return True
