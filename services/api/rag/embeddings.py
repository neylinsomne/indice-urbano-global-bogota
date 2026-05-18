"""
Generación y búsqueda de embeddings para dotaciones

Usa sentence-transformers para crear embeddings semánticos de nombres de dotaciones.
Permite búsquedas por similitud para queries en lenguaje natural.
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
import asyncpg
import pickle
import logging
from pathlib import Path

# Lazy import para no requerir en todos los entornos
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logging.warning("sentence-transformers no instalado. Funcionalidad de embeddings deshabilitada.")

logger = logging.getLogger(__name__)

# Path para cache de embeddings
EMBEDDINGS_CACHE = Path(__file__).parent / "cache" / "dotaciones_embeddings.pkl"

# Modelo multilingüe para español
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingsManager:
    """
    Gestiona embeddings de dotaciones para búsqueda semántica
    """

    def __init__(self):
        self.model = None
        self.embeddings_cache = {}
        self.categorias_mapping = {
            'ips': ['hospital', 'clinica', 'centro medico', 'salud', 'farmacia'],
            'colegio': ['colegio', 'escuela', 'institucion educativa', 'educacion basica'],
            'universidad': ['universidad', 'educacion superior', 'instituto', 'tecnologico'],
            'biblioteca': ['biblioteca', 'biblored', 'cultura', 'lectura'],
            'teatro': ['teatro', 'auditorio', 'cultural', 'arte'],
            'centro_comercial': ['centro comercial', 'mall', 'compras', 'comercio'],
            'plaza_mercado': ['plaza de mercado', 'mercado', 'plazoleta', 'abastecimiento'],
            'parque': ['parque', 'zona verde', 'espacio publico', 'recreacion'],
            'cancha_futbol': ['cancha', 'futbol', 'deporte', 'deportivo']
        }

    def load_model(self):
        """Carga el modelo de embeddings (lazy loading)"""
        if not EMBEDDINGS_AVAILABLE:
            raise RuntimeError("sentence-transformers no está instalado. Ejecutar: pip install sentence-transformers")

        if self.model is None:
            logger.info(f"Cargando modelo de embeddings: {MODEL_NAME}")
            self.model = SentenceTransformer(MODEL_NAME)

        return self.model

    def load_cache(self) -> bool:
        """Carga cache de embeddings si existe"""
        if EMBEDDINGS_CACHE.exists():
            try:
                with open(EMBEDDINGS_CACHE, 'rb') as f:
                    self.embeddings_cache = pickle.load(f)
                logger.info(f"Cache de embeddings cargado: {len(self.embeddings_cache)} dotaciones")
                return True
            except Exception as e:
                logger.error(f"Error cargando cache: {e}")
                return False
        return False

    def save_cache(self):
        """Guarda cache de embeddings"""
        EMBEDDINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(EMBEDDINGS_CACHE, 'wb') as f:
            pickle.dump(self.embeddings_cache, f)
        logger.info(f"Cache guardado: {len(self.embeddings_cache)} dotaciones")

    async def generate_embeddings_from_db(self, conn: asyncpg.Connection) -> Dict[int, np.ndarray]:
        """
        Genera embeddings para todas las dotaciones en la BD

        Returns:
            Dict con id_dotacion -> embedding
        """
        model = self.load_model()

        # Obtener todas las dotaciones
        rows = await conn.fetch("""
            SELECT id, nombre, categoria
            FROM iug.dotaciones_poi
            ORDER BY id
        """)

        logger.info(f"Generando embeddings para {len(rows)} dotaciones...")

        embeddings = {}
        batch_size = 100

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]

            # Concatenar nombre + categoría para contexto
            textos = [f"{row['categoria']}: {row['nombre']}" for row in batch]

            # Generar embeddings
            batch_embeddings = model.encode(textos, show_progress_bar=True)

            # Guardar
            for row, emb in zip(batch, batch_embeddings):
                embeddings[row['id']] = emb

        # Actualizar cache
        self.embeddings_cache = embeddings
        self.save_cache()

        return embeddings

    def get_category_embedding(self, categoria: str) -> Optional[np.ndarray]:
        """
        Obtiene embedding promedio para una categoría

        Args:
            categoria: Nombre de categoría (ips, colegio, etc.)

        Returns:
            Embedding promedio de la categoría
        """
        if categoria not in self.categorias_mapping:
            return None

        model = self.load_model()
        keywords = self.categorias_mapping[categoria]
        embeddings = model.encode(keywords)

        # Promedio de todos los keywords
        return np.mean(embeddings, axis=0)

    async def search_dotaciones_by_query(
        self,
        query: str,
        conn: asyncpg.Connection,
        top_k: int = 50,
        categoria_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Busca dotaciones similares a una query en lenguaje natural

        Args:
            query: Query del usuario (ej: "hospitales y centros médicos")
            conn: Conexión PostgreSQL
            top_k: Número de resultados
            categoria_filter: Filtrar por categoría específica

        Returns:
            Lista de dotaciones ranqueadas por similitud
        """
        # Cargar embeddings si no están en memoria
        if not self.embeddings_cache:
            if not self.load_cache():
                # Generar si no hay cache
                await self.generate_embeddings_from_db(conn)

        model = self.load_model()

        # Generar embedding de la query
        query_embedding = model.encode([query])[0]

        # Calcular similitud coseno con todas las dotaciones
        similarities = []

        for dot_id, dot_embedding in self.embeddings_cache.items():
            similarity = np.dot(query_embedding, dot_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(dot_embedding)
            )
            similarities.append((dot_id, similarity))

        # Ordenar por similitud
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Top K
        top_ids = [id for id, _ in similarities[:top_k]]

        # Obtener datos completos de la BD
        filter_clause = "AND categoria = $2" if categoria_filter else ""
        params = [top_ids] if not categoria_filter else [top_ids, categoria_filter]

        query_sql = f"""
            SELECT
                id,
                nombre,
                categoria,
                fuente,
                ST_X(geom) as longitud,
                ST_Y(geom) as latitud
            FROM iug.dotaciones_poi
            WHERE id = ANY($1)
            {filter_clause}
        """

        rows = await conn.fetch(query_sql, *params)

        # Ordenar según ranking de similitud
        id_to_row = {row['id']: row for row in rows}
        ranked_results = []

        for dot_id, sim_score in similarities[:top_k]:
            if dot_id in id_to_row:
                row = dict(id_to_row[dot_id])
                row['similarity_score'] = float(sim_score)
                ranked_results.append(row)

        return ranked_results

    async def search_nearby_with_categories(
        self,
        lat: float,
        lon: float,
        categorias: List[str],
        radius_m: int,
        conn: asyncpg.Connection
    ) -> Dict[str, List[Dict]]:
        """
        Busca dotaciones cercanas agrupadas por categoría

        Args:
            lat: Latitud del punto
            lon: Longitud del punto
            categorias: Lista de categorías a buscar
            radius_m: Radio de búsqueda en metros
            conn: Conexión PostgreSQL

        Returns:
            Dict con categoria -> lista de dotaciones cercanas
        """
        point_wkt = f"POINT({lon} {lat})"

        results = {}

        for categoria in categorias:
            rows = await conn.fetch("""
                SELECT
                    id,
                    nombre,
                    categoria,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_GeomFromText($1), 4326)::geography
                    ) as distancia_m,
                    ST_X(geom) as longitud,
                    ST_Y(geom) as latitud
                FROM iug.dotaciones_poi
                WHERE categoria = $2
                  AND ST_DWithin(
                      geom::geography,
                      ST_SetSRID(ST_GeomFromText($1), 4326)::geography,
                      $3
                  )
                ORDER BY distancia_m ASC
                LIMIT 10
            """, point_wkt, categoria, radius_m)

            results[categoria] = [dict(row) for row in rows]

        return results


# Instancia global
_embeddings_manager = None


def get_embeddings_manager() -> EmbeddingsManager:
    """Obtiene instancia singleton del manager de embeddings"""
    global _embeddings_manager
    if _embeddings_manager is None:
        _embeddings_manager = EmbeddingsManager()
    return _embeddings_manager


# Funciones de conveniencia
async def generate_embeddings(conn: asyncpg.Connection) -> Dict[int, np.ndarray]:
    """Genera embeddings para todas las dotaciones"""
    manager = get_embeddings_manager()
    return await manager.generate_embeddings_from_db(conn)


async def search_similar_dotaciones(
    query: str,
    conn: asyncpg.Connection,
    top_k: int = 50
) -> List[Dict]:
    """Busca dotaciones similares a una query"""
    manager = get_embeddings_manager()
    return await manager.search_dotaciones_by_query(query, conn, top_k)
