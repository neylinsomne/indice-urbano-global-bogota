"""
Normalizadores para datos de Habi.
Convierte la estructura de Habi a la estructura común para PostgreSQL.
"""
import re
import math


def clean_nan_values(obj):
    """Recursivamente reemplaza NaN e Inf con None."""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def parse_precio(valor) -> int | None:
    """Convierte precio string a entero."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        if math.isnan(valor) if isinstance(valor, float) else False:
            return None
        return int(valor)
    
    texto = str(valor).replace('.', '').replace(',', '').replace('$', '').strip()
    numeros = re.findall(r'\d+', texto)
    if numeros:
        return int(''.join(numeros))
    return None


def parse_area(valor) -> float | None:
    """Convierte área a float."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        if math.isnan(valor) if isinstance(valor, float) else False:
            return None
        return float(valor)
    
    texto = str(valor).lower().replace('m²', '').replace('m2', '').replace(',', '.').strip()
    match = re.search(r'[\d.]+', texto)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def parse_int(valor) -> int | None:
    """Convierte a entero."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        if math.isnan(valor) if isinstance(valor, float) else False:
            return None
        return int(valor)
    
    texto = str(valor).strip()
    match = re.search(r'\d+', texto)
    if match:
        return int(match.group())
    return None


def parse_estrato(valor) -> int | None:
    """Extrae estrato numérico."""
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor if 1 <= valor <= 6 else None
    
    texto = str(valor).strip()
    match = re.search(r'[1-6]', texto)
    if match:
        return int(match.group())
    return None


def normalize_habi_item(item: dict) -> dict:
    """
    Normaliza un documento de Habi a la estructura común de PostgreSQL.
    """
    # Extraer campos de la estructura de Habi
    codigo = item.get('codigo_habi') or item.get('code')
    
    # Precio
    precio = parse_precio(item.get('precio'))
    
    # Área - Habi usa "area" o puede estar en campos dinámicos
    area = parse_area(item.get('area') or item.get('area construida') or item.get('area privada'))
    
    # Habitaciones - campos dinámicos de Habi
    habitaciones = parse_int(
        item.get('habitaciones') or 
        item.get('alcobas') or 
        item.get('alcoba') or
        item.get('cuartos')
    )
    
    # Baños
    banos = parse_int(
        item.get('banos') or 
        item.get('bano') or 
        item.get('baños')
    )
    
    # Estrato
    estrato = parse_estrato(item.get('estrato') or item.get('Estrato'))
    
    # Coordenadas - Habi usa latitud/longitud
    lat = item.get('latitud') or item.get('lat')
    lon = item.get('longitud') or item.get('lon') or item.get('longitude')
    
    if lat is not None:
        try:
            lat = float(lat)
            if math.isnan(lat):
                lat = None
        except (ValueError, TypeError):
            lat = None
            
    if lon is not None:
        try:
            lon = float(lon)
            if math.isnan(lon):
                lon = None
        except (ValueError, TypeError):
            lon = None
    
    # Ubicación
    ubicacion = item.get('ubicacion') or item.get('lugar') or item.get('ciudad')
    
    # Características - extraer de campos dinámicos
    caracteristicas = []
    campos_caracteristicas = [
        'parqueadero', 'ascensor', 'vigilancia', 'gimnasio', 
        'piscina', 'zonas verdes', 'salon comunal',
        'terraza', 'balcon', 'deposito'
    ]
    for campo in campos_caracteristicas:
        valor = item.get(campo)
        if valor and str(valor).lower() not in ('no', 'false', '0', 'nan'):
            caracteristicas.append(campo.title())
    
    return {
        'pagina': 'habi',
        'codigo_fuente': str(codigo) if codigo else None,
        'precio': precio,
        'area_construida': area,
        'habitaciones': habitaciones,
        'banos': banos,
        'estrato': estrato,
        'tipo_inmueble': 'Apartamento',  # Habi solo tiene apartamentos
        'ubicacion': ubicacion,
        'direccion': item.get('direccion'),
        'lat': lat,
        'lon': lon,
        'image': item.get('imagen') or item.get('image'),
        'descripcion': item.get('descripcion'),
        'inmobiliaria': 'Habi',
        'proyecto': False,  # Habi no tiene proyectos
        'caracteristicas': caracteristicas,
    }
