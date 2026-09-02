import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError

from apps.routines.models import Exercise, Routine, RoutineCategory, RoutineExercise

DEFAULT_SEED_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "routine_seed_coach_2026_08.json"
)


class Command(BaseCommand):
    help = (
        "Reemplaza el catálogo de Exercise/Routine por lo que trae el JSON: solo "
        "sobreviven los ejercicios listados ahí (todo lo demás en esas categorías se "
        "borra), las categorías que el JSON no menciona se eliminan por completo "
        "(Routine + sus Exercise), y las rutinas quedan pre-armadas (RoutineExercise) "
        "en el orden exacto del JSON. Idempotente y seguro de correr contra Neon (no "
        "trae usuarios ni contraseñas de prueba). Nunca borra un Exercise/Routine con "
        "historial real (WorkoutExerciseEntry/WorkoutSessionLog, on_delete=PROTECT) — "
        "esos quedan intactos y se reportan al final."
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

    def handle(self, *args, **options):
        file_path = Path(options["file"])
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

            # Pre-arma cada rutina con exactamente los ejercicios del JSON, en el
            # orden en que el coach los mandó. Se limpia la selección anterior
            # primero (así los Exercise que ya no aplican quedan libres de
            # referencias de RoutineExercise antes del paso de borrado de abajo).
            for category in {e["category"] for e in routine_entries}:
                routine = Routine.objects.get(category=category)
                RoutineExercise.objects.filter(routine=routine).delete()
                order = 1
                for entry in exercise_entries:
                    if entry["category"] != category:
                        continue
                    exercise = Exercise.objects.get(name=entry["name"])
                    RoutineExercise.objects.create(routine=routine, exercise=exercise, order=order)
                    order += 1
                    routine_links_created += 1

            # Cualquier Exercise de una categoría cubierta por el JSON que no esté
            # en la lista del coach se borra (no se deja como placeholder). Si tiene
            # historial real (WorkoutExerciseEntry), el PROTECT lo bloquea: se deja
            # intacto y se reporta, nunca se fuerza el borrado.
            kept_names = {e["name"] for e in exercise_entries}
            for exercise in Exercise.objects.filter(category__in=categories_in_seed).exclude(
                name__in=kept_names
            ):
                if not self._delete_or_deactivate(exercise, deactivated_protected):
                    continue
                deleted_exercises += 1

            # Categorías que el coach no mandó (p. ej. CARDIO, ABS mientras no las
            # mande): se elimina la rutina completa (cascada a sus RoutineExercise)
            # y su catálogo de ejercicios. Mismo resguardo de PROTECT — un Routine
            # con historial (WorkoutSessionLog) no se puede desactivar (no tiene
            # is_active), así que ese caso solo se reporta, sin tocarlo.
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
                f"RoutineExercise: {routine_links_created} enlaces creados (orden del coach)."
            )
        )
        if deactivated_protected:
            self.stdout.write(
                self.style.WARNING(
                    "Bloqueados por historial real (no se borraron):\n  "
                    + "\n  ".join(deactivated_protected)
                )
            )
