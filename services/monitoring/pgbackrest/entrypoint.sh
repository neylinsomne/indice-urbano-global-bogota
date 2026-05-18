#!/bin/bash
set -e

echo "=== pgBackRest - Inicializando ==="

# Crear stanza si no existe
pgbackrest --stanza=iug stanza-create 2>/dev/null || echo "Stanza ya existe"

# Si se pasa un comando, ejecutarlo
if [ "$1" ]; then
    exec pgbackrest --stanza=iug "$@"
fi

# Modo por defecto: backup completo
echo "=== Ejecutando backup completo ==="
pgbackrest --stanza=iug --type=full backup
echo "=== Backup completado ==="
pgbackrest --stanza=iug info
