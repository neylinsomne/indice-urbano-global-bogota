# =========================================
# Dockerfile para Orquestador de Carga de Datos
# =========================================
# Imagen base ligera con Python para cargar GeoJSON/JSON
# No necesita GDAL ya que trabajamos directamente con JSON

FROM python:3.11-slim

# Metadata
LABEL maintainer="Estudio Inmobiliario"
LABEL description="Data Loader Orchestrator - Carga automática de datos geográficos"

# Instalar herramientas necesarias
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar scripts de carga
COPY orquestador_carga.py .
COPY cargar_datos.py .
COPY cargar_sitp.py .
COPY cargar_localidades_barrios.py .
COPY loaders/ ./loaders/

# Copiar archivos de datos (estos se montarán como volumen en runtime)
# COPY archivos/ ./archivos/

# Variables de entorno predeterminadas
ENV PG_HOST=localhost
ENV PG_PORT=5434
ENV PG_DB=postgres
ENV PG_USER=postgres
ENV PYTHONUNBUFFERED=1

# Entrypoint: ejecutar orquestador
ENTRYPOINT ["python3", "orquestador_carga.py"]

# Healthcheck (opcional, para verificar conectividad a PostgreSQL)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD pg_isready -h ${PG_HOST} -p ${PG_PORT} -U ${PG_USER} || exit 1
