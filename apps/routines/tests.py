import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.members.models import Member, User
from apps.tracking.models import WorkoutExerciseEntry, WorkoutSessionLog
from .models import Exercise, Routine, RoutineCategory, RoutineExercise

SEED = {
    "routines": [
        {
            "category": "PECHO",
            "estimated_duration_min_low": 45,
            "estimated_duration_min_high": 60,
            "estimated_calories": 350,
        },
    ],
    "exercises": [
        {"name": "Despechadas", "category": "PECHO"},
        {"name": "Pecho Plano", "category": "PECHO"},
    ],
}


class LoadRoutineSeedTests(TestCase):
    """Comando `load_routine_seed`: reemplaza el catálogo por lo que trae el
    JSON — borra lo que sobra, arma las rutinas ya seleccionadas en el orden
    del coach, y nunca borra un Exercise con historial real (PROTECT)."""

    def setUp(self):
        self.seed_file = Path(tempfile.mkstemp(suffix=".json")[1])
        self.seed_file.write_text(json.dumps(SEED), encoding="utf-8")

    def tearDown(self):
        self.seed_file.unlink(missing_ok=True)

    def _run(self):
        call_command("load_routine_seed", file=str(self.seed_file))

    def test_creates_routine_exercises_and_ordered_links(self):
        self._run()

        routine = Routine.objects.get(category="PECHO")
        self.assertEqual(routine.estimated_duration_min_low, 45)
        self.assertEqual(
            list(routine.exercises.order_by("order").values_list("exercise__name", "order")),
            [("Despechadas", 1), ("Pecho Plano", 2)],
        )

    def test_deletes_stray_exercise_in_covered_category(self):
        Exercise.objects.create(name="Ejercicio Viejo", category=RoutineCategory.PECHO)

        self._run()

        self.assertFalse(Exercise.objects.filter(name="Ejercicio Viejo").exists())

    def test_deletes_routine_and_exercises_for_categories_not_in_seed(self):
        Routine.objects.create(category=RoutineCategory.CARDIO)
        Exercise.objects.create(name="Trote (placeholder)", category=RoutineCategory.CARDIO)

        self._run()

        self.assertFalse(Routine.objects.filter(category="CARDIO").exists())
        self.assertFalse(Exercise.objects.filter(name="Trote (placeholder)").exists())

    def test_is_idempotent(self):
        self._run()
        self._run()

        self.assertEqual(Exercise.objects.filter(category="PECHO").count(), 2)
        self.assertEqual(RoutineExercise.objects.filter(routine__category="PECHO").count(), 2)

    def test_exercise_with_real_history_is_deactivated_not_deleted(self):
        stray = Exercise.objects.create(name="Ejercicio Con Historial", category=RoutineCategory.PECHO)
        routine = Routine.objects.create(category=RoutineCategory.PECHO)
        user = User.objects.create_user(username="hist@test.com", email="hist@test.com", password="pass1234")
        member = Member.objects.create(
            user=user, first_name="Test", first_last_name="User", age=25, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=30,
        )
        session = WorkoutSessionLog.objects.create(member=member, routine=routine, duration_minutes=30)
        WorkoutExerciseEntry.objects.create(
            session=session, exercise=stray, initial_weight_lb=10, final_weight_lb=15, reps_completed=10
        )

        self._run()

        stray.refresh_from_db()
        self.assertTrue(Exercise.objects.filter(pk=stray.pk).exists())
        self.assertFalse(stray.is_active)
