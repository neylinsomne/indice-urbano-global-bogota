#!/usr/bin/env bash
# =============================================================
# Bootstrap del usuario admin inicial.
# Reemplaza el seed peligroso de V107 (que sembraba admin/admin123).
#
# Uso (idempotente):
#   INITIAL_ADMIN_EMAIL=admin@example.com \
#   INITIAL_ADMIN_PASSWORD='S0me-Strong-Pass!' \
#     bash services/database/bootstrap_admin.sh
#
# Variables requeridas en .env (o exportadas):
#   INITIAL_ADMIN_EMAIL
#   INITIAL_ADMIN_PASSWORD
#   PG_USER, PG_PASSWORD, PG_DB    (superuser para hacer INSERT)
# =============================================================
set -euo pipefail

EMAIL="${INITIAL_ADMIN_EMAIL:?Falta INITIAL_ADMIN_EMAIL}"
PASSWORD="${INITIAL_ADMIN_PASSWORD:?Falta INITIAL_ADMIN_PASSWORD}"
USERNAME="${INITIAL_ADMIN_USERNAME:-admin}"
PG_USER_ENV="${PG_USER:-postgres}"
PG_DB_ENV="${PG_DB:-postgres}"
PGCONTAINER="${PG_CONTAINER:-iug-postgres}"
APICONTAINER="${API_CONTAINER:-api-inmobiliario}"

# Hashea con bcrypt (usa el container de la API, que ya tiene la lib)
echo "[bootstrap_admin] Generando hash bcrypt..."
HASH=$(docker exec "$APICONTAINER" python -c "
import bcrypt, os
pw = os.environ['PW'].encode('utf-8')
print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode('utf-8'))
" PW="$PASSWORD")

if [[ -z "$HASH" || ! "$HASH" =~ ^\$2b\$ ]]; then
    echo "[bootstrap_admin] ERROR: hash inválido"
    exit 1
fi

echo "[bootstrap_admin] Insertando o actualizando admin en BD..."
docker exec -i "$PGCONTAINER" psql -U "$PG_USER_ENV" -d "$PG_DB_ENV" <<SQL
INSERT INTO iug.users (email, username, password_hash, role, daily_pdf_limit, is_active)
VALUES ('$EMAIL', '$USERNAME', '$HASH', 'admin', -1, true)
ON CONFLICT (email) DO UPDATE
SET password_hash = EXCLUDED.password_hash,
    role = 'admin',
    is_active = true;
SQL

echo "[bootstrap_admin] Admin '$EMAIL' listo. Guarda esa password en un sitio seguro."
