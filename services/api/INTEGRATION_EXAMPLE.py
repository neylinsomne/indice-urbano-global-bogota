"""
Ejemplo de integración en main.py

COPIAR ESTAS SECCIONES A TU main.py EXISTENTE
"""

# ============================================
# 1. IMPORTS (agregar al inicio del archivo)
# ============================================
import asyncio
from contextlib import asynccontextmanager
import asyncpg

from .services.pca_service import init_pca_service
from .listeners.postgres_listener import listen_postgres_notifications
from .routers import indicadores  # Agregar a imports existentes


# ============================================
# 2. LIFESPAN (reemplazar o modificar el existente)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    
    # STARTUP
    print("🚀 Iniciando aplicación...")
    
    # Crear pool de conexiones PostgreSQL
    db_pool = await asyncpg.create_pool(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5434)),
        database=os.getenv("PG_DB", "postgres"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "xd"),
        min_size=2,
        max_size=10
    )
    
    # Inicializar servicio PCA
    init_pca_service(db_pool)
    print("✅ PCA Service inicializado")
    
    # Iniciar listener de PostgreSQL en background
    listener_task = asyncio.create_task(
        listen_postgres_notifications(db_pool)
    )
    print("✅ PostgreSQL Listener iniciado")
    
    # Guardar referencias en app state
    app.state.db_pool = db_pool
    app.state.listener_task = listener_task
    
    yield  # Aplicación corriendo
    
    # SHUTDOWN
    print("🛑 Deteniendo aplicación...")
    
    # Cancelar listener
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    
    # Cerrar pool de conexiones
    await db_pool.close()
    print("✅ Recursos liberados")


# ============================================
# 3. APP (modificar la creación de FastAPI)
# ============================================
app = FastAPI(
    title="API Indicadores Inmuebles",
    version="1.0.0",
    lifespan=lifespan  # <-- Agregar esto
)

# ============================================
# 4. ROUTERS (agregar junto a los existentes)
# ============================================
app.include_router(indicadores.router)


# ============================================
# 5. DEPENDENCY PARA DB POOL
# ============================================
def get_db_pool() -> asyncpg.Pool:
    """Dependency para obtener el pool de conexiones"""
    return app.state.db_pool


# ============================================
# 6. ENDPOINT DE PRUEBA (opcional)
# ============================================
@app.get("/")
async def root():
    return {
        "message": "API Indicadores v1.0",
        "endpoints": {
            "websocket": "ws://localhost:8000/api/indicadores/ws",
            "recalcular_pca": "POST /api/indicadores/recalcular-pca",
            "refresh_scores": "POST /api/indicadores/refresh-scores",
            "get_score": "GET /api/indicadores/{id_inmueble}"
        }
    }
