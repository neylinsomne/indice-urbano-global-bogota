"""
Router /favoritos — gestión de inmuebles que el usuario marca como
"me interesan" desde el chatbot o el dashboard.

Endpoints:
  POST   /favoritos              añade (idempotente)
  DELETE /favoritos/{id_inmueble} quita
  GET    /favoritos               lista los favoritos del usuario
  PATCH  /favoritos/{id_inmueble} actualiza nota o carpeta

Todos los endpoints requieren autenticación (Bearer token).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from db.postgre import get_db_pool
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/favoritos", tags=["favoritos"])


class FavoritoCreate(BaseModel):
    id_inmueble: int      = Field(..., gt=0)
    nota:        str      = Field("", max_length=500)
    carpeta:     str      = Field("default", max_length=60)


class FavoritoUpdate(BaseModel):
    nota:    Optional[str] = Field(None, max_length=500)
    carpeta: Optional[str] = Field(None, max_length=60)


@router.get("")
async def listar_favoritos(
    carpeta: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Lista los favoritos del usuario con todos los datos del inmueble
    (precio actual, IUG actual, ubicación). Opcionalmente filtra por carpeta.
    """
    params: List[Any] = [user["id"]]
    where_carpeta = ""
    if carpeta:
        params.append(carpeta)
        where_carpeta = f"AND f.carpeta = ${len(params)}"

    async with db.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                f.id_inmueble, f.nota, f.carpeta,
                f.snapshot_iug, f.snapshot_precio,
                f.created_at, f.updated_at,
                i.tipo_inmueble, i.precio, i.area_construida,
                i.habitaciones, i.banos,
                i.iurb AS iug_actual,
                l.nombre AS localidad,
                b.nombre AS barrio,
                ST_X(i.geom)::float AS lon,
                ST_Y(i.geom)::float AS lat
            FROM iug.user_favoritos f
            JOIN iug.inmueble  i ON i.id_inmueble = f.id_inmueble
            LEFT JOIN iug.localidad l ON l.id_localidad = i.id_localidad
            LEFT JOIN iug.barrio   b ON b.id_barrio    = i.id_barrio
            WHERE f.user_id = $1 {where_carpeta}
            ORDER BY f.created_at DESC
            """,
            *params,
        )
    return {"count": len(rows), "favoritos": [dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def agregar_favorito(
    body: FavoritoCreate,
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Marca un inmueble como favorito. Idempotente: si ya está, actualiza
    la nota/carpeta sin error.
    """
    async with db.acquire() as conn:
        # Verificamos que el inmueble exista y capturamos snapshot
        snap = await conn.fetchrow(
            "SELECT iurb, precio FROM iug.inmueble WHERE id_inmueble = $1",
            body.id_inmueble,
        )
        if not snap:
            raise HTTPException(404, "Inmueble no existe")

        row = await conn.fetchrow(
            """
            INSERT INTO iug.user_favoritos
                (user_id, id_inmueble, nota, carpeta,
                 snapshot_iug, snapshot_precio)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, id_inmueble) DO UPDATE SET
                nota    = EXCLUDED.nota,
                carpeta = EXCLUDED.carpeta,
                updated_at = NOW()
            RETURNING id, created_at, updated_at
            """,
            user["id"], body.id_inmueble, body.nota, body.carpeta,
            snap["iurb"], snap["precio"],
        )
    return {
        "id_inmueble": body.id_inmueble,
        "nota":        body.nota,
        "carpeta":     body.carpeta,
        "created_at":  row["created_at"],
        "updated_at":  row["updated_at"],
    }


@router.delete("/{id_inmueble}", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_favorito(
    id_inmueble: int,
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Quita un inmueble de favoritos. No falla si no estaba."""
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM iug.user_favoritos WHERE user_id = $1 AND id_inmueble = $2",
            user["id"], id_inmueble,
        )


@router.patch("/{id_inmueble}")
async def actualizar_favorito(
    id_inmueble: int,
    body: FavoritoUpdate,
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Actualiza nota o carpeta de un favorito existente."""
    updates: List[str] = []
    params: List[Any] = [user["id"], id_inmueble]
    if body.nota is not None:
        params.append(body.nota)
        updates.append(f"nota = ${len(params)}")
    if body.carpeta is not None:
        params.append(body.carpeta)
        updates.append(f"carpeta = ${len(params)}")
    if not updates:
        raise HTTPException(422, "Nada que actualizar (envía nota o carpeta)")
    updates.append("updated_at = NOW()")

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE iug.user_favoritos
            SET {", ".join(updates)}
            WHERE user_id = $1 AND id_inmueble = $2
            RETURNING id_inmueble, nota, carpeta, updated_at
            """,
            *params,
        )
    if not row:
        raise HTTPException(404, "Favorito no encontrado")
    return dict(row)


@router.get("/ids")
async def listar_ids(
    user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """
    Devuelve sólo los IDs (set) de inmuebles favoritos del usuario.
    Útil para que el frontend pinte el corazón lleno/vacío en cards
    sin tener que pedir el detalle.
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id_inmueble FROM iug.user_favoritos WHERE user_id = $1",
            user["id"],
        )
    return {"ids": [r["id_inmueble"] for r in rows]}
