import os
from routers import inmueble, solicitudes, iurb, busqueda_avanzada, llm, geo, acm, auth, admin, regression, pipeline, whatsapp, analytics, favoritos
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from models.model import InputModel, OutputModel
from db.postgre import connect_to_db, disconnect_from_db
from db.redis_cache import connect_to_redis, disconnect_from_redis
from routers.auth import limiter
from prometheus_fastapi_instrumentator import Instrumentator
import asyncpg

# --- Environment ---
ENV = os.getenv("ENV", "development")
IS_PROD = ENV == "production"

# Disable Swagger/ReDoc in production
docs_kwargs = {}
if IS_PROD:
    docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(
    title="API Estudio Inmobiliario",
    description="API para analisis de indicadores urbanisticos, busqueda inteligente, personalizacion AHP y consultas LLM",
    version="2.1.0",
    **docs_kwargs,
)

# --- CORS ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

if not ALLOWED_ORIGINS:
    if IS_PROD:
        ALLOWED_ORIGINS = []  # No CORS in production without explicit config
    else:
        ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:80", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Security Headers Middleware ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if IS_PROD:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# --- Rate Limiting ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
app.include_router(solicitudes.router)
app.include_router(inmueble.router)
app.include_router(iurb.router)
app.include_router(busqueda_avanzada.router)
app.include_router(llm.router)
app.include_router(geo.router)
app.include_router(acm.router)
app.include_router(auth.router)
app.include_router(admin.router)
from routers import admin_dashboard
app.include_router(admin_dashboard.router)
app.include_router(regression.router)
app.include_router(pipeline.router)
app.include_router(whatsapp.router)
app.include_router(analytics.router)
app.include_router(favoritos.router)

@app.on_event("startup")
async def startup():
    await connect_to_db()
    await connect_to_redis()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_from_redis()
    await disconnect_from_db()


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Endpoint de salud para keepalive de Cloudflare Tunnel."""
    return {"status": "ok"}
