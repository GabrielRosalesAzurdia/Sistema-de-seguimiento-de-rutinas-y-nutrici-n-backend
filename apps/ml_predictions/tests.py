from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.members.models import Member, User
from apps.routines.models import Routine, RoutineCategory
from apps.tracking.models import DailyNutritionLog, WorkoutSessionLog
from .models import MLPrediction
from .services import (
    MAX_DAYS_TO_GOAL,
    MIN_SESSIONS_FOR_RELIABLE_PREDICTION,
    compute_recent_adherence,
    predict_days_to_goal,
)


class ProgressPredictionDedupTests(TestCase):
    """Feedback: cada carga del dashboard creaba una fila MLPrediction
    nueva (el GET usaba `.create()` sin caché) — ahora reutiliza la
    predicción del día si ya existe una."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ml@test.com", email="ml@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=self.user, first_name="ML", first_last_name="Test", age=25, height_cm="170.0",
            current_weight_kg="80.00", goal_weight_kg="70.00",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_repeated_calls_same_day_reuse_prediction(self):
        r1 = self.client.get("/api/ml/me/progress/")
        r2 = self.client.get("/api/ml/me/progress/")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(MLPrediction.objects.filter(member=self.member).count(), 1)


class RecentAdherenceTests(TestCase):
    """`compute_recent_adherence` reemplaza las constantes fijas 12 y 30
    del cálculo de constancia por los denominadores reales del estudio:
    `Member.planned_training_days` y los "días activos en el sistema"
    (misma lógica que VD2, vía `member_active_window`)."""

    def _member(self, *, planned_training_days=20, activated_days_ago=None):
        user = User.objects.create_user(
            username=f"adh{planned_training_days}-{activated_days_ago}@test.com",
            email=f"adh{planned_training_days}-{activated_days_ago}@test.com",
            password="pass1234",
        )
        member = Member.objects.create(
            user=user, first_name="Adh", first_last_name="Test", age=30, height_cm="170.0",
            current_weight_kg="85.00", goal_weight_kg="78.00",
            planned_training_days=planned_training_days, planned_nutrition_days=30,
        )
        if activated_days_ago is not None:
            activation = timezone.localdate() - timedelta(days=activated_days_ago)
            member.start_date = activation
            member.save(update_fields=["start_date"])
            Member.objects.filter(pk=member.pk).update(
                created_at=timezone.make_aware(
                    timezone.datetime.combine(activation, timezone.datetime.min.time())
                )
            )
            member.refresh_from_db()
        return member

    def _log_workouts(self, member, count):
        routine = Routine.objects.create(category=RoutineCategory.PECHO)
        for _ in range(count):
            WorkoutSessionLog.objects.create(
                member=member, routine=routine, duration_minutes=40,
            )

    def test_training_adherence_uses_planned_training_days_not_constant_12(self):
        member = self._member(planned_training_days=4)
        self._log_workouts(member, 2)
        training, _ = compute_recent_adherence(member)
        self.assertAlmostEqual(training, 0.5)  # 2 / 4, no 2 / 12

    def test_training_adherence_clipped_to_one_when_goal_exceeded(self):
        member = self._member(planned_training_days=2)
        self._log_workouts(member, 5)
        training, _ = compute_recent_adherence(member)
        self.assertEqual(training, 1.0)

    def test_planned_training_days_zero_gives_zero_without_error(self):
        member = self._member(planned_training_days=0)
        self._log_workouts(member, 3)
        training, _ = compute_recent_adherence(member)
        self.assertEqual(training, 0.0)

    def test_nutrition_adherence_uses_active_days_for_recently_activated_member(self):
        # Alta hace 4 días -> 5 días activos (día de alta incluido), no 30.
        member = self._member(activated_days_ago=4)
        for i in range(2):
            DailyNutritionLog.objects.create(
                member=member, date=timezone.localdate() - timedelta(days=i), status="HECHO",
            )
        _, nutrition = compute_recent_adherence(member)
        self.assertAlmostEqual(nutrition, 2 / 5)  # 2 registros / 5 días activos

    def test_nutrition_adherence_clipped_to_one(self):
        member = self._member(activated_days_ago=2)  # 3 días activos
        for i in range(3):
            DailyNutritionLog.objects.create(
                member=member, date=timezone.localdate() - timedelta(days=i), status="HECHO",
            )
        _, nutrition = compute_recent_adherence(member)
        self.assertEqual(nutrition, 1.0)


class MinSessionsForPredictionTests(TestCase):
    """Con pocas sesiones registradas, el denominador de constancia es
    casi cero y tanto la heurística como el Random Forest entrenado
    (misma fórmula, ver ml/training/generate_synthetic_data.py) disparan
    el resultado a cifras de años. Por debajo de
    MIN_SESSIONS_FOR_RELIABLE_PREDICTION sesiones registradas en total,
    predicted_days_to_goal debe ser None en vez de un número absurdo."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="minsessions@test.com", email="minsessions@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=self.user, first_name="Min", first_last_name="Sessions", age=30, height_cm="170.0",
            current_weight_kg="90.00", goal_weight_kg="78.00",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.routine = Routine.objects.create(category=RoutineCategory.PECHO)

    def _log_sessions(self, count):
        for _ in range(count):
            WorkoutSessionLog.objects.create(
                member=self.member, routine=self.routine, duration_minutes=45,
            )

    def test_zero_sessions_returns_none(self):
        result = predict_days_to_goal(self.member, 0.0, 0.0)
        self.assertIsNone(result["days_to_goal"])

    def test_below_threshold_returns_none(self):
        self._log_sessions(MIN_SESSIONS_FOR_RELIABLE_PREDICTION - 1)
        result = predict_days_to_goal(self.member, 0.1, 0.1)
        self.assertIsNone(result["days_to_goal"])

    def test_at_threshold_returns_int_capped_at_max(self):
        """A partir del umbral de sesiones se devuelve un entero, pero
        acotado por MAX_DAYS_TO_GOAL: constancia 0.1 + 12 kg de
        diferencia dispararía la fórmula muy por encima de 2 años."""
        self._log_sessions(MIN_SESSIONS_FOR_RELIABLE_PREDICTION)
        result = predict_days_to_goal(self.member, 0.1, 0.1)
        self.assertIsInstance(result["days_to_goal"], int)
        self.assertLessEqual(result["days_to_goal"], MAX_DAYS_TO_GOAL)

    def test_heuristic_branch_is_also_capped(self):
        """El tope se aplica sobre el resultado final, así que cubre la
        rama de la heurística de respaldo (modelo .joblib ausente), no
        solo la del Random Forest."""
        self._log_sessions(MIN_SESSIONS_FOR_RELIABLE_PREDICTION)
        with patch("apps.ml_predictions.services._load_model", return_value=None):
            result = predict_days_to_goal(self.member, 0.05, 0.05)
        self.assertEqual(result["model_type"], "HEURISTIC_PLACEHOLDER")
        self.assertEqual(result["days_to_goal"], MAX_DAYS_TO_GOAL)

    def test_view_and_serializer_propagate_none_without_error(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/ml/me/progress/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["predicted_days_to_goal"])

    def test_crossing_threshold_same_day_recalculates_instead_of_reusing_null_cache(self):
        """Feedback: si la fila del día quedaba en null, el caché de 'una
        predicción por día' la reutilizaba tal cual — un miembro que
        cruzaba el umbral de sesiones a mitad del día seguía viendo el
        guion hasta el día siguiente. Debe recalcular y actualizar esa
        misma fila en vez de crear una nueva."""
        client = APIClient()
        client.force_authenticate(self.user)

        self._log_sessions(MIN_SESSIONS_FOR_RELIABLE_PREDICTION - 1)
        r1 = client.get("/api/ml/me/progress/")
        self.assertEqual(r1.status_code, 200)
        self.assertIsNone(r1.data["predicted_days_to_goal"])

        self._log_sessions(1)
        r2 = client.get("/api/ml/me/progress/")
        self.assertEqual(r2.status_code, 200)
        self.assertIsInstance(r2.data["predicted_days_to_goal"], int)

        # Misma fila actualizada in-place, no una fila nueva.
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(MLPrediction.objects.filter(member=self.member).count(), 1)
