"""
Validador estadistico para PCA.

Herramienta independiente que puede usarse antes de cualquier PCA
en el sistema (transporte, dimension, seguridad, o estudios individuales).

Implementa:
- Test KMO (Kaiser-Meyer-Olkin)
- Test de esfericidad de Bartlett
- Criterio de Kaiser (autovalores > 1)
- Bootstrap de estabilidad de loadings
- Fallback automatico cuando PCA no es valido
"""
import numpy as np
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PCAValidationResult:
    """Resultado de la validacion pre-PCA."""
    valido: bool
    metodo_recomendado: str  # 'pca', 'pca_robusto', 'varianza', 'promedio'
    kmo: float = 0.0
    kmo_por_variable: dict = field(default_factory=dict)
    bartlett_chi2: float = 0.0
    bartlett_p: float = 1.0
    n_muestras: int = 0
    n_variables: int = 0
    ratio_n_p: float = 0.0
    eigenvalues: list = field(default_factory=list)
    n_componentes_kaiser: int = 0
    varianza_pc1: float = 0.0
    advertencias: list = field(default_factory=list)

    def resumen(self) -> str:
        lines = [
            f"=== Validacion PCA (n={self.n_muestras}, p={self.n_variables}) ===",
            f"  KMO global:  {self.kmo:.4f} ({_interpretar_kmo(self.kmo)})",
            f"  Bartlett:    chi2={self.bartlett_chi2:.2f}, p={self.bartlett_p:.6f}",
            f"  Ratio n/p:   {self.ratio_n_p:.1f}",
            f"  PC1 varianza: {self.varianza_pc1:.1%}",
            f"  Componentes Kaiser (eigenvalue>1): {self.n_componentes_kaiser}",
            f"  Metodo recomendado: {self.metodo_recomendado}",
            f"  Valido para PCA: {'SI' if self.valido else 'NO'}",
        ]
        if self.advertencias:
            lines.append("  Advertencias:")
            for w in self.advertencias:
                lines.append(f"    - {w}")
        return "\n".join(lines)


def _interpretar_kmo(kmo: float) -> str:
    if kmo >= 0.90:
        return "Maravilloso"
    elif kmo >= 0.80:
        return "Meritorio"
    elif kmo >= 0.70:
        return "Aceptable"
    elif kmo >= 0.60:
        return "Mediocre"
    elif kmo >= 0.50:
        return "Miserable"
    else:
        return "Inaceptable"


def calcular_kmo(X: np.ndarray, nombres: Optional[list] = None) -> tuple:
    """
    Calcula el indice KMO (Kaiser-Meyer-Olkin).

    KMO mide la proporcion de varianza que podria ser causada por
    factores subyacentes. Valores altos (>0.60) indican que PCA
    es adecuado.

    Returns:
        (kmo_por_variable, kmo_global)
    """
    n, p = X.shape
    if nombres is None:
        nombres = [f"var_{i}" for i in range(p)]

    # Matriz de correlacion
    corr = np.corrcoef(X, rowvar=False)

    # Matriz de correlacion parcial (inversa de la correlacion)
    try:
        inv_corr = np.linalg.inv(corr)
    except np.linalg.LinAlgError:
        # Matriz singular - agregar regularizacion
        inv_corr = np.linalg.inv(corr + np.eye(p) * 1e-6)

    # Correlaciones parciales
    D = np.diag(1.0 / np.sqrt(np.diag(inv_corr)))
    partial_corr = -D @ inv_corr @ D
    np.fill_diagonal(partial_corr, 0)

    # KMO por variable y global
    corr_sq = corr ** 2
    np.fill_diagonal(corr_sq, 0)
    partial_sq = partial_corr ** 2

    sum_corr_sq = corr_sq.sum(axis=0)
    sum_partial_sq = partial_sq.sum(axis=0)

    kmo_vars = {}
    for i, name in enumerate(nombres):
        denom = sum_corr_sq[i] + sum_partial_sq[i]
        kmo_vars[name] = float(sum_corr_sq[i] / denom) if denom > 0 else 0.0

    total_corr = corr_sq.sum()
    total_partial = partial_sq.sum()
    kmo_global = float(total_corr / (total_corr + total_partial)) if (total_corr + total_partial) > 0 else 0.0

    return kmo_vars, kmo_global


