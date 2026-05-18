"""
Pipeline de PostgreSQL para Habi.
Guarda datos normalizados en la misma estructura que FincaRaiz.
"""
import os
import json
import math
import logging
import psycopg2
from normalizers import normalize_habi_item, clean_nan_values

log = logging.getLogger(__name__)


class PostgreSQLPipeline:
    """Pipeline para guardar datos de Habi en PostgreSQL."""
    
    def __init__(self):
        self.conn = None
        self.stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}
    
    def connect(self):
        """Conecta a PostgreSQL."""
        postgres_uri = os.getenv('POSTGRES_URI')
        if not postgres_uri:
            # Construir URI desde variables individuales
            host = os.getenv('PG_HOST', 'localhost')
            port = os.getenv('PG_PORT', '5434')
            db = os.getenv('PG_DB', 'postgres')
            user = os.getenv('PG_USER', 'postgres')
            password = os.getenv('PG_PASSWORD', 'xd')
            postgres_uri = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        
        self.conn = psycopg2.connect(postgres_uri)
        log.info("✅ PostgreSQL conectado")
    
    def close(self):
        """Cierra conexión."""
        if self.conn:
            self.conn.close()
    
    def process_item(self, item: dict) -> dict:
        """Procesa un item de Habi y lo guarda en PostgreSQL."""
        if not self.conn:
            self.connect()
        
        # Normalizar el item
        normalized = normalize_habi_item(item)
        
        # Validar que tenga código
        if not normalized.get('codigo_fuente'):
            log.warning("Item sin codigo_fuente, saltando...")
            return item
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM iug.f_upsert_inmueble(
                        p_pagina := %s::TEXT,
                        p_codigo_fuente := %s::TEXT,
                        p_precio := %s::NUMERIC,
                        p_area_construida := %s::NUMERIC,
                        p_habitaciones := %s::SMALLINT,
                        p_banos := %s::SMALLINT,
                        p_estrato := %s::SMALLINT,
                        p_tipo_inmueble := %s::TEXT,
                        p_ubicacion := %s::TEXT,
                        p_direccion := %s::TEXT,
                        p_lat := %s::FLOAT,
                        p_lon := %s::FLOAT,
                        p_image := %s::TEXT,
                        p_descripcion := %s::TEXT,
                        p_inmobiliaria := %s::TEXT,
                        p_proyecto := %s::BOOLEAN,
                        p_raw_data := %s::JSONB
                    )
                """, (
                    clean_nan_values(normalized['pagina']),
                    clean_nan_values(normalized['codigo_fuente']),
                    clean_nan_values(normalized['precio']),
                    clean_nan_values(normalized['area_construida']),
                    clean_nan_values(normalized['habitaciones']),
                    clean_nan_values(normalized['banos']),
                    clean_nan_values(normalized['estrato']),
                    clean_nan_values(normalized['tipo_inmueble']),
                    clean_nan_values(normalized['ubicacion']),
                    clean_nan_values(normalized['direccion']),
                    clean_nan_values(normalized['lat']),
                    clean_nan_values(normalized['lon']),
                    clean_nan_values(normalized['image']),
                    clean_nan_values(normalized['descripcion']),
                    clean_nan_values(normalized['inmobiliaria']),
                    normalized['proyecto'] if normalized['proyecto'] is not None else False,
                    json.dumps(clean_nan_values(item), ensure_ascii=False, default=str)
                ))
                
                result = cur.fetchone()
                if result:
                    id_inmueble, accion, _ = result
                    self.stats[accion] = self.stats.get(accion, 0) + 1
                    
                    # Insertar características
                    self._insert_caracteristicas(cur, id_inmueble, normalized.get('caracteristicas', []))
                
                self.conn.commit()
                
        except Exception as e:
            self.conn.rollback()
            self.stats['errors'] += 1
            log.error(f"PostgreSQL error: {e}")
        
        return item
    
    def _insert_caracteristicas(self, cursor, id_inmueble: int, caracteristicas: list):
        """Inserta características en la tabla EAV."""
        if not caracteristicas:
            return
            
        for carac in caracteristicas:
            if not carac or not isinstance(carac, str):
                continue
            
            carac_clean = carac.strip()
            if not carac_clean:
                continue
                
            try:
                cursor.execute("""
                    INSERT INTO iug.inmueble_caracteristica 
                    (id_inmueble, nombre, valor_bool, fuente)
                    VALUES (%s, %s, TRUE, 'habi')
                    ON CONFLICT (id_inmueble, nombre) DO NOTHING
                """, (id_inmueble, carac_clean))
            except Exception:
                pass
    
    def get_stats(self) -> dict:
        """Retorna estadísticas."""
        return self.stats.copy()


def guardar_en_postgresql(data: list) -> dict:
    """
    Función de conveniencia para guardar una lista de items en PostgreSQL.
    Retorna estadísticas de la operación.
    """
    pipeline = PostgreSQLPipeline()
    
    try:
        pipeline.connect()
        
        for item in data:
            pipeline.process_item(item)
        
        return pipeline.get_stats()
        
    finally:
        pipeline.close()
