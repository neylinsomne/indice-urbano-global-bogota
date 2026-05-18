"""
Funciones de normalización de datos para el scraper de FincaRaiz.
Convierte datos crudos del scraping a formatos consistentes para PostgreSQL.
"""
import re
from typing import Optional, Union


def parse_precio(valor: Union[str, int, float, None]) -> Optional[int]:
    """
    Convierte precio a entero.
    
    Ejemplos:
        "$ 299.999.000" -> 299999000
        "299999000" -> 299999000
        299999000 -> 299999000
    """
    if valor is None:
        return None
    
    if isinstance(valor, (int, float)):
        return int(valor)
    
    if isinstance(valor, str):
        # Remover símbolos de moneda y espacios
        cleaned = valor.replace('$', '').replace(' ', '').replace('.', '').replace(',', '')
        try:
            return int(cleaned)
        except ValueError:
            return None
    
    return None


def parse_area(valor: Union[str, float, None]) -> Optional[float]:
    """
    Convierte área a float.
    
    Ejemplos:
        "25.43 m²" -> 25.43
        "25.43 m2" -> 25.43
        "25,43" -> 25.43
        25.43 -> 25.43
    """
    if valor is None:
        return None
    
    if isinstance(valor, (int, float)):
        return float(valor)
    
    if isinstance(valor, str):
        # Remover unidades y espacios
        cleaned = valor.lower().replace('m²', '').replace('m2', '').strip()
        # Manejar comas como decimales
        cleaned = cleaned.replace(',', '.')
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    return None


def parse_int(valor: Union[str, int, None]) -> Optional[int]:
    """
    Extrae entero de un string.
    
    Ejemplos:
        "1 Hab" -> 1
        "2 Baños" -> 2
        "1" -> 1
        1 -> 1
    """
    if valor is None:
        return None
    
    if isinstance(valor, int):
        return valor
    
    if isinstance(valor, str):
        # Buscar el primer número
        match = re.search(r'(\d+)', valor)
        if match:
            return int(match.group(1))
    
    return None


def parse_estrato(valor: Union[str, int, None]) -> Optional[int]:
    """
    Convierte estrato a entero (1-6).
    
    Ejemplos:
        "4" -> 4
        4 -> 4
        "Estrato 3" -> 3
    """
    result = parse_int(valor)
    if result is not None and 1 <= result <= 6:
        return result
    return None


def parse_coords(valor: Union[str, float, None]) -> Optional[float]:
    """
    Convierte coordenadas a float.
    
    Ejemplos:
        "4.6257275" -> 4.6257275
        4.6257275 -> 4.6257275
    """
    if valor is None:
        return None
    
    if isinstance(valor, (int, float)):
        return float(valor)
    
    if isinstance(valor, str):
        try:
            return float(valor.strip())
        except ValueError:
            return None
    
    return None


def normalize_tipo_inmueble(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza el tipo de inmueble a valores del catálogo.
    
    Catálogo: 'Apartamento', 'Casa', 'PH', 'Lote'
    """
    if not valor:
        return None
    
    valor_lower = valor.lower().strip()
    
    # Mapeo de variantes
    mapping = {
        'apartamento': 'Apartamento',
        'apto': 'Apartamento',
        'casa': 'Casa',
        'ph': 'PH',
        'penthouse': 'PH',
        'lote': 'Lote',
        'terreno': 'Lote',
        'bodega': 'Bodega',
        'local': 'Local',
        'oficina': 'Oficina',
        'finca': 'Finca',
    }
    
    for key, normalized in mapping.items():
        if key in valor_lower:
            return normalized
    
    # Si no matchea, retornar capitalizado
    return valor.strip().title()


def normalize_estado(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza el estado del inmueble.
    
    Catálogo: 'Nuevos', 'Usados', 'En construcción'
    """
    if not valor:
        return None
    
    valor_lower = valor.lower().strip()
    
    if 'nuevo' in valor_lower:
        return 'Nuevos'
    elif 'construcción' in valor_lower or 'construccion' in valor_lower:
        return 'En construcción'
    elif 'usado' in valor_lower or 'buen estado' in valor_lower:
        return 'Usados'
    
    return valor.strip()


def normalize_item(item: dict) -> dict:
    """
    Normaliza todos los campos de un item scrapeado.
    
    Args:
        item: Dict con datos crudos del scraper
        
    Returns:
        Dict con datos normalizados para PostgreSQL
    """
    return {
        # Identificadores
        'pagina': item.get('pagina', 'finca_raiz'),
        'codigo_fuente': str(item.get('codigo_fr', '')),
        
        # Precio y áreas (normalizados)
        'precio': parse_precio(item.get('precio')),
        'area_construida': parse_area(item.get('area_construida')),
        'area_privada': parse_area(item.get('area_privada')),
        
        # Enteros
        'habitaciones': parse_int(item.get('habitaciones')),
        'banos': parse_int(item.get('banos')),
        'estrato': parse_estrato(item.get('estrato')),
        
        # Tipo y estado (catálogos)
        'tipo_inmueble': normalize_tipo_inmueble(item.get('tipo_de_inmueble') or item.get('tipo_inmueble')),
        'estado': normalize_estado(item.get('estado')),
        
        # Ubicación
        'ubicacion': item.get('ubicacion'),
        'ubicacion_asociada': item.get('ubicacion_asociada'),
        'direccion': item.get('direccion'),
        'lat': parse_coords(item.get('latitud')),
        'lon': parse_coords(item.get('longitud')),
        
        # Otros
        'image': item.get('image'),
        'descripcion': item.get('descripcion'),
        'inmobiliaria': item.get('inmobiliaria'),
        'proyecto': item.get('proyecto', False),
        
        # Características (lista)
        'caracteristicas': item.get('caracteristicas', []),
        
        # Raw data para referencia
        'raw_data': item,
    }
