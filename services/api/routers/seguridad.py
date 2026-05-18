"""
API endpoints para gestionar indicador de seguridad.
Permite actualizar pesos AHP y recalcular normalización.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

router = APIRouter(prefix="/seguridad", tags=["seguridad"])

# Modelos Pydantic
class PesosAHP(BaseModel):
    homicidios: float = Field(..., ge=0, le=1, description="Peso para homicidios")
    delitos_sexuales: float = Field(..., ge=0, le=1, description="Peso para delitos sexuales")
    hurto_personas: float = Field(..., ge=0, le=1, description="Peso para hurto a personas")
    otros_delitos: float = Field(..., ge=0, le=1, description="Peso para otros delitos")
    
    @validator('otros_delitos')
    def suma_debe_ser_uno(cls, v, values):
        total = v + values.get('homicidios', 0) + values.get('delitos_sexuales', 0) + values.get('hurto_personas', 0)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f'Los pesos deben sumar 1.0, suma actual: {total:.4f}')
        return v

class PesosNormalizacion(BaseModel):
    peso_cai: float = Field(..., ge=0, le=1)
    peso_crimen: float = Field(..., ge=0, le=1)
    peso_sector: float = Field(..., ge=0, le=1)
    
    @validator('peso_sector')
    def suma_razonable(cls, v, values):
        total = v + values.get('peso_cai', 0) + values.get('peso_crimen', 0)
        if total < 0.9 or total > 1.1:
            raise ValueError(f'Los pesos deberían sumar ~1.0, suma actual: {total:.4f}')
        return v

# Dependency
def get_db():
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DB', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', 'xd')
    )
    try:
        yield conn
    finally:
        conn.close()

@router.get("/pesos-ahp")
async def obtener_pesos_ahp(conn = Depends(get_db)):
    """Obtener pesos AHP actuales para tipos de crimen."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT tipo_delito, peso_ahp, descripcion, version, fecha_actualizacion
            FROM iug.ahp_pesos_crimen
            ORDER BY peso_ahp DESC
        """)
        pesos = cur.fetchall()
    
    return {
        "pesos": pesos,
        "suma": sum(p['peso_ahp'] for p in pesos)
    }

@router.put("/pesos-ahp")
async def actualizar_pesos_ahp(pesos: PesosAHP, conn = Depends(get_db)):
    """
    Actualizar pesos AHP para cálculo de masa de crimen.
    Los pesos deben sumar 1.0.
    Tras actualizar, recalcula masa_crimen para todas las localidades.
    """
    with conn.cursor() as cur:
        # Actualizar pesos
        cur.execute("""
            UPDATE iug.ahp_pesos_crimen SET peso_ahp = %s, fecha_actualizacion = now(), version = version + 1
            WHERE tipo_delito = 'homicidios'
        """, (pesos.homicidios,))
        
        cur.execute("""
            UPDATE iug.ahp_pesos_crimen SET peso_ahp = %s, fecha_actualizacion = now(), version = version + 1
            WHERE tipo_delito = 'delitos_sexuales'
        """, (pesos.delitos_sexuales,))
        
        cur.execute("""
            UPDATE iug.ahp_pesos_crimen SET peso_ahp = %s, fecha_actualizacion = now(), version = version + 1
            WHERE tipo_delito = 'hurto_personas'
        """, (pesos.hurto_personas,))
        
        cur.execute("""
            UPDATE iug.ahp_pesos_crimen SET peso_ahp = %s, fecha_actualizacion = now(), version = version + 1
            WHERE tipo_delito = 'otros_delitos'
        """, (pesos.otros_delitos,))
        
        # Recalcular masa_crimen para todas las localidades
        cur.execute("""
            UPDATE iug.criminalidad_localidad
            SET masa_crimen = 
                (homicidios_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='homicidios')) +
                (delitos_sexuales_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='delitos_sexuales')) +
                (hurto_personas_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='hurto_personas')) +
                (otros_delitos_2024 * (SELECT peso_ahp FROM iug.ahp_pesos_crimen WHERE tipo_delito='otros_delitos'))
        """)
        
        localidades_actualizadas = cur.rowcount
        conn.commit()
    
    return {
        "message": "Pesos AHP actualizados",
        "pesos": pesos.dict(),
        "localidades_recalculadas": localidades_actualizadas
    }

@router.get("/pesos-normalizacion/{tipo_inmueble}")
async def obtener_pesos_normalizacion(tipo_inmueble: str, conn = Depends(get_db)):
    """Obtener parámetros de normalización para un tipo de inmueble."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT *
            FROM iug.normalizacion_seguridad
            WHERE tipo_inmueble = %s
        """, (tipo_inmueble,))
        
        params = cur.fetchone()
    
    if not params:
        raise HTTPException(status_code=404, detail=f"Tipo inmueble '{tipo_inmueble}' no encontrado")
    
    return params

@router.put("/pesos-normalizacion/{tipo_inmueble}")
async def actualizar_pesos_normalizacion(
    tipo_inmueble: str,
    pesos: PesosNormalizacion,
    conn = Depends(get_db)
):
    """
    Actualizar pesos para combinación final del score de seguridad.
    Los pesos determinan la importancia relativa de CAI, crimen, y sectores.
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE iug.normalizacion_seguridad
            SET 
                peso_cai = %s,
                peso_crimen = %s,
                peso_sector = %s,
                fecha_actualizacion = now(),
                version = version + 1
            WHERE tipo_inmueble = %s
        """, (pesos.peso_cai, pesos.peso_crimen, pesos.peso_sector, tipo_inmueble))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Tipo inmueble '{tipo_inmueble}' no encontrado")
        
        conn.commit()
        
        # Refrescar vista materializada
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_seguridad_final")
        conn.commit()
    
    return {
        "message": f"Pesos actualizados para {tipo_inmueble}",
        "pesos": pesos.dict()
    }

@router.post("/recalcular-normalizacion")
async def recalcular_normalizacion(tipo_inmueble: Optional[str] = None, conn = Depends(get_db)):
    """
    Recalcula min/max para normalización desde el dataset actual.
    Compara todos los inmuebles para encontrar los límites reales.
    """
    with conn.cursor() as cur:
        if tipo_inmueble:
            cur.execute("SELECT iug.recalcular_normalizacion_seguridad(%s)", (tipo_inmueble,))
        else:
            cur.execute("SELECT iug.recalcular_normalizacion_seguridad(NULL)")
        
        conn.commit()
    
    return {
        "message": "Normalización recalculada desde dataset",
        "tipo_inmueble": tipo_inmueble or "todos"
    }

@router.get("/estadisticas")
async def obtener_estadisticas(conn = Depends(get_db)):
    """Estadisticas generales del indicador de seguridad."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total_inmuebles,
                COUNT(DISTINCT tipo_inmueble) as tipos_inmueble,
                AVG(score_seguridad_final) as score_promedio,
                MIN(score_seguridad_final) as score_min,
                MAX(score_seguridad_final) as score_max,
                COUNT(*) FILTER (WHERE en_sector_priorizado) as en_sectores_peligrosos,
                COUNT(*) FILTER (WHERE cais_cercanos > 0) as con_cai_cerca
            FROM iug.indicador_seguridad_final
        """)

        stats = cur.fetchone()

    return stats


# ─────────────────────────────────────────────────────────────────
# I_SEG Tridimensional y Paradoja (V117)
# ─────────────────────────────────────────────────────────────────

@router.get("/paradoja")
async def obtener_paradoja_seguridad(conn = Depends(get_db)):
    """
    Paradoja de inseguridad por localidad.

    Muestra localidades donde la percepcion de inseguridad
    no corresponde con la criminalidad objetiva.
    Util para el cliente final: identifica zonas donde la
    "sensacion" de inseguridad afecta precios aunque la
    criminalidad real sea baja.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM iug.v_paradoja_seguridad
            ORDER BY icsu_compuesto DESC
        """)
        rows = cur.fetchall()

    if not rows:
        return {
            "message": "No hay datos ICSU cargados. Ejecutar carga de icsu_localidad.",
            "data": []
        }

    return {
        "total_localidades": len(rows),
        "en_paradoja": sum(1 for r in rows if r.get('cluster_perfil') == 'bajo_alto'),
        "data": rows
    }


@router.get("/tridimensional/{id_inmueble}")
async def obtener_seguridad_tridimensional(id_inmueble: int, conn = Depends(get_db)):
    """
    Descomposicion tridimensional del I_SEG para un inmueble.

    Retorna las tres dimensiones separadas para que el cliente
    entienda de donde viene el score de seguridad:
    - Micro: proximidad a CAI y sectores priorizados
    - Objetivo: criminalidad reportada en la localidad
    - Subjetivo: percepcion de inseguridad (EPV 2024)
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Obtener geometria del inmueble
        cur.execute("""
            SELECT geom, tipo_inmueble, iseg, id_localidad
            FROM iug.inmueble
            WHERE id_inmueble = %s AND geom IS NOT NULL
        """, (id_inmueble,))
        inmueble = cur.fetchone()

        if not inmueble:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado o sin geometria")

        # Calcular tridimensional
        cur.execute("""
            SELECT * FROM iug.calcular_seguridad_tridimensional(
                (SELECT geom FROM iug.inmueble WHERE id_inmueble = %s),
                %s
            )
        """, (id_inmueble, inmueble['tipo_inmueble']))
        tri = cur.fetchone()

        # Obtener datos ICSU de la localidad
        icsu = None
        if inmueble.get('id_localidad'):
            cur.execute("""
                SELECT score_objetivo, score_subjetivo, icsu_compuesto,
                       cluster_id, cluster_perfil
                FROM iug.icsu_localidad
                WHERE id_localidad = %s
            """, (inmueble['id_localidad'],))
            icsu = cur.fetchone()

        # Obtener pesos activos
        cur.execute("""
            SELECT nombre_perfil, peso_micro, peso_objetivo, peso_subjetivo
            FROM iug.pesos_seguridad_tridimensional
            WHERE activo = TRUE LIMIT 1
        """)
        pesos = cur.fetchone()

    return {
        "id_inmueble": id_inmueble,
        "iseg_actual": float(inmueble['iseg']) if inmueble.get('iseg') else None,
        "tridimensional": {
            "score_micro": float(tri['score_micro']) if tri else None,
            "score_objetivo": float(tri['score_objetivo']) if tri else None,
            "score_subjetivo": float(tri['score_subjetivo']) if tri else None,
            "score_final": float(tri['score_final']) if tri else None,
            "localidad": tri['localidad_nombre'] if tri else None,
        } if tri else None,
        "icsu_localidad": dict(icsu) if icsu else None,
        "pesos_activos": dict(pesos) if pesos else None,
        "interpretacion": _interpretar_seguridad(tri, icsu) if tri else None,
    }


