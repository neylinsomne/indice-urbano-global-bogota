import asyncpg
import os
from typing import Any, Dict
import logging

# Usar variables de entorno
DATABASE_TYPE = 'postgresql'
ENDPOINT = os.getenv('PG_HOST', 'localhost')
USER = os.getenv('PG_USER', 'postgres')
PASSWORD = os.getenv('PG_PASSWORD')
if not PASSWORD:
    raise RuntimeError("FATAL: PG_PASSWORD no está configurado.")
PORT = int(os.getenv('PG_PORT', '5432'))
DATABASE = os.getenv('PG_DB', 'postgres')

DATABASE_URL = f"{DATABASE_TYPE}://{USER}:{PASSWORD}@{ENDPOINT}:{PORT}/{DATABASE}"

db_pool = None

async def connect_to_db():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        logging.info("Database connection initialized")

async def disconnect_from_db():
    global db_pool
    if db_pool is not None:
        await db_pool.close()
        db_pool = None
        logging.info("Database connection closed")

async def get_db_pool() -> asyncpg.Pool:
    """
    Dependency para obtener el pool de conexiones a la DB.
    Usado en endpoints FastAPI con Depends(get_db_pool).
    """
    global db_pool
    if db_pool is None:
        await connect_to_db()
    return db_pool