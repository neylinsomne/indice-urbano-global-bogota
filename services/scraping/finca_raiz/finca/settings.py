# Scrapy settings for finca project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html
import os
from dotenv import load_dotenv, find_dotenv

import datetime
#env_path = '../../.env'

# Cargar el archivo .env desde la ruta especificada
#load_dotenv(dotenv_path=env_path)

load_dotenv()
load_dotenv(find_dotenv(filename=".env", raise_error_if_not_found=False))
# Leer la variable de entorno
MONGODB_URI = os.getenv('MONGO_URI')
POSTGRES_URI = os.getenv('POSTGRES_URI')  # PostgreSQL para datos normalizados

BOT_NAME = "finca"

#apartamentos_venta', 'casas_venta', 'lotes_venta', 'bodegas_venta',"inmuebles_venta","locales_venta
# Generar MONGO_CONEXION para todas las ciudades y transacciones
_CIUDADES = ['bogota', 'medellin', 'cali', 'barranquilla', 'cajica', 'chia', 'madrid']
_TIPOS = ['apartamentos', 'casas', 'locales', 'lotes', 'bodegas', 'parqueadero', 'inmuebles', 'fincas']
_TRANSACCIONES = ['venta', 'arriendo']

MONGO_CONEXION = {
    ciudad: {
        f'{tipo}_{tx}': f'{tipo}_{tx}'
        for tipo in _TIPOS
        for tx in _TRANSACCIONES
    }
    for ciudad in _CIUDADES
}

SPIDER_MODULES = ["finca.spiders"]
NEWSPIDER_MODULE = "finca.spiders"


# Obey robots.txt rules
ROBOTSTXT_OBEY = False

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

 
DOWNLOADER_MIDDLEWARES = {
    'finca.middlewares.RotatingUserAgentMiddleware': 400,
    'finca.middlewares.RotatingProxyMiddleware': 410,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
}

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--no-sandbox", "--disable-setuid-sandbox"]
}

# Pipelines: solo MongoDB por ahora.
# PostgreSQL se llena luego via migración desde el panel de admin.
ITEM_PIPELINES = {
    "finca.pipelines.MongoDBPipeline": 300,
    # "finca.pipelines.PostgreSQLPipeline": 400,  # DESHABILITADO: migrar desde admin
}


PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 60_000
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8

# Configuración de reintentos automáticos
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
RETRY_PRIORITY_ADJUST = -1

# Configuración de delays para evitar bloqueos
DOWNLOAD_DELAY = 0.3
RANDOMIZE_DOWNLOAD_DELAY = True

# AutoThrottle: ajusta delay automaticamente segun respuesta del servidor
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.3
AUTOTHROTTLE_MAX_DELAY = 5
AUTOTHROTTLE_TARGET_CONCURRENCY = 8.0

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"
# Por defecto sin LOG_FILE para que logs vayan a stdout (visible en Docker logs)
# Definir LOG_FILE env para redirigir a archivo si se necesita debug local
LOG_FILE = os.getenv("LOG_FILE", None)
#USER_AGENT = "finca (+http://www.yourdomain.com)"


#Splash settings :)
#SPLASH_URL = 'http://localhost:8050'  NOW IS NOT WORKING >:(

# DOWNLOADER_MIDDLEWARES = {
#     'scrapy_splash.SplashCookiesMiddleware': 723,
#     'scrapy_splash.SplashMiddleware': 725,
#     'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
# }

#playwright info:
#SELENIUM PAPA
# DOWNLOADER_MIDDLEWARES = {
#     'finca.selenium_middleware.SeleniumMiddleware': 543,
# }

# SELENIUM_DRIVER_NAME = 'chrome'
# SELENIUM_DRIVER_EXECUTABLE_PATH = None  # No es necesario si usas un navegador remoto
# SELENIUM_DRIVER_ARGUMENTS = ['--headless']  # Para ejecutar en modo headless
# SELENIUM_BROWSER_EXECUTABLE_PATH = None
#DOWNLOADER_MIDDLEWARES = {
#    "finca.middlewares.FincaDownloaderMiddleware": 543,
#}
# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# SPIDER_MIDDLEWARES = {
#     'scrapy_splash.SplashDeduplicateArgsMiddleware': 100,
# }


# DUPEFILTER_CLASS = 'scrapy_splash.SplashAwareDupeFilter'
# HTTPCACHE_STORAGE = 'scrapy_splash.SplashAwareFSCacheStorage'

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "finca.middlewares.FincaSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html


# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "finca.pipelines.FincaPipeline": 300,
#}
# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"


