from django.test import TestCase
from rest_framework.test import APIClient

from apps.members.models import Member, User
from .models import MLPrediction


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
