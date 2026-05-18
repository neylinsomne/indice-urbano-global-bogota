"""
Servicio de calculo de PCA para indicadores de transporte

Calcula pesos de Primera Componente Principal usando scikit-learn
y actualiza la tabla pca_pesos_tipo en PostgreSQL.

Incluye validacion estadistica obligatoria (KMO, Bartlett) y
fallback automatico cuando PCA no es valido.
"""
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler
import asyncpg
import logging
from typing import Optional, Dict, Any

from services.api.services.pca_validator import (
    validar_pca, calcular_con_fallback, bootstrap_loadings
)

logger = logging.getLogger(__name__)

# Minimo de muestras: ratio n/p >= 10 con 4 features = 40
MIN_MUESTRAS_DEFAULT = 40


class PCAService:
    """
    Servicio para calcular pesos PCA de indicadores de transporte.

    Flujo:
    1. Obtiene todos los scores raw de un tipo de inmueble
    2. Valida estructura estadistica (KMO, Bartlett)
    3. Aplica PCA o fallback segun validacion
    4. Calcula bootstrap de estabilidad de loadings
    5. Actualiza tabla pca_pesos_tipo
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def calcular_pesos_por_tipo(
        self,
        tipo_inmueble: str,
        min_muestras: int = MIN_MUESTRAS_DEFAULT
    ) -> Optional[Dict[str, Any]]:
        """
        Calcula y actualiza pesos PCA para un tipo de inmueble.

        Incluye validacion KMO/Bartlett obligatoria y fallback
        automatico si PCA no es estadisticamente valido.

        Args:
            tipo_inmueble: 'Apartamento', 'Casa', 'Lote', etc.
            min_muestras: Minimo de inmuebles requeridos (default 40)

        Returns:
            Dict con resultados o None si no hay suficientes datos
        """
        async with self.db_pool.acquire() as conn:
            # 1. Obtener scores raw
            rows = await conn.fetch("""
                SELECT
                    id_inmueble,
                    score_transmilenio_raw,
                    score_sitp_raw,
                    score_vias_raw,
                    score_parques_raw
                FROM iug.indicador_transporte_raw
                WHERE tipo_inmueble = $1
                  AND score_transmilenio_raw IS NOT NULL
                  AND score_sitp_raw IS NOT NULL
                ORDER BY id_inmueble
            """, tipo_inmueble)

            if len(rows) < min_muestras:
                logger.warning(
                    f"Tipo '{tipo_inmueble}': Solo {len(rows)} muestras "
                    f"(minimo {min_muestras}). PCA no calculado."
                )
                return None

            # 2. Convertir a matriz numpy (filtrar NaN)
            feature_names = ['transmilenio', 'sitp', 'vias', 'parques']
            raw_data = []
            for r in rows:
                vals = [
                    r['score_transmilenio_raw'],
                    r['score_sitp_raw'],
                    r['score_vias_raw'],
                    r['score_parques_raw']
                ]
                if all(v is not None for v in vals):
                    raw_data.append([float(v) for v in vals])

            if len(raw_data) < min_muestras:
                logger.warning(
                    f"Tipo '{tipo_inmueble}': Solo {len(raw_data)} muestras "
                    f"validas despues de filtrar NaN."
                )
                return None

            X = np.array(raw_data)

            # 3. Validacion + calculo con fallback automatico
            resultado_pca = calcular_con_fallback(
                X, nombres=feature_names, n_components=1, min_kmo=0.50
            )

            validacion = resultado_pca['validacion']
            metodo = resultado_pca['metodo']
            pesos_dict = resultado_pca['pesos']
            pesos = np.array([pesos_dict[n] for n in feature_names])
            varianza_explicada = resultado_pca['varianza_explicada']

            # 4. Bootstrap de estabilidad (solo si PCA fue valido)
            bootstrap_info = None
            if metodo in ('pca', 'pca_robusto') and len(X) >= 30:
                bootstrap_info = bootstrap_loadings(X, feature_names, n_bootstrap=200)

            # 5. Calcular PC1 values para min/max
            from sklearn.preprocessing import RobustScaler as RS
            scaler = RS()
            Z = scaler.fit_transform(X)
            pc1_values = Z @ pesos
            pc1_min = float(pc1_values.min())
            pc1_max = float(pc1_values.max())

            # 6. Actualizar tabla pca_pesos_tipo (con metricas de validacion)
            import json as _json
            await conn.execute("""
                INSERT INTO iug.pca_pesos_tipo (
                    tipo_inmueble,
                    peso_transmilenio,
                    peso_sitp,
                    peso_vias,
                    peso_parques,
                    pc1_min,
                    pc1_max,
                    pca_version,
                    total_muestras,
                    varianza_explicada,
                    kmo,
                    bartlett_p,
                    metodo_usado,
                    advertencias,
                    fecha_actualizacion
                ) VALUES ($1, $2, $3, $4, $5, $6, $7,
                         (SELECT COALESCE(MAX(pca_version), 0) + 1 FROM iug.pca_pesos_tipo WHERE tipo_inmueble = $1),
                         $8, $9, $10, $11, $12, $13::jsonb, now())
                ON CONFLICT (tipo_inmueble) DO UPDATE SET
                    peso_transmilenio = EXCLUDED.peso_transmilenio,
                    peso_sitp = EXCLUDED.peso_sitp,
                    peso_vias = EXCLUDED.peso_vias,
                    peso_parques = EXCLUDED.peso_parques,
                    pc1_min = EXCLUDED.pc1_min,
                    pc1_max = EXCLUDED.pc1_max,
                    pca_version = EXCLUDED.pca_version,
                    total_muestras = EXCLUDED.total_muestras,
                    varianza_explicada = EXCLUDED.varianza_explicada,
                    kmo = EXCLUDED.kmo,
                    bartlett_p = EXCLUDED.bartlett_p,
                    metodo_usado = EXCLUDED.metodo_usado,
                    advertencias = EXCLUDED.advertencias,
                    fecha_actualizacion = now()
            """, tipo_inmueble, float(pesos[0]), float(pesos[1]),
                 float(pesos[2]), float(pesos[3]), pc1_min, pc1_max,
                 len(raw_data), varianza_explicada,
                 validacion.kmo, validacion.bartlett_p,
                 metodo,
                 _json.dumps(validacion.advertencias))

            resultado = {
                "tipo_inmueble": tipo_inmueble,
                "total_muestras": len(raw_data),
                "metodo_usado": metodo,
                "pesos": pesos_dict,
                "pc1_range": [pc1_min, pc1_max],
                "varianza_explicada": varianza_explicada,
                "validacion": {
                    "kmo": validacion.kmo,
                    "bartlett_p": validacion.bartlett_p,
                    "valido_pca": validacion.valido,
                    "advertencias": validacion.advertencias,
                },
            }

            if bootstrap_info:
                resultado["bootstrap_estabilidad"] = bootstrap_info

            logger.info(
                f"PCA [{metodo}] para '{tipo_inmueble}': "
                f"{len(raw_data)} muestras, KMO={validacion.kmo:.3f}, "
                f"varianza={varianza_explicada:.2%}"
            )

            return resultado
    
    async def calcular_todos_los_tipos(self) -> Dict[str, Any]:
        """
        Calcula PCA para todos los tipos de inmueble con datos suficientes.
        
        Returns:
            Dict con resultados por tipo
        """
        # Obtener tipos únicos
        async with self.db_pool.acquire() as conn:
            tipos = await conn.fetch("""
                SELECT DISTINCT tipo_inmueble, COUNT(*) as total
                FROM iug.indicador_transporte_raw
                WHERE score_transmilenio_raw IS NOT NULL
                GROUP BY tipo_inmueble
                ORDER BY total DESC
            """)
        
        resultados = {}
        for row in tipos:
            tipo = row['tipo_inmueble']
            resultado = await self.calcular_pesos_por_tipo(tipo)
            if resultado:
                resultados[tipo] = resultado
        
        return resultados


# Instancia global (se inicializa en main.py)
_pca_service: Optional[PCAService] = None


def init_pca_service(db_pool: asyncpg.Pool):
    """Inicializa el servicio PCA (llamar en startup)"""
    global _pca_service
    _pca_service = PCAService(db_pool)


def get_pca_service() -> PCAService:
    """Obtiene la instancia del servicio PCA"""
    if _pca_service is None:
        raise RuntimeError("PCAService no inicializado. Llamar init_pca_service() primero.")
    return _pca_service
