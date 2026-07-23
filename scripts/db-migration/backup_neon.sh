#!/usr/bin/env bash
# Genera un dump completo (schema + datos) de la base de Neon, listo
# para restaurar en Render con restore_render.sh. Ver
# docs/migracion_neon_render.md para el procedimiento completo.
#
# Uso:
#   ./backup_neon.sh [connection_string] [output_file]
#   NEON_DATABASE_URL=postgres://... ./backup_neon.sh
#
# Requiere Docker corriendo (usa postgres:16-alpine para pg_dump/
# pg_isready, la misma versión que usan Neon, Render y
# docker-compose.yml local — evita instalar el cliente de Postgres en
# la máquina y garantiza compatibilidad de versión).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUPS_DIR="$SCRIPT_DIR/backups"
PG_IMAGE="postgres:16-alpine"

CONN_STRING="${1:-${NEON_DATABASE_URL:-}}"
if [[ -z "$CONN_STRING" ]]; then
  echo "Error: falta la connection string de Neon." >&2
  echo "Uso: ./backup_neon.sh <connection_string> [output_file]" >&2
  echo "  o: NEON_DATABASE_URL=postgres://... ./backup_neon.sh" >&2
  exit 1
fi

if [[ "$CONN_STRING" != *"sslmode="* ]]; then
  if [[ "$CONN_STRING" == *"?"* ]]; then
    CONN_STRING="${CONN_STRING}&sslmode=require"
  else
    CONN_STRING="${CONN_STRING}?sslmode=require"
  fi
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE="${2:-$BACKUPS_DIR/neon_${TIMESTAMP}.dump}"
OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_FILE")" && pwd)"
OUTPUT_NAME="$(basename "$OUTPUT_FILE")"

mkdir -p "$OUTPUT_DIR"

echo "Verificando conexión a Neon..."
docker run --rm "$PG_IMAGE" pg_isready -d "$CONN_STRING"

echo "Generando dump (formato custom, sin owner ni privilegios)..."
docker run --rm -v "$OUTPUT_DIR:/backups" "$PG_IMAGE" \
  pg_dump --format=custom --no-owner --no-privileges \
  --file="/backups/$OUTPUT_NAME" --dbname="$CONN_STRING"

SIZE="$(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "Dump generado correctamente:"
echo "  $OUTPUT_FILE ($SIZE)"