def test_bartlett(X: np.ndarray) -> tuple:
    """
    Test de esfericidad de Bartlett.

    H0: La matriz de correlacion es una identidad (variables no correlacionadas).
    Si p < alpha, rechazamos H0 y PCA es justificable.

    Returns:
        (chi2, p_value)
    """
    from scipy import stats as sp_stats

    n, p = X.shape
    corr = np.corrcoef(X, rowvar=False)

    # Estadistico chi-cuadrado
    det_corr = np.linalg.det(corr)
    if det_corr <= 0:
        det_corr = 1e-300  # Evitar log(0)

    chi2 = -((n - 1) - (2 * p + 5) / 6) * np.log(det_corr)
    df = p * (p - 1) / 2
    p_value = 1.0 - sp_stats.chi2.cdf(chi2, df)

    return float(chi2), float(p_value)


def validar_pca(
    X: np.ndarray,
    nombres: Optional[list] = None,
    alpha: float = 0.05,
    min_kmo: float = 0.50,
    min_varianza_pc1: float = 0.40,
) -> PCAValidationResult:
    """
    Protocolo completo de validacion previo a PCA.

    Puede usarse como herramienta individual para cualquier estudio
    de analisis factorial.

    Args:
        X: Matriz de datos (n_muestras x n_variables), ya sin NaN.
        nombres: Nombres de las variables.
        alpha: Nivel de significancia para Bartlett.
        min_kmo: KMO minimo aceptable.
        min_varianza_pc1: Varianza minima que debe explicar PC1.

    Returns:
        PCAValidationResult con diagnostico completo.
    """
    n, p = X.shape
    if nombres is None:
        nombres = [f"var_{i}" for i in range(p)]

    result = PCAValidationResult(
        valido=True,
        metodo_recomendado='pca',
        n_muestras=n,
        n_variables=p,
        ratio_n_p=round(n / max(p, 1), 2),
    )

    # --- 1. Ratio n/p ---
    if n / p < 3:
        result.advertencias.append(
            f"n/p = {n/p:.1f} < 3. Muestra critica: resultados muy inestables."
        )
    elif n / p < 5:
        result.advertencias.append(
            f"n/p = {n/p:.1f} < 5. Muestra pequena: resultados inestables."
        )

    if n < 20:
        result.advertencias.append(
            f"n = {n} < 20. Considerar metodos bayesianos o promedio ponderado."
        )

    # --- 2. KMO ---
    try:
        kmo_vars, kmo_global = calcular_kmo(X, nombres)
        result.kmo = kmo_global
        result.kmo_por_variable = kmo_vars

        if kmo_global < min_kmo:
            result.valido = False
            result.advertencias.append(
                f"KMO = {kmo_global:.4f} < {min_kmo}: "
                f"{_interpretar_kmo(kmo_global)}. PCA no recomendado."
            )

        # Variables individuales con KMO bajo
        for name, kmo_v in kmo_vars.items():
            if kmo_v < 0.50:
                result.advertencias.append(
                    f"KMO({name}) = {kmo_v:.3f} < 0.50: considerar eliminar."
                )
    except Exception as e:
        result.advertencias.append(f"Error calculando KMO: {e}")
        result.kmo = 0.0

    # --- 3. Bartlett ---
    try:
        chi2, p_val = test_bartlett(X)
        result.bartlett_chi2 = chi2
        result.bartlett_p = p_val

        if p_val > alpha:
            result.valido = False
            result.advertencias.append(
                f"Bartlett p = {p_val:.6f} > {alpha}: "
                "correlaciones no significativas. PCA no justificado."
            )
    except Exception as e:
        result.advertencias.append(f"Error en test de Bartlett: {e}")

    # --- 4. Autovalores (Kaiser) ---
    try:
        corr = np.corrcoef(X, rowvar=False)
        eigenvalues = np.sort(np.linalg.eigvalsh(corr))[::-1]
        result.eigenvalues = [round(float(ev), 4) for ev in eigenvalues]
        result.n_componentes_kaiser = int(np.sum(eigenvalues > 1.0))
        result.varianza_pc1 = float(eigenvalues[0] / eigenvalues.sum())

        if result.varianza_pc1 < min_varianza_pc1:
            result.advertencias.append(
                f"PC1 explica solo {result.varianza_pc1:.1%} "
                f"(minimo {min_varianza_pc1:.0%}). "
                "Un solo componente puede ser insuficiente."
            )

        if result.n_componentes_kaiser == 0:
            result.advertencias.append(
                "Ningun autovalor > 1.0. La estructura factorial es debil."
            )
    except Exception as e:
        result.advertencias.append(f"Error calculando autovalores: {e}")

    # --- 5. Determinar metodo recomendado ---
    if result.valido:
        result.metodo_recomendado = 'pca'
    elif result.kmo >= 0.50 and result.bartlett_p <= alpha:
        # KMO marginal pero correlaciones significativas
        result.metodo_recomendado = 'pca_robusto'
        result.advertencias.append(
            "Se recomienda PCA robusto (RobustScaler + MCD) "
            "por KMO marginal."
        )
    elif result.kmo >= 0.40:
        # Fallback: pesos proporcionales a varianza
        result.metodo_recomendado = 'varianza'
        result.advertencias.append(
            "Fallback: usar pesos proporcionales a la varianza "
            "de cada variable (sin extraccion factorial)."
        )
    else:
        result.metodo_recomendado = 'promedio'
        result.advertencias.append(
            "Fallback: usar promedio simple (pesos iguales)."
        )

    return result


