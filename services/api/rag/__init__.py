"""
RAG System for Semantic Search

Sistema de búsqueda semántica usando embeddings para dotaciones urbanas.
Permite queries en lenguaje natural como:
- "cerca a colegios y centros médicos"
- "zonas con universidades y parques"
- "área con hospitales y bibliotecas"
"""

from .embeddings import generate_embeddings, search_similar_dotaciones
from .query_processor import process_natural_query
from .langchain_integration import setup_langchain_agent

__all__ = [
    'generate_embeddings',
    'search_similar_dotaciones',
    'process_natural_query',
    'setup_langchain_agent'
]
