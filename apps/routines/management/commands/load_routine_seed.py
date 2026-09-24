import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import ProtectedError

from apps.routines.models import Exercise, Routine, RoutineCategory, RoutineExercise

DEFAULT_SEED_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "routine_seed_coach_2026_09.json"
)


def _target_looks_like_neon():
    host = connection.settings_dict.get("HOST") or ""
    return "neon.tech" in host


class Command(BaseCommand):
    help = (
        "Crea/actualiza el catálogo de Exercise/Routine con lo que trae el JSON y "
        "deja cada Routine pre-armada con sus RoutineExercise (RoutineExercise) en el "
        "orden exacto del JSON — salvo las entradas marcadas 'in_routine': false, que "
        "solo se guardan como catálogo (Exercise) sin seleccionarlas en la rutina, tal "
        "como quedaron tras la última edición semanal del coach en el panel. Por "
        "defecto NUNCA borra: ni ejercicios que el JSON no mencione dentro de una "
        "categoría cubierta, ni categorías completas que el JSON no mencione en "
        "absoluto. Ese borrado (el comportamiento original del comando) solo ocurre "
        "si se pasa explícitamente --prune. Nunca borra un Exercise/Routine con "
        "historial real (WorkoutExerciseEntry/WorkoutSessionLog, on_delete=PROTECT) — "
        "esos quedan intactos y se reportan al final, con o sin --prune."
    )

    @staticmethod
    def _delete_or_deactivate(exercise, deactivated_log):
        """Borra el Exercise; si WorkoutExerciseEntry lo protege por historial
        real, lo desactiva en su lugar (nunca lo deja visible/seleccionable)."""
        try:
            with transaction.atomic():
                exercise.delete()
            return True
        except ProtectedError:
            if exercise.is_active:
                exercise.is_active = False
                exercise.save(update_fields=["is_active"])
            deactivated_log.append(
                f"Exercise '{exercise.name}' ({exercise.category}) — tiene historial, "
                "se desactivó en vez de borrarse"
            )
            return False

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(DEFAULT_SEED_FILE),
            help="Ruta al JSON con las claves 'routines' y 'exercises'.",
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Habilita el borrado destructivo original: elimina Exercise no "
                "listados dentro de una categoría cubierta por el JSON, y elimina "
                "por completo Routine+Exercise de categorías que el JSON no "
                "menciona en absoluto. Sin este flag el comando nunca borra nada, "
                "solo crea/actualiza. Usar con cuidado, sobre todo contra Neon."
            ),
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        prune = options["prune"]

        if _target_looks_like_neon():
            self.stdout.write(
                self.style.WARNING(
                    "\n*** ATENCIÓN: esta conexión apunta a Neon "
                    f"({connection.settings_dict.get('HOST')}), no a la base local. ***\n"
                    + ("*** Corriendo con --prune: puede BORRAR rutinas/ejercicios reales. ***\n"
                       if prune else
                       "*** Sin --prune: solo se crea/actualiza, no se borra nada. ***\n")
                )
            )

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        routine_entries = data.get("routines", [])
        exercise_entries = data.get("exercises", [])
        categories_in_seed = {e["category"] for e in routine_entries} | {
            e["category"] for e in exercise_entries
        }
        categories_excluded = [
            category for category, _ in RoutineCategory.choices if category not in categories_in_seed
        ]

        routines_created = routines_updated = 0
        exercises_created = exercises_updated = 0
        routine_links_created = 0
        deleted_exercises = 0
        deleted_routines = 0
        deactivated_protected = []

        with transaction.atomic():
            for entry in routine_entries:
                _, created = Routine.objects.update_or_create(
                    category=entry["category"],
                    defaults={
                        "estimated_duration_min_low": entry["estimated_duration_min_low"],
                        "estimated_duration_min_high": entry["estimated_duration_min_high"],
                        "estimated_calories": entry["estimated_calories"],
                    },
                )
                routines_created += created
                routines_updated += not created

            for entry in exercise_entries:
                _, created = Exercise.objects.update_or_create(
                    name=entry["name"],
                    defaults={"category": entry["category"], "is_active": True},
                )
                exercises_created += created
                exercises_updated += not created

            # Pre-arma cada rutina con los ejercicios del JSON marcados como
            # seleccionados (cualquier entrada sin 'in_routine' o con
            # 'in_routine': true), en el orden en que aparecen. Las marcadas
            # 'in_routine': false quedan como catálogo (Exercise) pero fuera de
            # la rutina — así se respeta la última selección semanal del coach
            # en vez de reseleccionar todo el catálogo en cada corrida. Se
            # limpia la selección anterior primero (así los Exercise que ya no
            # aplican quedan libres de referencias de RoutineExercise antes del
            # paso de borrado de abajo, si --prune está activo).
            for category in {e["category"] for e in routine_entries}:
                routine = Routine.objects.get(category=category)
                RoutineExercise.objects.filter(routine=routine).delete()
                order = 1
                for entry in exercise_entries:
                    if entry["category"] != category:
                        continue
                    if not entry.get("in_routine", True):
                        continue
                    exercise = Exercise.objects.get(name=entry["name"])
                    RoutineExercise.objects.create(routine=routine, exercise=exercise, order=order)
                    order += 1
                    routine_links_created += 1

            if prune:
                # Cualquier Exercise de una categoría cubierta por el JSON que no
                # esté en la lista se borra (no se deja como placeholder). Si
                # tiene historial real (WorkoutExerciseEntry), el PROTECT lo
                # bloquea: se deja intacto y se reporta, nunca se fuerza el
                # borrado. Solo corre con --prune (ver help del comando).
                kept_names = {e["name"] for e in exercise_entries}
                for exercise in Exercise.objects.filter(category__in=categories_in_seed).exclude(
                    name__in=kept_names
                ):
                    if not self._delete_or_deactivate(exercise, deactivated_protected):
                        continue
                    deleted_exercises += 1

                # Categorías que el JSON no menciona en absoluto: se elimina la
                # rutina completa (cascada a sus RoutineExercise) y su catálogo
                # de ejercicios. Mismo resguardo de PROTECT — un Routine con
                # historial (WorkoutSessionLog) no se puede desactivar (no tiene
                # is_active), así que ese caso solo se reporta, sin tocarlo.
                # Solo corre con --prune.
                for category in categories_excluded:
                    routine = Routine.objects.filter(category=category).first()
                    if routine:
                        try:
                            with transaction.atomic():
                                routine.delete()
                            deleted_routines += 1
                        except ProtectedError:
                            deactivated_protected.append(f"Routine '{category}' (tiene historial, no se tocó)")

                    for exercise in Exercise.objects.filter(category=category):
                        if not self._delete_or_deactivate(exercise, deactivated_protected):
                            continue
                        deleted_exercises += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Routine: {routines_created} creadas, {routines_updated} actualizadas, "
                f"{deleted_routines} eliminadas. "
                f"Exercise: {exercises_created} creados, {exercises_updated} actualizados, "
                f"{deleted_exercises} eliminados. "
                f"RoutineExercise: {routine_links_created} enlaces creados (orden del coach). "
                f"--prune: {'activo' if prune else 'inactivo (no se borró nada)'}."
            )
        )
        if deactivated_protected:
            self.stdout.write(
                self.style.WARNING(
                    "Bloqueados por historial real (no se borraron):\n  "
                    + "\n  ".join(deactivated_protected)
                )
            )