def calcular_con_fallback(
    X: np.ndarray,
    nombres: Optional[list] = None,
    n_components: int = 1,
    min_kmo: float = 0.50,
) -> dict:
    """
    Calcula scores dimensionales con validacion y fallback automatico.

    Puede usarse como herramienta independiente para cualquier
    analisis de reduccion de dimensionalidad.

    Returns:
        {
            'metodo': 'pca' | 'pca_robusto' | 'varianza' | 'promedio',
            'scores': np.array (n_muestras,),
            'pesos': np.array (n_variables,),
            'validacion': PCAValidationResult,
            'varianza_explicada': float,
        }
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler, RobustScaler

    n, p = X.shape
    if nombres is None:
        nombres = [f"var_{i}" for i in range(p)]

    validacion = validar_pca(X, nombres, min_kmo=min_kmo)
    logger.info(validacion.resumen())

    metodo = validacion.metodo_recomendado

    if metodo == 'pca':
        scaler = StandardScaler()
        Z = scaler.fit_transform(X)
        pca = PCA(n_components=n_components)
        scores = pca.fit_transform(Z).flatten()
        pesos = pca.components_[0]
        var_exp = float(pca.explained_variance_ratio_[0])

    elif metodo == 'pca_robusto':
        # RobustScaler usa mediana e IQR (resistente a outliers)
        scaler = RobustScaler()
        Z = scaler.fit_transform(X)
        pca = PCA(n_components=n_components)
        scores = pca.fit_transform(Z).flatten()
        pesos = pca.components_[0]
        var_exp = float(pca.explained_variance_ratio_[0])

    elif metodo == 'varianza':
        # Pesos proporcionales a la varianza de cada variable
        scaler = StandardScaler()
        Z = scaler.fit_transform(X)
        variances = np.var(X, axis=0)
        pesos = variances / variances.sum()
        scores = Z @ pesos
        var_exp = float(np.var(scores) / np.sum(np.var(Z, axis=0)))

    else:  # 'promedio'
        scaler = StandardScaler()
        Z = scaler.fit_transform(X)
        pesos = np.ones(p) / p
        scores = Z @ pesos
        var_exp = float(np.var(scores) / np.sum(np.var(Z, axis=0)))

    return {
        'metodo': metodo,
        'scores': scores,
        'pesos': {nombre: float(w) for nombre, w in zip(nombres, pesos)},
        'validacion': validacion,
        'varianza_explicada': var_exp,
    }


def bootstrap_loadings(
    X: np.ndarray,
    nombres: Optional[list] = None,
    n_bootstrap: int = 200,
    ci: float = 0.95,
) -> dict:
    """
    Estabilidad de loadings PCA via bootstrap.

    Herramienta independiente para evaluar la confiabilidad de
    los pesos extraidos por PCA.

    Returns:
        {variable: {'loading': float, 'ci_lower': float, 'ci_upper': float, 'se': float}}
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    n, p = X.shape
    if nombres is None:
        nombres = [f"var_{i}" for i in range(p)]

    alpha = (1 - ci) / 2
    all_loadings = []

    for _ in range(n_bootstrap):
        idx = np.random.choice(n, size=n, replace=True)
        X_boot = X[idx]

        try:
            scaler = StandardScaler()
            Z = scaler.fit_transform(X_boot)
            pca = PCA(n_components=1)
            pca.fit(Z)
            loadings = pca.components_[0]
            all_loadings.append(loadings)
        except Exception:
            continue

    if len(all_loadings) < 50:
        return {name: {'loading': 0, 'ci_lower': 0, 'ci_upper': 0, 'se': 0}
                for name in nombres}

    all_loadings = np.array(all_loadings)

    # Corregir sign-flipping: alinear con la primera muestra
    for i in range(1, len(all_loadings)):
        if np.dot(all_loadings[0], all_loadings[i]) < 0:
            all_loadings[i] *= -1

    result = {}
    for j, name in enumerate(nombres):
        col = all_loadings[:, j]
        result[name] = {
            'loading': round(float(np.mean(col)), 6),
            'ci_lower': round(float(np.percentile(col, alpha * 100)), 6),
            'ci_upper': round(float(np.percentile(col, (1 - alpha) * 100)), 6),
            'se': round(float(np.std(col)), 6),
        }

    return result
