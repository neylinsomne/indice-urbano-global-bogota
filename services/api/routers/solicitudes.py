# Router de Solicitudes - Legacy (a refactorizar)
from typing import Union, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from models.model import InputModel, OutputModel
from db.postgre import get_db_pool
import asyncpg

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


class UserAnswer(BaseModel):
    """Modelo para respuestas de usuario"""
    user_id: int
    question_id: int
    alternative_id: int


@router.get("/health")
async def health_check():
    """Health check del router de solicitudes"""
    return {"status": "ok", "router": "solicitudes"}


@router.post("/obtener_mejores_inmuebles", response_model=List[OutputModel])
async def obtener_puntaje_ponderado(
    input_data: InputModel,
    db: asyncpg.Pool = Depends(get_db_pool)
):
    """Obtener mejores inmuebles basado en ponderación"""
    query = """
    SELECT * FROM obtener_puntaje_ponderado($1::json, $2::text[], $3::text);
    """

    async with db.acquire() as connection:
        try:
            results = await connection.fetch(
                query,
                input_data.pesos,
                input_data.columnas,
                input_data.barrio
            )
            return [dict(record) for record in results]
        except asyncpg.PostgresError as e:
            raise HTTPException(status_code=400, detail=str(e))
