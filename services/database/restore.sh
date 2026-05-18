#!/usr/bin/env bash
# =============================================================
# Restaura un backup creado por backup.sh.
#
# ⚠️  USO DESTRUCTIVO — sobreescribe la BD actual.
#
# Uso:
#   bash services/database/restore.sh <archivo.sql.gz>
#
# Variables:
#   PG_USER, PG_PASSWORD, PG_DB, PG_CONTAINER
# =============================================================
set -euo pipefail

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Uso: $0 <archivo.sql.gz>"
    echo "Ejemplo: $0 ./backups/pg-postgres-20260504-031200.sql.gz"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "[restore] ERROR: archivo no encontrado: $BACKUP_FILE"
    exit 1
fi

PGCONTAINER="${PG_CONTAINER:-iug-postgres}"
PG_USER_ENV="${PG_USER:-postgres}"
PG_DB_ENV="${PG_DB:-postgres}"

echo "[restore] ⚠️  Vas a SOBREESCRIBIR la base de datos '$PG_DB_ENV'"
echo "[restore] Archivo: $BACKUP_FILE"
read -p "[restore] Escribe 'CONFIRMAR' para continuar: " CONFIRM
if [[ "$CONFIRM" != "CONFIRMAR" ]]; then
    echo "[restore] Cancelado por el usuario"
    exit 0
fi

echo "[restore] Restaurando..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$PGCONTAINER" psql \
    -U "$PG_USER_ENV" \
    -d "$PG_DB_ENV" \
    --single-transaction \
    --set ON_ERROR_STOP=on

echo "[restore] OK. Reinicia la API: docker compose --profile production up -d --force-recreate api"
