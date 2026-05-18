from pydantic import BaseModel
from typing import List, Dict, Any

class InputModel(BaseModel):
    pesos: Dict[str, float]
    columnas: List[str]
    barrio: str

class OutputModel(BaseModel):
    codigo_busqueda: str
    geometry: str
    weighted_score: float
