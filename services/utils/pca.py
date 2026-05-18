"""
PCA (Principal Component Analysis) Utilities

Funciones genéricas para PCA reutilizables entre indicadores.
"""

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA as SklearnPCA
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from typing import Dict, Tuple, Optional


def calculate_pca(
    X: pd.DataFrame,
    n_components: int = 1,
    impute_strategy: str = 'median'
) -> Dict:
    """
    Calcula PCA de manera genérica
    
    Args:
        X: DataFrame con variables
        n_components: Número de componentes (default 1)
        impute_strategy: 'median', 'mean', 'most_frequent'
    
    Returns:
        dict con 'pca', 'scaler', 'imputer', 'loadings', 'explained_variance', 'scores'
    """
    X_copy = X.copy()
    
    # 1. Imputar valores faltantes
    imputer = SimpleImputer(strategy=impute_strategy)
    X_imputed = imputer.fit_transform(X_copy)
    X_imputed = pd.DataFrame(X_imputed, columns=X.columns, index=X.index)
    
    # 2. Estandarizar (Z-score)
    scaler = StandardScaler()
    Z = scaler.fit_transform(X_imputed)
    
    # 3. Calcular PCA
    pca = SklearnPCA(n_components=n_components)
    scores = pca.fit_transform(Z)
    
    # 4. Extraer loadings
    loadings = pca.components_  # shape: (n_components, n_features)
    
    return {
        'pca': pca,
        'scaler': scaler,
        'imputer': imputer,
        'loadings': loadings,
        'explained_variance': pca.explained_variance_ratio_,
        'scores': scores,
        'feature_names': list(X.columns)
    }


def apply_pca_transform(
    X: pd.DataFrame,
    loadings: np.ndarray,
    scaler_params: Dict,
    imputer: Optional[SimpleImputer] = None
) -> np.ndarray:
    """
    Aplica PCA ya entrenado a nuevos datos
    
    Args:
        X: DataFrame con variables
        loadings: Cargas factoriales (phi) de componentes
        scaler_params: dict con 'mean' y 'scale' por variable
        imputer: SimpleImputer ya entrenado (opcional)
    
    Returns:
        np.ndarray: Scores de componentes principales
    """
    X_copy = X.copy()
    
    # 1. Imputar si se provee imputer
    if imputer is not None:
        X_imputed = imputer.transform(X_copy)
        X_imputed = pd.DataFrame(X_imputed, columns=X.columns)
    else:
        X_imputed = X_copy.fillna(0)  # Fallback simple
    
    # 2. Estandarizar manualmente
    Z = np.zeros_like(X_imputed, dtype=float)
    for i, col in enumerate(X_imputed.columns):
        mean = scaler_params['mean'][col]
        scale = scaler_params['scale'][col]
        
        if scale > 0:
            Z[:, i] = (X_imputed[col] - mean) / scale
        else:
            Z[:, i] = 0
    
    # 3. Aplicar loadings: PC = Σ(φ_j * Z_j)
    scores = Z @ loadings.T
    
    return scores


def get_pca_interpretation(loadings: np.ndarray, feature_names: list) -> pd.DataFrame:
    """
    Genera tabla interpretativa de loadings
    
    Returns:
        DataFrame con feature, loading, abs_loading ordenado por importancia
    """
    n_components, n_features = loadings.shape
    
    interpretations = []
    for i in range(n_components):
        comp_loadings = loadings[i, :]
        
        for j, feature in enumerate(feature_names):
            interpretations.append({
                'component': f'PC{i+1}',
                'feature': feature,
                'loading': comp_loadings[j],
                'abs_loading': abs(comp_loadings[j])
            })
    
    df = pd.DataFrame(interpretations)
    df = df.sort_values(['component', 'abs_loading'], ascending=[True, False])
    
    return df
