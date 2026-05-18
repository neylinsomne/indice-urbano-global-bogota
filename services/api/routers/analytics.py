"""
Router /analytics/*

Expone los resultados de las 9 metodologias estadisticas avanzadas
implementadas en services/api/analytics/. NO modifica el pipeline en
produccion: cada endpoint corre una simulacion sobre los datos
existentes y devuelve resultados comparativos.

Endpoints:

    GET  /analytics/methodology              -> Lista de metodologias
    GET  /analytics/gravity/calibration      -> Tabla de sigma calibrado
    GET  /analytics/gravity/{id}             -> Comparar funciones de decaimiento
    GET  /analytics/regression/diagnostics/{tipo} -> VIF + Moran + normalidad + BP
    GET  /analytics/iurb-weights/empirical   -> Pesos empiricos vs uniformes
    GET  /analytics/ahp-pca/hybrid           -> Pesos hibridos AHP-PCA
    GET  /analytics/ahp-pca/sensitivity      -> Sensibilidad al alpha
    GET  /analytics/ahp-pca/locality         -> Aplicar a localidades
    GET  /analytics/dbscan/compare/{tipo}    -> DBSCAN actual vs adaptativo vs IF
    GET  /analytics/sobol/iurb               -> Indices Sobol del IUG
    GET  /analytics/normalization/compare    -> 3 esquemas de normalizacion
    GET  /analytics/regression/1se/{tipo}    -> Seleccion 1-SE
    GET  /analytics/uncertainty/{id}         -> IC para IUG de inmueble
    GET  /analytics/uncertainty/locality/{nombre} -> IC para IUG de localidad
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from db.postgre import get_db_pool
from analytics import (
    gravity_gaussian,
    regression_diagnostics,
    iurb_weights,
    ahp_pca_hybrid,
    dbscan_adaptive,
    sensitivity_sobol,
    normalization_unified,
    regression_1se,
    uncertainty,
    iurb_validation,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


# ============================================================
# Indice de metodologias
# ============================================================

@router.get("/methodology")
def list_methodologies():
    """Lista las metodologias estadisticas implementadas."""
    return {
        "version": "1.0.0",
        "documento_referencia": "docs/tesis_definitivos/mejoras_estadisticas.tex",
        "metodologias": [
            {
                "id": 1,
                "nombre": "Funcion de gravedad gaussiana",
                "endpoint": "/analytics/gravity/{id_inmueble}",
                "referencia": "Fotheringham et al. (1989)",
            },
            {
                "id": 4,
                "nombre": "Diagnosticos regresion (VIF + Moran + Shapiro + BP)",
                "endpoint": "/analytics/regression/diagnostics/{tipo}",
                "referencia": "Anselin (1995); Hastie et al. (2009)",
            },
            {
                "id": 7,
                "nombre": "Pesos hibridos AHP-PCA para crimen",
                "endpoint": "/analytics/ahp-pca/hybrid",
                "referencia": "Saaty (1980); ICSU V117",
            },
            {
                "id": 9,
                "nombre": "Normalizacion unificada (min-max global)",
                "endpoint": "/analytics/normalization/compare",
                "referencia": "OECD Handbook (2008)",
            },
            {
                "id": 10,
                "nombre": "Pesos empiricos del IUG",
                "endpoint": "/analytics/iurb-weights/empirical",
                "referencia": "OECD Handbook (2008), Cap 6",
            },
            {
                "id": 11,
                "nombre": "Seleccion de modelo regla 1-SE",
                "endpoint": "/analytics/regression/1se/{tipo}",
                "referencia": "Hastie, Tibshirani, Friedman (2009)",
            },
            {
                "id": 12,
                "nombre": "DBSCAN adaptativo vs Isolation Forest",
                "endpoint": "/analytics/dbscan/compare/{tipo}",
                "referencia": "Ester et al. (1996); Liu et al. (2008)",
            },
            {
                "id": 14,
                "nombre": "Bandas de confianza para IUG",
                "endpoint": "/analytics/uncertainty/{id_inmueble}",
                "referencia": "Propagacion lineal Taylor",
            },
            {
                "id": 15,
                "nombre": "Indices de Sobol",
                "endpoint": "/analytics/sobol/iurb",
                "referencia": "Sobol (1993); Saltelli (2010)",
            },
            {
                "id": 16,
                "nombre": "Validacion IUG (modelos anidados + commonality + estabilidad)",
                "endpoint": "/analytics/validation/complete",
                "referencia": "Nardo et al. (2008); Nimon & Oswald (2013); Munda (2008)",
            },
        ],
    }


# ============================================================
# 1. Gravedad gaussiana
# ============================================================

@router.get("/gravity/calibration")
def gravity_calibration():
    """Tabla de sigma calibrado para todas las capas (5% utilidad en radio)."""
    return {
        "metodologia": "Calibracion gaussiana sigma = r / sqrt(2*ln(20))",
        "tabla": gravity_gaussian.tabla_calibracion_sigma(),
    }


@router.get("/gravity/{id_inmueble}")
async def gravity_compare(
    id_inmueble: int,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Compara las 3 funciones de decaimiento para un inmueble."""
    async with db.acquire() as conn:
        try:
            return await gravity_gaussian.comparar_funciones_inmueble(conn, id_inmueble)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# 4. Diagnosticos regresion
