#!/usr/bin/env bash
# Restaura en una base de Render un dump generado por backup_neon.sh.
# DESTRUCTIVO: sobrescribe (--clean) la base destino. Ver
# docs/migracion_neon_render.md para el procedimiento completo.
#
# Uso:
#   ./restore_render.sh <dump_file> [connection_string]
#   RENDER_DATABASE_URL=postgres://... ./restore_render.sh <dump_file>
#
# Requiere Docker corriendo (usa postgres:16-alpine para pg_restore/
# psql, la misma versión que usan Neon, Render y docker-compose.yml
# local).

set -euo pipefail

PG_IMAGE="postgres:16-alpine"

DUMP_FILE="${1:-}"
if [[ -z "$DUMP_FILE" ]]; then
  echo "Error: falta la ruta del dump a restaurar." >&2
  echo "Uso: ./restore_render.sh <dump_file> [connection_string]" >&2
  exit 1
fi
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Error: no existe el archivo '$DUMP_FILE'." >&2
  exit 1
fi
DUMP_FILE="$(cd "$(dirname "$DUMP_FILE")" && pwd)/$(basename "$DUMP_FILE")"
DUMP_DIR="$(dirname "$DUMP_FILE")"
DUMP_NAME="$(basename "$DUMP_FILE")"

CONN_STRING="${2:-${RENDER_DATABASE_URL:-}}"
if [[ -z "$CONN_STRING" ]]; then
  echo "Error: falta la connection string de Render." >&2
  echo "Uso: ./restore_render.sh <dump_file> <connection_string>" >&2
  echo "  o: RENDER_DATABASE_URL=postgres://... ./restore_render.sh <dump_file>" >&2
  exit 1
fi

if [[ "$CONN_STRING" != *"sslmode="* ]]; then
  if [[ "$CONN_STRING" == *"?"* ]]; then
    CONN_STRING="${CONN_STRING}&sslmode=require"
  else
    CONN_STRING="${CONN_STRING}?sslmode=require"
  fi
fi

echo "Vas a restaurar '$DUMP_NAME' en la base:"
echo "  $CONN_STRING"
echo ""
echo "Esto BORRA y reemplaza (--clean) el contenido actual de esa base."
read -r -p "Escribe RESTAURAR (en mayúsculas) para continuar: " CONFIRM
if [[ "$CONFIRM" != "RESTAURAR" ]]; then
  echo "Cancelado, no se hizo ningún cambio."
  exit 1
fi

echo "Restaurando..."
docker run --rm -v "$DUMP_DIR:/backups" "$PG_IMAGE" \
  pg_restore --clean --if-exists --no-owner --no-privileges --jobs=4 \
  --dbname="$CONN_STRING" "/backups/$DUMP_NAME"

echo ""
echo "Restore completo. Verificando conteos de tablas..."

VERIFY_SQL="
SELECT 'members_user' AS tabla, COUNT(*) FROM members_user
UNION ALL SELECT 'members_member', COUNT(*) FROM members_member
UNION ALL SELECT 'routines_exercise', COUNT(*) FROM routines_exercise
UNION ALL SELECT 'routines_routine', COUNT(*) FROM routines_routine
UNION ALL SELECT 'routines_routineexercise', COUNT(*) FROM routines_routineexercise
UNION ALL SELECT 'routines_scheduledroutineday', COUNT(*) FROM routines_scheduledroutineday
UNION ALL SELECT 'nutrition_nutritionplan', COUNT(*) FROM nutrition_nutritionplan
UNION ALL SELECT 'nutrition_mealsuggestion', COUNT(*) FROM nutrition_mealsuggestion
UNION ALL SELECT 'tracking_workoutsessionlog', COUNT(*) FROM tracking_workoutsessionlog
UNION ALL SELECT 'tracking_workoutexerciseentry', COUNT(*) FROM tracking_workoutexerciseentry
UNION ALL SELECT 'tracking_dailynutritionlog', COUNT(*) FROM tracking_dailynutritionlog
UNION ALL SELECT 'tracking_bodymeasurementlog', COUNT(*) FROM tracking_bodymeasurementlog
UNION ALL SELECT 'ml_predictions_mlprediction', COUNT(*) FROM ml_predictions_mlprediction
ORDER BY tabla;
"

docker run --rm "$PG_IMAGE" psql "$CONN_STRING" -c "$VERIFY_SQL"

echo ""
echo "Listo. Revisa los conteos de arriba contra lo que esperabas de Neon"
echo "antes de actualizar las variables de entorno del Web Service en Render."
