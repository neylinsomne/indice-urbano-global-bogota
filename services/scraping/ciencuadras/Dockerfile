FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema (Chrome para Selenium)
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg2 \
    unzip \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt webdriver_manager

# Copiar codigo
COPY . .

# Comando por defecto
CMD ["python", "main.py"]
