#!/usr/bin/env bash
# =============================================================
# Crea (o actualiza) un usuario de prueba listo para login —
# sin pasar por OTP ni Turnstile. Idempotente.
#
# Hashea la password con bcrypt usando el container API (la lib
# 'bcrypt' está allí, no en el host). Marca email_verified=TRUE
# y registra el consent hábeas data v1.0-2026 para cumplir con
# la trazabilidad de Ley 1581/2012.
#
# Uso típico:
#   TEST_EMAIL=ia_trial@inmu.com \
#   TEST_PASSWORD='#insuranceuse_ACA_123' \
#   TEST_USERNAME=ia_trial \
#   TEST_NOMBRE='IA' TEST_APELLIDO='Trial' \
#   TEST_ROLE=free \
#     bash services/database/create_test_user.sh
#
# Variables soportadas:
#   TEST_EMAIL       (requerido)
#   TEST_PASSWORD    (requerido)
#   TEST_USERNAME    (default: derivado del email antes de @)
#   TEST_ROLE        (default: free; opciones: free, premium, admin)
#   TEST_NOMBRE      (default: 'Trial')
#   TEST_APELLIDO    (default: 'User')
#   TEST_TELEFONO    (default: vacío)
#   TEST_CEDULA      (default: vacío)
#   PG_USER          (default: postgres)
#   PG_DB            (default: postgres)
#   PG_CONTAINER     (default: iug-postgres)
#   API_CONTAINER    (default: api-inmobiliario)
# =============================================================
set -euo pipefail

EMAIL="${TEST_EMAIL:?Falta TEST_EMAIL}"
PASSWORD="${TEST_PASSWORD:?Falta TEST_PASSWORD}"
USERNAME="${TEST_USERNAME:-${EMAIL%@*}}"
ROLE="${TEST_ROLE:-free}"
NOMBRE="${TEST_NOMBRE:-Trial}"
APELLIDO="${TEST_APELLIDO:-User}"
TELEFONO="${TEST_TELEFONO:-}"
CEDULA="${TEST_CEDULA:-}"
PG_USER_ENV="${PG_USER:-postgres}"
PG_DB_ENV="${PG_DB:-postgres}"
PGCONTAINER="${PG_CONTAINER:-iug-postgres}"
APICONTAINER="${API_CONTAINER:-api-inmobiliario}"

# Validación de role
case "$ROLE" in
  free|premium|admin) ;;
  *) echo "[create_test_user] ERROR: TEST_ROLE inválido ('$ROLE'). Usa: free, premium, admin" ; exit 2 ;;
esac

# Hash bcrypt — generado dentro del container API
echo "[create_test_user] Hasheando contraseña con bcrypt..."
HASH=$(docker exec -e PW="$PASSWORD" "$APICONTAINER" python -c "
import bcrypt, os
pw = os.environ['PW'].encode('utf-8')
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode('utf-8'))
")

if [[ -z "$HASH" || ! "$HASH" =~ ^\$2b\$ ]]; then
    echo "[create_test_user] ERROR: hash bcrypt inválido"
    exit 1
fi

# Defaults para columnas opcionales
TELEFONO_SQL=$([[ -z "$TELEFONO" ]] && echo "NULL" || echo "'$TELEFONO'")
CEDULA_SQL=$([[ -z "$CEDULA" ]] && echo "NULL" || echo "'$CEDULA'")

# daily_pdf_limit: -1 admin (ilimitado), 50 premium, 2 free
case "$ROLE" in
  admin) PDF_LIMIT=-1 ;;
  premium) PDF_LIMIT=50 ;;
  *) PDF_LIMIT=2 ;;
esac

echo "[create_test_user] Upsert en iug.users..."
docker exec -i "$PGCONTAINER" psql -U "$PG_USER_ENV" -d "$PG_DB_ENV" <<SQL
WITH up AS (
  INSERT INTO iug.users
    (email, username, password_hash, role, daily_pdf_limit, is_active,
     email_verified, nombre, apellido, telefono, cedula, pais, ciudad)
  VALUES
    ('$EMAIL', '$USERNAME', '$HASH', '$ROLE', $PDF_LIMIT, TRUE,
     TRUE, '$NOMBRE', '$APELLIDO', $TELEFONO_SQL, $CEDULA_SQL, 'Colombia', 'Bogotá')
  ON CONFLICT (email) DO UPDATE SET
     password_hash  = EXCLUDED.password_hash,
     username       = EXCLUDED.username,
     role           = EXCLUDED.role,
     daily_pdf_limit= EXCLUDED.daily_pdf_limit,
     is_active      = TRUE,
     email_verified = TRUE,
     nombre         = EXCLUDED.nombre,
     apellido       = EXCLUDED.apellido,
     telefono       = EXCLUDED.telefono,
     cedula         = EXCLUDED.cedula
  RETURNING id
)
INSERT INTO iug.consent_log
  (user_id, email, evento, politica_version,
   autoriza_tratamiento, autoriza_marketing, autoriza_terceros,
   ip_origen, user_agent, locale)
SELECT
  id, '$EMAIL', 'registro', '1.0-2026',
  TRUE, FALSE, FALSE,
  NULL, 'create_test_user.sh (CLI)', 'es-CO'
FROM up;
SQL

echo "[create_test_user] OK · Usuario '$EMAIL' (role=$ROLE) listo para login."
echo "[create_test_user] · password_hash bcrypt cost=12 almacenado"
echo "[create_test_user] · email_verified=TRUE (skip OTP)"
echo "[create_test_user] · consent_log entrada 'registro' insertada"
