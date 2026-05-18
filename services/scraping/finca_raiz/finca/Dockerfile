# Playwright + browsers preinstalados
# IMPORTANTE: la versión de la imagen DEBE coincidir con la versión de playwright
# que instala pip (via scrapy-playwright). Si pip instala playwright 1.58.0,
# la imagen debe ser v1.58.0-jammy.
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# Evita re-descargas de browsers (ya vienen en la imagen)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    PYTHONUNBUFFERED=1 \
    SCRAPY_SETTINGS_MODULE=finca.settings

WORKDIR /app

# Instala dependencias de Python (Scrapy, scrapy-playwright, pymongo, etc.)
# Recomendación: NO instales 'playwright' aquí, ya viene con la imagen.
COPY finca/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia scrapy.cfg (raíz del proyecto Scrapy) y el paquete finca/
COPY scrapy.cfg .
COPY finca/ ./finca/

# Entrypoint flexible: modo single o matrix
COPY finca/docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]
