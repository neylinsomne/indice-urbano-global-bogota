# Database Setup and Migration Guide

This guide explains how to set up the geographic database on a new machine, including importing POT, GeoJSON, and OSM data.

## 1. Prerequisites

* **Docker Desktop** (or Docker Engine + Compose) installed.
* **Git** installed.
* The raw data files (see Section 3).

## 2. Environment Setup

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd Estudio_inmobiliario
   ```
2. Ensure you have the `.env` file (if used) or check `docker-compose.yml` for default credentials.

   * Default user: `postgres`
   * Default password: `xd`
   * Default DB: `postgres`
   * Docker Network: `gisnet`

## 3. Data Files Management

**IMPORTANT:** The raw data files are **not** in git. You must copy them manually to `services/database/archivos/`.

Create the following structure:

```
services/database/archivos/
├── archivos/
│   ├── Bogota.osm.pbf           <-- 17MB OSM file
│   ├── barriolegalizado.json
│   ├── colegio.geojson
│   ├── ... (other GeoJSONs)
│   └── POT 555/
│       ├── areaactividad.json
│       ├── edificabilidad.json
│       └── tratamientourbanistico.json
```

## 4. Launching the Database

1. Navigate to the database directory:

   ```bash
   cd services/database
   ```
2. Create the external network (if it doesn't exist):

   ```bash
   docker network create gisnet
   ```
3. Start the services:

   ```bash
   docker-compose up -d
   ```

   * This starts `iug-postgres` (PostGIS) and `iug-flyway`.
   * **Flyway** will automatically apply SQL migrations `V1` through `V13` to create tables and views.
4. **Verify Migrations:**
   Check Flyway logs or check the database to ensure tables like `iug.inmueble`, `iug.osm_education`, etc., exist.

   ```bash
   docker logs iug-flyway
   ```

## 5. Running Data Imports

You need to run these scripts manually after the database is up.

### A. Load OSM Data (Roads & POIs)

This uses `OSM2PGSQL` via Docker.

```bash
# Windows PowerShell
docker run --rm --network gisnet -v "${PWD}/archivos/archivos:/data" -e PGPASSWORD=xd iboates/osm2pgsql osm2pgsql -d postgres -H iug-postgres -U postgres --slim -G --hstore /data/Bogota.osm.pbf
```

### B. Load POT and Administrative Data (Python)

Use the Dockerized Python environment to run the loading scripts.

1. **Load GeoJSONs (Localities, schools, etc.):**

   ```bash
   docker run --rm --network gisnet -v "${PWD}:/app" -w /app -e PG_HOST=iug-postgres -e PG_PORT=5432 -e PG_PASSWORD=xd python:3.11-slim sh -c "pip install psycopg2-binary -q && python load_geojson.py"
   ```
2. **Load POT Data (Edificabilidad, Barrios*, etc.):****s**
   *Note: Some POT files currently have geometry issues and may report errors.*

   ```bash
   docker run --rm --network gisnet -v "${PWD}:/app" -w /app -e PG_HOST=iug-postgres -e PG_PORT=5432 -e PG_PASSWORD=xd python:3.11-slim sh -c "pip install psycopg2-binary -q && python load_pot.py"
   ```

## 6. Final Steps

1. **Refresh Indicators:**
   Once data (and real estate properties) are loaded, refresh the Materialized View:

   ```bash
   docker run --rm --network gisnet -e PGPASSWORD=xd postgis/postgis:16-3.4 psql -h iug-postgres -U postgres -c "REFRESH MATERIALIZED VIEW iug.mv_inmueble_osm_indicators;"
   ```
2. **Verify:**
   Connect via pgAdmin or DBeaver to `localhost:5434` (User: `postgres`, Pass: `xd`) and check the `iug` schema.
