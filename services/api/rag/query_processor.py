"""
Procesador de queries en lenguaje natural

Usa LangChain y LLM para interpretar queries del usuario y extraer:
- Categorías de dotaciones mencionadas
- Radio de búsqueda
- Filtros adicionales
"""
import re
from typing import Dict, List, Optional, Tuple
import asyncpg

# Lazy imports para LangChain
try:
    from langchain.llms import OpenAI
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


class QueryProcessor:
    """
    Procesa queries en lenguaje natural y extrae intención de búsqueda
    """

    # Mapeo de términos comunes a categorías de BD
    CATEGORIA_KEYWORDS = {
        'hospital': 'ips',
        'clinica': 'ips',
        'centro medico': 'ips',
        'salud': 'ips',
        'farmacia': 'farmacia',
        'colegio': 'colegio',
        'escuela': 'colegio',
        'instituto': 'colegio',
        'universidad': 'universidad',
        'educacion superior': 'universidad',
        'biblioteca': 'biblioteca',
        'biblored': 'biblioteca',
        'teatro': 'teatro',
        'auditorio': 'teatro',
        'centro comercial': 'centro_comercial',
        'mall': 'centro_comercial',
        'compras': 'centro_comercial',
        'plaza de mercado': 'plaza_mercado',
        'mercado': 'plaza_mercado',
        'parque': 'parque',
        'zona verde': 'parque',
        'cancha': 'cancha_futbol',
        'deportivo': 'cancha_futbol'
    }

    # Palabras clave de distancia
    DISTANCIA_KEYWORDS = {
        'muy cerca': 300,
        'cerca': 500,
        'cercano': 500,
        'proximos': 800,
        'proximidad': 800,
        'alrededor': 1000,
        'radio': 1000,
        'zona': 1500,
        'sector': 2000
    }

    def __init__(self, use_llm: bool = False, openai_api_key: Optional[str] = None):
        """
        Args:
            use_llm: Si True, usa LangChain+OpenAI para parsing avanzado
            openai_api_key: API key de OpenAI (requerida si use_llm=True)
        """
        self.use_llm = use_llm and LANGCHAIN_AVAILABLE
        self.llm_chain = None

        if self.use_llm:
            if not openai_api_key:
                raise ValueError("OpenAI API key requerida para usar LLM")

            prompt = PromptTemplate(
                input_variables=["query"],
                template="""
Eres un asistente que extrae información de búsquedas inmobiliarias.

Query del usuario: "{query}"

Extrae la siguiente información:
1. Categorías de dotaciones mencionadas (hospitales, colegios, parques, etc.)
2. Radio de búsqueda implícito (en metros)
3. Si menciona cantidad mínima de dotaciones

Responde en formato JSON:
{{
    "categorias": ["categoria1", "categoria2"],
    "radio_metros": 500,
    "cantidad_minima": null
}}

JSON:
"""
            )

            self.llm_chain = LLMChain(
                llm=OpenAI(api_key=openai_api_key, temperature=0),
                prompt=prompt
            )

    def extract_categories_rule_based(self, query: str) -> List[str]:
        """
        Extrae categorías usando reglas simples (no requiere LLM)

        Args:
            query: Query del usuario en minúsculas

        Returns:
            Lista de categorías identificadas
        """
        query_lower = query.lower()
        categorias = set()

        for keyword, categoria in self.CATEGORIA_KEYWORDS.items():
            if keyword in query_lower:
                categorias.add(categoria)

        return list(categorias)

    def extract_radius_rule_based(self, query: str) -> int:
        """
        Extrae radio de búsqueda usando reglas simples

        Args:
            query: Query del usuario

        Returns:
            Radio en metros (default 1000)
        """
        query_lower = query.lower()

        # Buscar número explícito (ej: "500 metros", "1 km")
        # Patrón: número + metros/km
        metros_match = re.search(r'(\d+)\s*metros?', query_lower)
        if metros_match:
            return int(metros_match.group(1))

        km_match = re.search(r'(\d+)\s*km', query_lower)
        if km_match:
            return int(km_match.group(1)) * 1000

        # Palabras clave de distancia
        for keyword, radius in self.DISTANCIA_KEYWORDS.items():
            if keyword in query_lower:
                return radius

        # Default
        return 1000

    async def process_query_llm(self, query: str) -> Dict:
        """
        Procesa query usando LangChain+LLM (requiere OpenAI API)

        Args:
            query: Query en lenguaje natural

        Returns:
            Dict con categorías, radio, etc.
        """
        if not self.use_llm:
            raise RuntimeError("LLM no configurado")

        import json

        # Ejecutar LLM
        response = await self.llm_chain.arun(query=query)

        # Parsear JSON
        try:
            result = json.loads(response)
            return result
        except json.JSONDecodeError:
            # Fallback a reglas
            return {
                "categorias": self.extract_categories_rule_based(query),
                "radio_metros": self.extract_radius_rule_based(query),
                "cantidad_minima": None
            }

    def process_query_rules(self, query: str) -> Dict:
        """
        Procesa query usando solo reglas (no requiere LLM)

        Args:
            query: Query en lenguaje natural

        Returns:
            Dict con categorías, radio, cantidad_minima
        """
        categorias = self.extract_categories_rule_based(query)
        radio = self.extract_radius_rule_based(query)

        return {
            "categorias": categorias,
            "radio_metros": radio,
            "cantidad_minima": None
        }

    async def process_natural_query(self, query: str) -> Dict:
        """
        Procesa query en lenguaje natural (usa LLM si disponible, sino reglas)

        Args:
            query: Query del usuario

        Returns:
            Dict con información extraída
        """
        if self.use_llm:
            return await self.process_query_llm(query)
        else:
            return self.process_query_rules(query)


# Instancia global con reglas (no requiere API key)
_processor = QueryProcessor(use_llm=False)


def process_natural_query(query: str) -> Dict:
    """
    Procesa query en lenguaje natural usando reglas

    Args:
        query: "cerca a colegios y hospitales"

    Returns:
        {
            "categorias": ["colegio", "ips"],
            "radio_metros": 500,
            "cantidad_minima": None
        }
    """
    return _processor.process_query_rules(query)


# Ejemplos de queries soportadas
QUERY_EXAMPLES = [
    "cerca a colegios y universidades",
    "zonas con hospitales y centros médicos",
    "área con parques y centros comerciales a 500 metros",
    "sectores cerca de bibliotecas",
    "buscar cerca de plazas de mercado y farmacias",
    "muy cerca a teatros y auditorios",
    "proximidad a canchas y parques"
]
