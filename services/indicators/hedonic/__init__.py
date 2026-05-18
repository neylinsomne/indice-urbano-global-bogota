"""
Hedonic Indicator (I_HED) - Calidad Estructural Objetiva

I_HED = w_dim × I_Dim + w_dot × I_Dot

Componentes:
- I_Dim (70%): PCA de variables físicas (dimension/)
- I_Dot (30%): Conteo ponderado de amenities (amenities/)
"""

def calculate_hedonic_score(i_dim, i_dot, w_dim=0.7, w_dot=0.3):
    """
    Calcula score hedónico objetivo combinando dimensión y dotación
    
    Args:
        i_dim: Score de dimensión (0-5) desde PCA
        i_dot: Score de dotación (0-5) desde conteo amenities
        w_dim: Peso de dimensión (default 0.7)
        w_dot: Peso de dotación (default 0.3)
    
    Returns:
        float: I_HED normalizado 0-5
    """
    if i_dim is None or i_dot is None:
        return None
    
    return w_dim * i_dim + w_dot * i_dot
