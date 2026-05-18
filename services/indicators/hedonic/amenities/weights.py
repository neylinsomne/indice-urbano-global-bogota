"""
Pesos de Amenities para I_Dot

Configuración de pesos para características/amenities del inmueble.

Categorías:
- Alta prioridad (2.0): Amenities de alto valor (piscina, gimnasio)
- Media prioridad (1.5): Servicios importantes (ascensor, portería)
- Baja prioridad (1.0): Características básicas (balcón, depósito)
"""

import psycopg2
from typing import Dict

# Pesos predefinidos por amenity
DEFAULT_WEIGHTS = {
    # Alta prioridad (2.0)
    'piscina': 2.0,
    'gimnasio': 2.0,
    'cancha deportiva': 2.0,
    'zona de parrilla': 1.8,
    'salón social': 1.8,
    
    # Media prioridad (1.5)
    'ascensor': 1.5,
    'portería 24 horas': 1.5,
    'zonas verdes': 1.5,
    'parqueadero cubierto': 1.5,
    'parqueadero visitantes': 1.3,
    
    # Baja prioridad (1.0)
    'balcón': 1.0,
    'terraza': 1.0,
    'depósito': 1.0,
    'cuarto útil': 1.0,
    'calentador': 1.0,
    
    # Servicios y ubicación (1.2)
    'centros comerciales cercanos': 1.2,
    'acceso pavimentado': 1.0,
    'área urbana': 0.8,
    
    # Seguridad (1.5)
    'administración': 1.5,
    'detector de humo': 1.2,
    'escalera de emergencia': 1.2,
}


def inicializar_pesos_amenities(conn: psycopg2.extensions.connection):
    """
    Inicializa tabla de pesos de amenities con valores predefinidos
    
    Usa:
        - DEFAULT_WEIGHTS para amenities conocidos
        - Peso 1.0 para amenities no configurados
    """
    with conn.cursor() as cur:
        # Obtener todas las características del catálogo
        cur.execute("""
            SELECT id_caracteristica, nombre_caracteristica
            FROM iug.cat_caracteristica
        """)
        
        caracteristicas = cur.fetchall()
        
        for id_caract, nombre in caracteristicas:
            # Buscar peso en diccionario (case-insensitive)
            nombre_lower = nombre.lower()
            peso = DEFAULT_WEIGHTS.get(nombre_lower, 1.0)
            
            # Determinar categoría automáticamente
            if peso >= 1.8:
                categoria = 'recreacion'
            elif peso >= 1.4:
                categoria = 'servicios'
            elif peso >= 1.1:
                categoria = 'ubicacion'
            else:
                categoria = 'basico'
            
            # Insertar o actualizar
            cur.execute("""
                INSERT INTO iug.pesos_amenities (
                    id_amenity,
                    nombre,
                    categoria,
                    peso,
                    activo
                ) VALUES (
                    %s, %s, %s, %s, true
                )
                ON CONFLICT (id_amenity) DO UPDATE SET
                    peso = EXCLUDED.peso,
                    categoria = EXCLUDED.categoria
            """, (id_caract, nombre, categoria, peso))
        
        conn.commit()
        print(f"[WEIGHTS] Inicializados pesos para {len(caracteristicas)} amenities")


def actualizar_peso_amenity(
    conn: psycopg2.extensions.connection,
    nombre_amenity: str,
    nuevo_peso: float
):
    """
    Actualiza el peso de un amenity específico
    
    Args:
        conn: Conexión a PostgreSQL
        nombre_amenity: Nombre del amenity (ej: 'piscina')
        nuevo_peso: Nuevo peso (0.5 - 3.0 recomendado)
    """
    with conn.cursor() as cur:
        # Buscar ID de característica
        cur.execute("""
            SELECT id_caracteristica
            FROM iug.cat_caracteristica
            WHERE LOWER(nombre_caracteristica) = LOWER(%s)
        """, (nombre_amenity,))
        
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Amenity '{nombre_amenity}' no encontrado en catálogo")
        
        id_caract = row[0]
        
        # Actualizar peso
        cur.execute("""
            UPDATE iug.pesos_amenities
            SET peso = %s
            WHERE id_amenity = %s
        """, (nuevo_peso, id_caract))
        
        conn.commit()
        print(f"[WEIGHTS] Actualizado '{nombre_amenity}' → peso {nuevo_peso}")


def obtener_pesos_por_categoria(
    conn: psycopg2.extensions.connection
) -> Dict[str, list]:
    """
    Obtiene pesos agrupados por categoría
    
    Returns:
        dict {categoria: [(nombre, peso), ...]}
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT categoria, nombre, peso
            FROM iug.pesos_amenities
            WHERE activo = true
            ORDER BY categoria, peso DESC
        """)
        
        por_categoria = {}
        for categoria, nombre, peso in cur.fetchall():
            if categoria not in por_categoria:
                por_categoria[categoria] = []
            por_categoria[categoria].append((nombre, peso))
    
    return por_categoria


# Script de inicialización
if __name__ == '__main__':
    import os
    
    DB_CONFIG = {
        'host': os.getenv('PG_HOST', 'localhost'),
        'port': os.getenv('PG_PORT', '5434'),
        'database': os.getenv('PG_DATABASE', 'postgres'),
        'user': os.getenv('PG_USER', 'postgres'),
        'password': os.getenv('PG_PASSWORD', 'postgres')
    }
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        print("Inicializando pesos de amenities...")
        inicializar_pesos_amenities(conn)
        
        print("\nPesos por categoría:")
        pesos = obtener_pesos_por_categoria(conn)
        for cat, items in pesos.items():
            print(f"\n{cat.upper()}:")
            for nombre, peso in items[:5]:  # Top 5 por categoría
                print(f"  {peso:.1f} - {nombre}")
        
        print("\n✓ Pesos inicializados correctamente")
        
    finally:
        conn.close()