# ============================================================

@router.get("/regression/diagnostics/{tipo_inmueble}")
async def regression_diagnostics_endpoint(
    tipo_inmueble: str,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """VIF + Moran I + Shapiro-Wilk + Breusch-Pagan."""
    async with db.acquire() as conn:
        return await regression_diagnostics.diagnostico_completo_tipo(conn, tipo_inmueble)


# ============================================================
# 7. AHP-PCA hibrido
# ============================================================

@router.get("/ahp-pca/hybrid")
def ahp_pca_hybrid_endpoint(alpha: float = Query(0.5, ge=0, le=1)):
    """Pesos hibridos para tipos de delito."""
    return ahp_pca_hybrid.calcular_pesos_hibridos(alpha=alpha)


@router.get("/ahp-pca/sensitivity")
def ahp_pca_sensitivity():
    """Sensibilidad de pesos al parametro alpha."""
    return ahp_pca_hybrid.sensibilidad_alpha()


@router.get("/ahp-pca/locality")
async def ahp_pca_locality(
    alpha: float = Query(0.5, ge=0, le=1),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Recalcula masa de crimen por localidad con pesos hibridos."""
    async with db.acquire() as conn:
        return await ahp_pca_hybrid.aplicar_pesos_hibridos_localidad(conn, alpha)


# ============================================================
# 10. Pesos empiricos IUG
# ============================================================

@router.get("/iurb-weights/empirical")
async def iurb_weights_empirical(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Compara 4 metodos de derivacion de pesos vs uniformes."""
    async with db.acquire() as conn:
        return await iurb_weights.comparar_pesos_iurb(conn, tipo_inmueble)


# ============================================================
# 12. DBSCAN adaptativo
# ============================================================

@router.get("/dbscan/compare/{tipo_inmueble}")
async def dbscan_compare(
    tipo_inmueble: str,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """DBSCAN actual vs calibrado vs Isolation Forest."""
    async with db.acquire() as conn:
        return await dbscan_adaptive.comparar_metodos_outliers(conn, tipo_inmueble)


# ============================================================
# 15. Sobol
# ============================================================

@router.get("/sobol/iurb")
async def sobol_iurb(
    n_samples: int = Query(1024, ge=128, le=4096),
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Indices de Sobol para sensibilidad de pesos del IUG."""
    async with db.acquire() as conn:
        return await sensitivity_sobol.sobol_sensibilidad_iurb(
            conn, n_samples, tipo_inmueble,
        )


# ============================================================
# 9. Normalizacion unificada
# ============================================================

@router.get("/normalization/compare")
async def normalization_compare(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Compara 3 esquemas de normalizacion."""
    async with db.acquire() as conn:
        return await normalization_unified.comparar_esquemas_normalizacion(
            conn, tipo_inmueble,
        )


# ============================================================
# 11. Regla 1-SE
# ============================================================

@router.get("/regression/1se/{tipo_inmueble}")
async def regression_1se_endpoint(
    tipo_inmueble: str,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Aplica regla 1-SE a los modelos entrenados actuales."""
    async with db.acquire() as conn:
        return await regression_1se.aplicar_1se_a_modelos_actuales(conn, tipo_inmueble)


# ============================================================
# 14. Incertidumbre / Bandas de confianza
# ============================================================

@router.get("/uncertainty/{id_inmueble}")
async def uncertainty_inmueble(
    id_inmueble: int,
    sigma_gps_m: float = Query(10.0, ge=1, le=50),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Bandas de confianza para IUG de un inmueble especifico."""
    async with db.acquire() as conn:
        return await uncertainty.banda_confianza_iurb_inmueble(
            conn, id_inmueble, sigma_gps_m,
        )


@router.get("/uncertainty/locality/{nombre_localidad}")
async def uncertainty_locality(
    nombre_localidad: str,
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Bandas de confianza para IUG promedio de una localidad."""
    async with db.acquire() as conn:
        return await uncertainty.banda_confianza_localidad(conn, nombre_localidad)


# ============================================================
# 16. Validación del IUG como indicador compuesto
#     (modelos anidados, commonality, estabilidad de rankings)
# ============================================================

async def _cargar_dataset_validacion(conn, tipo_inmueble: Optional[str] = None):
    """Carga inmuebles + zonas agregadas desde PostgreSQL en dicts numpy."""
    import math as _math

    tipo_filtro = ""
    params = []
    if tipo_inmueble:
        tipo_filtro = "AND tipo_inmueble = $1"
        params.append(tipo_inmueble)

    q_inm = f"""
        SELECT id_inmueble, precio, area_construida, habitaciones, banos,
               COALESCE(estrato, 3) as estrato,
               iacc, iseg, idot, ihed, ipnu, iug, id_localidad
        FROM iug.inmueble
        WHERE precio > 0 AND area_construida > 0
          AND iacc IS NOT NULL AND iseg IS NOT NULL
          AND idot IS NOT NULL AND ihed IS NOT NULL AND ipnu IS NOT NULL
          AND iug IS NOT NULL
          AND is_outlier IS DISTINCT FROM true
          {tipo_filtro}
    """
    rows = await conn.fetch(q_inm, *params)
    if not rows:
        return None, None

    # Convertir filas a dict de listas
    cols_inm = ["precio", "area_construida", "habitaciones", "banos",
                "estrato", "iacc", "iseg", "idot", "ihed", "ipnu", "iug",
                "id_localidad"]
    data_inm = {c: [] for c in cols_inm}
    data_inm["log_precio"] = []
    for r in rows:
        for c in cols_inm:
            v = r[c]
            data_inm[c].append(float(v) if v is not None else float("nan"))
        p = r["precio"]
        data_inm["log_precio"].append(_math.log(p) if p and p > 0 else float("nan"))

    q_zonas = """
        SELECT l.id_localidad AS id_zona,
               AVG(i.iacc) as iacc, AVG(i.iseg) as iseg,
               AVG(i.idot) as idot, AVG(i.ihed) as ihed,
               AVG(i.ipnu) as ipnu
        FROM iug.inmueble i
        JOIN iug.localidad l ON l.id_localidad = i.id_localidad
        WHERE i.iacc IS NOT NULL AND i.iseg IS NOT NULL
          AND i.idot IS NOT NULL AND i.ihed IS NOT NULL AND i.ipnu IS NOT NULL
        GROUP BY l.id_localidad
        HAVING COUNT(*) >= 5
    """
    rows_z = await conn.fetch(q_zonas)
    cols_z = ["id_zona", "iacc", "iseg", "idot", "ihed", "ipnu"]
    data_zonas = {c: [] for c in cols_z}
    for r in rows_z:
        for c in cols_z:
            v = r[c]
            data_zonas[c].append(float(v) if v is not None else float("nan"))

    return data_inm, data_zonas


@router.get("/validation/nested")
async def validation_nested(
    tipo_inmueble: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Comparación de modelos anidados: IUG + controles vs subindicadores + controles."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes para validación")
        return iurb_validation.compare_nested_models(data_inm)


@router.get("/validation/commonality")
async def validation_commonality(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Commonality analysis: descomposición de varianza entre subindicadores."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.commonality_analysis(data_inm)


@router.get("/validation/ranking-stability")
async def validation_ranking_stability(
    delta: float = Query(0.20, ge=0.05, le=0.50, description="Perturbación relativa"),
    n_sim: int = Query(1000, ge=100, le=5000),
    umbral: int = Query(5, ge=1, le=20, description="Cambio mínimo de posiciones"),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Estabilidad del ranking de localidades bajo perturbación Monte Carlo de pesos."""
    async with db.acquire() as conn:
        _, data_zonas = await _cargar_dataset_validacion(conn)
        if not data_zonas:
            raise HTTPException(status_code=404, detail="Sin zonas suficientes")
        return iurb_validation.ranking_stability_mc(
            data_zonas, delta=delta, n_sim=n_sim, umbral_cambio_posiciones=umbral,
        )


@router.get("/validation/complete")
async def validation_complete(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Ejecuta las 3 pruebas de validación y devuelve la tabla de decisión."""
    async with db.acquire() as conn:
        data_inm, data_zonas = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm or not data_zonas:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.validar_iurb_completo(data_inm, data_zonas)


# ---- Pruebas de auditoría de R² y AIC (metodologías adicionales) ----

@router.get("/validation/cv-comparison")
async def validation_cv_comparison(
    tipo_inmueble: Optional[str] = Query(None),
    n_splits: int = Query(5, ge=3, le=10),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Compara R² in-sample vs CV aleatorio vs CV espacial (detecta leakage)."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.cv_comparison(data_inm, n_splits=n_splits)


@router.get("/validation/bootstrap")
async def validation_bootstrap(
    tipo_inmueble: Optional[str] = Query(None),
    n_boot: int = Query(1000, ge=200, le=5000),
    ci_level: float = Query(0.95, ge=0.80, le=0.99),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Intervalos de confianza bootstrap para R² y ΔAIC."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.bootstrap_r2_aic(
            data_inm, n_boot=n_boot, ci_level=ci_level,
        )


@router.get("/validation/ramsey")
async def validation_ramsey(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Test RESET de Ramsey para validez de la forma funcional."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.ramsey_reset(data_inm)


@router.get("/validation/subgroup")
async def validation_subgroup(
    group_col: str = Query("id_localidad", description="id_localidad (unica opcion por ahora)"),
    min_n_grupo: int = Query(50, ge=20, le=500),
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """R² por subgrupo (detecta heterogeneidad no modelada).

    Solo se permiten columnas categoricas validas como agrupador. Pasar
    columnas continuas (precio, area) genera cientos de OLS inutiles y
    responses gigantes.
    """
    # Whitelist de columnas categoricas permitidas para agrupar
    GROUP_COLS_PERMITIDAS = {"id_localidad"}
    if group_col not in GROUP_COLS_PERMITIDAS:
        raise HTTPException(
            status_code=422,
            detail=f"group_col debe ser uno de {sorted(GROUP_COLS_PERMITIDAS)}",
        )
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm or group_col not in data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.subgroup_r2(
            data_inm, group_col=group_col, min_n_grupo=min_n_grupo,
        )


@router.get("/validation/specification")
async def validation_specification(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Prueba 5 especificaciones (base/log/cuadráticos/interacciones/completa)."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.improve_specification(data_inm)


# ---- VALIDEZ DE USO: el IUG como herramienta de decisión ----

@router.get("/validation/mispricing")
async def validation_mispricing(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Detecta si el IUG correlaciona con sub/sobrevaloración del mercado."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.mispricing_analysis(data_inm)


@router.get("/validation/convergent")
async def validation_convergent(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Validez convergente (IUG vs estrato, precio/m²) y discriminante (ANOVA, AUC)."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.convergent_validity(data_inm)


@router.get("/validation/decision-matrix")
async def validation_decision_matrix(
    tipo_inmueble: Optional[str] = Query(None),
    db: asyncpg.Pool = Depends(get_db_pool),
):
    """Matriz 2×2 de decisión de inversión (IUG × mispricing)."""
    async with db.acquire() as conn:
        data_inm, _ = await _cargar_dataset_validacion(conn, tipo_inmueble)
        if not data_inm:
            raise HTTPException(status_code=404, detail="Sin datos suficientes")
        return iurb_validation.investment_decision_matrix(data_inm)
