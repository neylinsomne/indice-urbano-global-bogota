"""
Integración con LangChain (opcional)

Sistema avanzado de QA usando LangChain para queries complejas sobre inmuebles.
Requiere OpenAI API key.
"""
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

# Lazy imports
try:
    from langchain.agents import create_sql_agent
    from langchain.agents.agent_toolkits import SQLDatabaseToolkit
    from langchain.sql_database import SQLDatabase
    from langchain.llms import OpenAI
    from langchain.agents import AgentExecutor
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain no instalado. Funcionalidad avanzada deshabilitada.")


def setup_langchain_agent(
    db_url: str,
    openai_api_key: str,
    verbose: bool = False
) -> Optional['AgentExecutor']:
    """
    Configura agente de LangChain para consultas en lenguaje natural a la BD

    Args:
        db_url: URL de conexión PostgreSQL (postgresql://user:pass@host:port/db)
        openai_api_key: API key de OpenAI
        verbose: Si True, muestra pasos del agente

    Returns:
        AgentExecutor configurado o None si LangChain no disponible

    Ejemplo:
        agent = setup_langchain_agent(
            db_url="postgresql://user:pass@localhost:5432/postgres",
            openai_api_key="sk-...",
            verbose=True
        )

        result = agent.run("Encuentra inmuebles con I_URB > 4 cerca de universidades")
    """
    if not LANGCHAIN_AVAILABLE:
        logger.error("LangChain no está instalado")
        return None

    try:
        # Conectar a BD
        db = SQLDatabase.from_uri(db_url)

        # Crear toolkit con tablas permitidas
        toolkit = SQLDatabaseToolkit(
            db=db,
            llm=OpenAI(api_key=openai_api_key, temperature=0)
        )

        # Crear agente SQL
        agent_executor = create_sql_agent(
            llm=OpenAI(api_key=openai_api_key, temperature=0),
            toolkit=toolkit,
            verbose=verbose,
            agent_type="zero-shot-react-description"
        )

        logger.info("Agente LangChain configurado exitosamente")
        return agent_executor

    except Exception as e:
        logger.error(f"Error configurando LangChain agent: {e}")
        return None


# Prompt templates para queries comunes
QUERY_TEMPLATES = {
    "mejor_ubicacion": """
        Encuentra los {n} inmuebles con mejor I_URB (>=4.0) que tengan:
        - Precio menor a {precio_max}
        - Tipo: {tipo_inmueble}
        - Ordenados por ratio precio/I_URB (menor = mejor oportunidad)
    """,

    "cerca_dotaciones": """
        Busca inmuebles cerca de {dotaciones} (radio {radio}m) que:
        - Tengan I_URB >= {iurb_min}
        - Precio entre {precio_min} y {precio_max}
    """,

    "zona_segura_accesible": """
        Encuentra zonas con:
        - I_SEG >= {iseg_min} (seguridad)
        - I_ACC >= {iacc_min} (accesibilidad)
        - I_PNU >= {ipnu_min} (potencial desarrollo)
    """,

    "oportunidad_inversion": """
        Identifica oportunidades de inversión:
        - I_URB alto (>= 4.0)
        - Precio por debajo del percentil {percentil}
        - En zonas con {tratamiento_pot}
    """
}


def build_query_from_template(template_name: str, **params) -> str:
    """
    Construye query en lenguaje natural desde template

    Args:
        template_name: Nombre del template
        **params: Parámetros para el template

    Returns:
        Query formateada

    Ejemplo:
        query = build_query_from_template(
            "mejor_ubicacion",
            n=10,
            precio_max=500000000,
            tipo_inmueble="Apartamento"
        )
    """
    if template_name not in QUERY_TEMPLATES:
        raise ValueError(f"Template '{template_name}' no existe")

    template = QUERY_TEMPLATES[template_name]
    return template.format(**params)
