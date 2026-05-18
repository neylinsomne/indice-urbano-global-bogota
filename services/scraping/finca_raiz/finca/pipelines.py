from pymongo import MongoClient
import pymongo
import logging
import json
import os
from scrapy.utils.project import get_project_settings
from itemadapter import ItemAdapter

import math

# Importar normalizadores
try:
    from finca.normalizers import normalize_item
except ImportError:
    from normalizers import normalize_item


def clean_nan_values(obj):
    """
    Recursivamente reemplaza NaN e Inf con None para JSON válido.
    """
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


class MongoDBPipeline:
    """Pipeline para guardar datos crudos en MongoDB (backup)."""
    
    def __init__(self, mongo_uri, mongo_conexion):
        self.mongo_uri = mongo_uri
        self.mongo_conexion = mongo_conexion
        self.client = None
        self.db = None
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGODB_URI"),
            mongo_conexion=crawler.settings.get("MONGO_CONEXION")
        )

    def open_spider(self, spider):
        if self.mongo_uri:
            self.client = pymongo.MongoClient(self.mongo_uri)
            self.db = self.client[spider.sector]
            self.logger.info(f"MongoDB conectado: {spider.sector}")
        else:
            self.logger.warning("MONGODB_URI no configurado, MongoDB deshabilitado")

    def close_spider(self, spider):
        if self.client is not None:
            self.client.close()

    def process_item(self, item, spider):
        if self.client is None or self.db is None:
            return item
            
        adapter = ItemAdapter(item)

        # Verificaciones básicas
        if not hasattr(spider, 'sector') or not hasattr(spider, 'trans_completa'):
            self.logger.warning("Spider sin atributos sector/trans_completa")
            return item

        if self.mongo_conexion is None:
            return item

        if spider.sector not in self.mongo_conexion:
            return item

        if spider.trans_completa not in self.mongo_conexion[spider.sector]:
            return item

        # Insertar en MongoDB
        collection_name = spider.trans_completa
        collection = self.db[collection_name]

        try:
            result = collection.insert_one(adapter.asdict())
            self.logger.debug(f"MongoDB: insertado {result.inserted_id}")
        except Exception as e:
            self.logger.error(f"MongoDB error: {e}")

        return item


class PostgreSQLPipeline:
    """
    Pipeline para guardar datos normalizados en PostgreSQL.
    Usa la función iug.f_upsert_inmueble() para upsert inteligente.
    """
    
    def __init__(self, postgres_uri):
        self.postgres_uri = postgres_uri
        self.conn = None
        self.logger = logging.getLogger(__name__)
        self.stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            postgres_uri=crawler.settings.get("POSTGRES_URI")
        )

    def open_spider(self, spider):
        if not self.postgres_uri:
            self.logger.warning("POSTGRES_URI no configurado, PostgreSQL deshabilitado")
            return
            
        try:
            import psycopg2
            self.conn = psycopg2.connect(self.postgres_uri)
            self.conn.autocommit = False
            self.logger.info("PostgreSQL conectado")
        except ImportError:
            self.logger.error("psycopg2 no instalado")
        except Exception as e:
            self.logger.error(f"PostgreSQL conexión fallida: {e}")

    def close_spider(self, spider):
        if self.conn:
            self.conn.close()
            self.logger.info(f"PostgreSQL stats: {self.stats}")

    def process_item(self, item, spider):
        if not self.conn:
            return item
            
        adapter = ItemAdapter(item)
        raw_item = adapter.asdict()
        
        # Normalizar datos
        normalized = normalize_item(raw_item)
        
        try:
            with self.conn.cursor() as cur:
                # Llamar a la función de upsert con tipos explícitos
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
                    normalized['pagina'] or 'finca_raiz',
                    normalized['codigo_fuente'],
                    normalized['precio'],
                    normalized['area_construida'],
                    normalized['habitaciones'],
                    normalized['banos'],
                    normalized['estrato'],
                    normalized['tipo_inmueble'],
                    normalized['ubicacion'],
                    normalized['direccion'],
                    normalized['lat'],
                    normalized['lon'],
                    normalized['image'],
                    normalized['descripcion'],
                    normalized['inmobiliaria'],
                    normalized['proyecto'] if normalized['proyecto'] is not None else False,
                    json.dumps(clean_nan_values(raw_item), ensure_ascii=False, default=str)
                ))
                
                result = cur.fetchone()
                if result:
                    id_inmueble, accion, cambios = result
                    self.stats[accion] = self.stats.get(accion, 0) + 1
                    self.logger.debug(f"PostgreSQL: {accion} id={id_inmueble}")
                    
                    # Insertar características
                    self._insert_caracteristicas(cur, id_inmueble, normalized.get('caracteristicas', []))
                
                self.conn.commit()
                
        except Exception as e:
            self.conn.rollback()
            self.stats['errors'] += 1
            self.logger.error(f"PostgreSQL error: {e}")
        
        return item
    
    def _insert_caracteristicas(self, cursor, id_inmueble: int, caracteristicas: list):
        """Inserta las características del inmueble en la tabla EAV."""
        if not caracteristicas:
            return
            
        for carac in caracteristicas:
            if not carac or not isinstance(carac, str):
                continue
            
            carac_clean = carac.strip()
            carac_clean = carac_clean.replace('\rVer más', '').replace('Ver más', '').replace('\rVer menos', '').replace('Ver menos', '').strip()
            if not carac_clean or carac_clean.lower() in ('ver más', 'ver menos'):
                continue
                
            try:
                cursor.execute("""
                    INSERT INTO iug.inmueble_caracteristica (id_inmueble, nombre, valor_bool, fuente)
                    VALUES (%s, %s, TRUE, 'finca_raiz')
                    ON CONFLICT (id_inmueble, nombre) DO UPDATE SET updated_at = now()
                """, (id_inmueble, carac_clean))
            except Exception as e:
                self.logger.debug(f"Característica error: {e}")

