"""
Sistema de caché en memoria para resultados de consultas LLM
Evita repetir queries costosas a la base de datos
"""
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Caché LRU (Least Recently Used) en memoria para resultados de queries
    """

    def __init__(self, max_size: int = 100, ttl_minutes: int = 30):
        """
        Args:
            max_size: Máximo número de entries en caché
            ttl_minutes: Tiempo de vida de cada entry (minutos)
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = timedelta(minutes=ttl_minutes)
        self.access_times: Dict[str, datetime] = {}
        self.hit_count = 0
        self.miss_count = 0

    def _generate_key(self, query: str, params: Optional[Dict] = None) -> str:
        """
        Genera hash único para query + params
        """
        # Normalizar query (lowercase, strip whitespace)
        normalized_query = ' '.join(query.lower().split())

        # Incluir params en el hash
        if params:
            params_str = json.dumps(params, sort_keys=True)
        else:
            params_str = ""

        combined = f"{normalized_query}|{params_str}"
        return hashlib.md5(combined.encode()).hexdigest()

    def get(self, query: str, params: Optional[Dict] = None) -> Optional[Any]:
        """
        Obtiene resultado del caché si existe y no ha expirado
        """
        key = self._generate_key(query, params)

        if key not in self.cache:
            self.miss_count += 1
            logger.debug(f"Cache MISS: {key[:8]}...")
            return None

        entry = self.cache[key]
        timestamp = entry['timestamp']

        # Verificar si ha expirado
        if datetime.now() - timestamp > self.ttl:
            logger.debug(f"Cache EXPIRED: {key[:8]}...")
            del self.cache[key]
            del self.access_times[key]
            self.miss_count += 1
            return None

        # Actualizar tiempo de acceso (LRU)
        self.access_times[key] = datetime.now()
        self.hit_count += 1

        logger.debug(f"Cache HIT: {key[:8]}...")
        return entry['result']

    def set(self, query: str, result: Any, params: Optional[Dict] = None):
        """
        Guarda resultado en caché
        """
        key = self._generate_key(query, params)

        # Si caché está lleno, eliminar entry menos reciente
        if len(self.cache) >= self.max_size:
            self._evict_lru()

        self.cache[key] = {
            'result': result,
            'timestamp': datetime.now(),
            'query': query[:100]  # Solo primeros 100 chars para debug
        }
        self.access_times[key] = datetime.now()

        logger.debug(f"Cache SET: {key[:8]}... (size: {len(self.cache)}/{self.max_size})")

    def _evict_lru(self):
        """
        Elimina entry menos recientemente usado
        """
        if not self.access_times:
            return

        lru_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        del self.cache[lru_key]
        del self.access_times[lru_key]
        logger.debug(f"Cache EVICT: {lru_key[:8]}...")

    def clear(self):
        """
        Limpia todo el caché
        """
        self.cache.clear()
        self.access_times.clear()
        self.hit_count = 0
        self.miss_count = 0
        logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del caché
        """
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_rate': round(hit_rate, 2),
            'ttl_minutes': self.ttl.total_seconds() / 60
        }


# Instancia global del caché
llm_cache = CacheManager(max_size=100, ttl_minutes=30)
