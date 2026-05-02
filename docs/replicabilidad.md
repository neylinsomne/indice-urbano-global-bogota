# Replicabilidad

Cómo levantar el sistema completo en una máquina local.

## Requisitos

- Docker Desktop (Windows / macOS / Linux)
- 8 GB RAM mínimo (16 GB recomendado)
- 20 GB de disco
- Git

## Pasos

### 1. Clonar el repositorio

```bash
git clone https://github.com/neylinsomne/indice-urbano-global-bogota.git
cd indice-urbano-global-bogota
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` y completar:

- `MONGO_URI` — instancia de MongoDB (Atlas o local)
- `JWT_SECRET` — generar con `python -c "import secrets; print(secrets.token_hex(32))"`
- `PIPELINE_SECRET` — igual al anterior
- `GOOGLE_API_KEY` — para el asistente RAG (https://aistudio.google.com)
- Otros: dejar valores por defecto

### 3. Levantar la pila

```bash
# Base de datos + migraciones
docker compose up -d postgres flyway redis

# Esperar a que Flyway termine
docker compose logs -f flyway
# (ver "Successfully applied N migrations to schema...")
# Ctrl+C cuando termine

# API + Frontend
docker compose up -d api frontend-dev
```

### 4. Cargar datos iniciales

```bash
# Si el dump está disponible
docker compose exec -T postgres psql -U postgres -d postgres < data/seed.sql

# O ejecutar el ETL desde MongoDB
curl -X POST http://localhost:8000/pipeline/etl \
  -H "X-Pipeline-Secret: $PIPELINE_SECRET"
```

### 5. Verificar

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

## Ejecutar scrapers (opcional)

Para repoblar datos:

```bash
# Solo Bogotá apartamentos venta + arriendo
docker compose --profile finca run --rm \
  -e TIPOS=apartamentos \
  -e SECTORES=bogota \
  -e TXS=venta,arriendo \
  scraper-finca
```

## Recalcular indicadores

```bash
curl -X POST http://localhost:8000/admin/recalcular-indicadores \
  -H "X-Pipeline-Secret: $PIPELINE_SECRET"
```

O directamente en SQL:

```sql
SELECT iug.f_recalcular_indicadores(id_inmueble)
FROM iug.inmueble;
```

## Datos de muestra

El directorio `data/sample/` incluye un subset de 100 inmuebles ya procesados, suficientes para verificar las métricas reportadas en la tesis sin necesidad de ejecutar el scraping completo.

## Troubleshooting

### Error: "function f_asignar_barrio_localidad does not exist"

Las migraciones no se aplicaron correctamente. Re-ejecutar:

```bash
docker compose run --rm flyway migrate
```

### Error: "port 8000 already in use"

Otro servicio está usando el puerto. Detenerlo o cambiar el puerto en `docker-compose.yml`:

```yaml
api:
  ports:
    - "8001:8000"  # cambiar host port
```

### El scraper queda en "0 pages/min"

Verificar que `SCRAPER_PROXIES` esté vacío (a menos que tengas un proxy funcional configurado).

## Soporte

Para preguntas sobre replicabilidad, abrir un *issue* en GitHub.