def _interpretar_seguridad(tri, icsu) -> str:
    """Genera interpretacion en lenguaje natural para el cliente."""
    if not tri:
        return "Sin datos suficientes para interpretar."

    micro = float(tri['score_micro']) if tri.get('score_micro') else 2.5
    obj = float(tri['score_objetivo']) if tri.get('score_objetivo') else 2.5
    subj = float(tri['score_subjetivo']) if tri.get('score_subjetivo') else 2.5
    final = float(tri['score_final']) if tri.get('score_final') else 2.5

    parts = []

    if final >= 4.0:
        parts.append("Zona con buen nivel de seguridad general.")
    elif final >= 3.0:
        parts.append("Zona con seguridad moderada.")
    elif final >= 2.0:
        parts.append("Zona con seguridad por debajo del promedio.")
    else:
        parts.append("Zona con problemas significativos de seguridad.")

    # Detectar paradoja
    if icsu and icsu.get('cluster_perfil') == 'bajo_alto':
        parts.append(
            "NOTA: Esta localidad presenta la 'paradoja de inseguridad': "
            "la criminalidad real es baja, pero los residentes perciben "
            "alta inseguridad. Esto puede afectar la valoracion del inmueble."
        )
    elif icsu and icsu.get('cluster_perfil') == 'alto_bajo':
        parts.append(
            "NOTA: Esta localidad tiene criminalidad alta pero los "
            "residentes reportan baja percepcion de inseguridad "
            "(posible habituacion)."
        )

    # Diferencia micro vs localidad
    if abs(micro - obj) > 1.5:
        if micro > obj:
            parts.append(
                "El entorno inmediato (CAI cercanos) es mas seguro "
                "que el promedio de la localidad."
            )
        else:
            parts.append(
                "El entorno inmediato tiene menor presencia policial "
                "que el promedio de la localidad."
            )

    return " ".join(parts)


@router.get("/perfiles-pesos")
async def obtener_perfiles_pesos(conn = Depends(get_db)):
    """Perfiles disponibles de pesos para el I_SEG tridimensional."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT nombre_perfil, descripcion,
                   peso_micro, peso_objetivo, peso_subjetivo, activo
            FROM iug.pesos_seguridad_tridimensional
            ORDER BY activo DESC, nombre_perfil
        """)
        return cur.fetchall()


@router.put("/perfiles-pesos/{nombre_perfil}/activar")
async def activar_perfil_pesos(nombre_perfil: str, conn = Depends(get_db)):
    """Activa un perfil de pesos para el calculo tridimensional."""
    with conn.cursor() as cur:
        # Desactivar todos
        cur.execute("UPDATE iug.pesos_seguridad_tridimensional SET activo = FALSE")
        # Activar el seleccionado
        cur.execute("""
            UPDATE iug.pesos_seguridad_tridimensional
            SET activo = TRUE
            WHERE nombre_perfil = %s
        """, (nombre_perfil,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Perfil '{nombre_perfil}' no encontrado")
        conn.commit()

    return {"message": f"Perfil '{nombre_perfil}' activado", "perfil": nombre_perfil}
