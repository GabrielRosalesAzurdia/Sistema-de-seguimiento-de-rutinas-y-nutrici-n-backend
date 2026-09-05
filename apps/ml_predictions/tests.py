from django.test import TestCase
from rest_framework.test import APIClient

from apps.members.models import Member, User
from apps.routines.models import Routine, RoutineCategory
from apps.tracking.models import WorkoutSessionLog
from .models import MLPrediction
from .services import MIN_SESSIONS_FOR_RELIABLE_PREDICTION, predict_days_to_goal


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

    def test_at_threshold_returns_unbounded_int(self):
        self._log_sessions(MIN_SESSIONS_FOR_RELIABLE_PREDICTION)
        result = predict_days_to_goal(self.member, 0.1, 0.1)
        self.assertIsInstance(result["days_to_goal"], int)

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
