#!/usr/bin/env bash
# =============================================================
# Backup completo de Postgres (todo el cluster).
# Recomendado: ejecutar diariamente vía cron / Task Scheduler.
#
# Uso:
#   bash services/database/backup.sh
#
# Variables requeridas:
#   PG_USER, PG_PASSWORD, PG_DB
#
# Variables opcionales:
#   BACKUP_DIR       (default: ./backups)
#   BACKUP_RETENTION (default: 14 días)
#   PG_CONTAINER     (default: iug-postgres)
# =============================================================
set -euo pipefail

PGCONTAINER="${PG_CONTAINER:-iug-postgres}"
PG_USER_ENV="${PG_USER:-postgres}"
PG_DB_ENV="${PG_DB:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-14}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILE="$BACKUP_DIR/pg-${PG_DB_ENV}-${TIMESTAMP}.sql.gz"

echo "[backup] Iniciando backup de '$PG_DB_ENV' → $FILE"
docker exec "$PGCONTAINER" pg_dump \
    -U "$PG_USER_ENV" \
    -d "$PG_DB_ENV" \
    --format=plain \
    --no-owner \
    --no-acl \
    --clean --if-exists \
  | gzip -9 > "$FILE"

# Verificar que el archivo se creó correctamente
if [[ ! -s "$FILE" ]]; then
    echo "[backup] ERROR: backup vacío o no creado"
    exit 1
fi

SIZE=$(du -h "$FILE" | cut -f1)
echo "[backup] OK: $FILE ($SIZE)"

# Rotación: borrar backups más viejos que BACKUP_RETENTION días
echo "[backup] Limpiando backups con más de $BACKUP_RETENTION días..."
find "$BACKUP_DIR" -type f -name "pg-${PG_DB_ENV}-*.sql.gz" -mtime +"$BACKUP_RETENTION" -delete

# Lista actual de backups
echo "[backup] Backups disponibles:"
ls -lh "$BACKUP_DIR"/pg-${PG_DB_ENV}-*.sql.gz 2>/dev/null | tail -10
