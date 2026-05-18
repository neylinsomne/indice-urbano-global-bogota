FROM python:3.11-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copiar código de la aplicación
COPY main.py .
COPY websocket_manager.py .
COPY routers/ ./routers/
COPY models/ ./models/
COPY db/ ./db/
COPY llm/ ./llm/
COPY rag/ ./rag/
COPY ahp/ ./ahp/
COPY analytics/ ./analytics/
COPY listeners/ ./listeners/
COPY services/ ./services/
COPY resources/ ./resources/
COPY schema/ ./schema/
COPY util/ ./util/

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Exponer puerto
EXPOSE 8000

# Comando para ejecutar la API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]