"""
Cross-Validation Espacial para modelos inmobiliarios.

Herramienta independiente que puede usarse para cualquier estudio
de regresion con datos georreferenciados.

Problema que resuelve:
  En CV estandar, inmuebles del mismo edificio o cuadra pueden caer
  en folds distintos, causando data leakage espacial que infla
  artificialmente R2 y reduce RMSE.

Solucion:
  GroupKFold donde los grupos son unidades espaciales (localidad,
  barrio, o clusters geograficos).
"""
import numpy as np
import logging
from typing import Optional
from dataclasses import dataclass, field

from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.base import clone

logger = logging.getLogger(__name__)


@dataclass
class SpatialCVResult:
    """Resultado de cross-validation espacial."""
    # CV estandar (referencia)
    cv_rmse_standard: float = 0.0
    cv_r2_standard: float = 0.0
    cv_rmse_std_standard: float = 0.0

    # CV espacial
    cv_rmse_spatial: float = 0.0
    cv_r2_spatial: float = 0.0
    cv_rmse_std_spatial: float = 0.0

    # Diagnostico
    n_groups: int = 0
    n_folds: int = 0
    group_sizes: dict = field(default_factory=dict)
    leakage_ratio: float = 0.0  # spatial / standard - 1
    leakage_flag: bool = False  # True si ratio > 0.15

    def resumen(self) -> str:
        lines = [
            "=== Cross-Validation Espacial ===",
            f"  Grupos espaciales: {self.n_groups}",
            f"  Folds: {self.n_folds}",
            "",
            f"  CV estandar:  RMSE={self.cv_rmse_standard:.4f} "
            f"(+/-{self.cv_rmse_std_standard:.4f}), "
            f"R2={self.cv_r2_standard:.4f}",
            "",
            f"  CV espacial:  RMSE={self.cv_rmse_spatial:.4f} "
            f"(+/-{self.cv_rmse_std_spatial:.4f}), "
            f"R2={self.cv_r2_spatial:.4f}",
            "",
            f"  Leakage ratio: {self.leakage_ratio:+.1%}",
        ]
        if self.leakage_flag:
            lines.append(
                "  ADVERTENCIA: Leakage espacial >15%. "
                "El modelo esta memorizando barrios, no aprendiendo patrones."
            )
        return "\n".join(lines)


def spatial_cross_validate(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    model,
    n_splits: int = 5,
    standard_cv_scores: Optional[tuple] = None,
) -> SpatialCVResult:
    """
    Ejecuta cross-validation espacial usando GroupKFold.

    Puede usarse como herramienta independiente para cualquier
    modelo de regresion con datos georreferenciados.

    Args:
        X: Features (n_samples, n_features)
        y: Target (n_samples,)
        groups: Grupo espacial por muestra (n_samples,).
                Tipicamente id_localidad, id_barrio, o cluster geo.
        model: Estimador sklearn (se clona internamente).
        n_splits: Numero de folds (max = n_groups_unicos).
        standard_cv_scores: (rmse_mean, rmse_std, r2_mean) de CV estandar
                            para comparar. Si None, se calcula internamente.

    Returns:
        SpatialCVResult con diagnostico completo.
    """
    unique_groups = np.unique(groups)
    n_groups = len(unique_groups)
    actual_splits = min(n_splits, n_groups)

    if actual_splits < 2:
        logger.warning(
            f"Solo {n_groups} grupo(s) espacial(es). "
            "No se puede hacer CV espacial."
        )
        return SpatialCVResult(n_groups=n_groups, n_folds=0)

    result = SpatialCVResult(
        n_groups=n_groups,
        n_folds=actual_splits,
    )

    # Tamano de cada grupo
    for g in unique_groups:
        count = int(np.sum(groups == g))
        result.group_sizes[str(g)] = count

    # --- CV Espacial ---
    gkf = GroupKFold(n_splits=actual_splits)
    spatial_rmses = []
    spatial_r2s = []

    for train_idx, test_idx in gkf.split(X, y, groups):
        m = clone(model)
        m.fit(X[train_idx], y[train_idx])
        y_pred = m.predict(X[test_idx])

        rmse = float(np.sqrt(mean_squared_error(y[test_idx], y_pred)))
        r2 = float(r2_score(y[test_idx], y_pred))

        spatial_rmses.append(rmse)
        spatial_r2s.append(r2)

    result.cv_rmse_spatial = float(np.mean(spatial_rmses))
    result.cv_rmse_std_spatial = float(np.std(spatial_rmses))
    result.cv_r2_spatial = float(np.mean(spatial_r2s))

    # --- CV Estandar (si no se proporciono) ---
    if standard_cv_scores:
        result.cv_rmse_standard = standard_cv_scores[0]
        result.cv_rmse_std_standard = standard_cv_scores[1]
        result.cv_r2_standard = standard_cv_scores[2]
    else:
        from sklearn.model_selection import KFold
        kf = KFold(n_splits=actual_splits, shuffle=True, random_state=42)
        standard_rmses = []
        standard_r2s = []

        for train_idx, test_idx in kf.split(X, y):
            m = clone(model)
            m.fit(X[train_idx], y[train_idx])
            y_pred = m.predict(X[test_idx])

            rmse = float(np.sqrt(mean_squared_error(y[test_idx], y_pred)))
            r2 = float(r2_score(y[test_idx], y_pred))

            standard_rmses.append(rmse)
            standard_r2s.append(r2)

        result.cv_rmse_standard = float(np.mean(standard_rmses))
        result.cv_rmse_std_standard = float(np.std(standard_rmses))
        result.cv_r2_standard = float(np.mean(standard_r2s))

    # --- Diagnostico de leakage ---
    if result.cv_rmse_standard > 0:
        result.leakage_ratio = (
            (result.cv_rmse_spatial - result.cv_rmse_standard)
            / result.cv_rmse_standard
        )
        # Si RMSE espacial es >15% peor que estandar, hay leakage
        result.leakage_flag = result.leakage_ratio > 0.15

    logger.info(result.resumen())
    return result


def crear_grupos_espaciales(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    ids_localidad: Optional[np.ndarray] = None,
    ids_barrio: Optional[np.ndarray] = None,
    metodo: str = 'auto',
    n_clusters: int = 10,
) -> np.ndarray:
    """
    Crea grupos espaciales para CV a partir de coordenadas.

    Puede usarse como herramienta independiente.

    Args:
        latitudes, longitudes: Coordenadas de cada muestra.
        ids_localidad: Si disponible, usar como grupo directo.
        ids_barrio: Si disponible, usar como grupo directo.
        metodo: 'localidad', 'barrio', 'kmeans', 'auto'.
        n_clusters: Numero de clusters para K-Means.

    Returns:
        np.array de grupo por muestra.
    """
    if metodo == 'auto':
        if ids_barrio is not None and len(np.unique(ids_barrio)) >= 5:
            metodo = 'barrio'
        elif ids_localidad is not None and len(np.unique(ids_localidad)) >= 5:
            metodo = 'localidad'
        else:
            metodo = 'kmeans'

    if metodo == 'localidad' and ids_localidad is not None:
        return ids_localidad

    if metodo == 'barrio' and ids_barrio is not None:
        return ids_barrio

    # K-Means sobre coordenadas
    from sklearn.cluster import KMeans

    coords = np.column_stack([latitudes, longitudes])
    actual_k = min(n_clusters, len(coords))
    kmeans = KMeans(n_clusters=actual_k, random_state=42, n_init=10)
    return kmeans.fit_predict(coords)
