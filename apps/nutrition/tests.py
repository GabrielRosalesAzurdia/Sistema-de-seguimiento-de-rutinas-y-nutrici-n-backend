from django.test import TestCase
from rest_framework.test import APIClient

from apps.members.models import User, Member
from .models import NutritionPlan


class MyCurrentPlanViewTests(TestCase):
    """
    Regla de negocio crítica (CLAUDE.md): un plan pendiente de revisión
    NUNCA debe llegar al miembro — solo planes con status=APPROVED.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="miembro", email="miembro@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=self.user, first_name="Ana", first_last_name="Test", age=25, height_cm="165.0"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_plan(self, status, is_current=True):
        return NutritionPlan.objects.create(
            member=self.member, status=status, total_calories=2000,
            protein_g=140, carbs_g=200, fats_g=60, is_current=is_current,
        )

    def test_pending_plan_is_not_returned(self):
        self._create_plan("PENDING_REVIEW")
        response = self.client.get("/api/nutrition/me/current-plan/")
        self.assertEqual(response.status_code, 404)

    def test_rejected_plan_is_not_returned(self):
        self._create_plan("REJECTED")
        response = self.client.get("/api/nutrition/me/current-plan/")
        self.assertEqual(response.status_code, 404)

    def test_no_plan_at_all_returns_clean_404_not_500(self):
        # Regresión: get_object() usaba .latest() sin capturar
        # DoesNotExist y devolvía un 500 sin manejar.
        response = self.client.get("/api/nutrition/me/current-plan/")
        self.assertEqual(response.status_code, 404)

    def test_approved_plan_is_returned(self):
        self._create_plan("APPROVED")
        response = self.client.get("/api/nutrition/me/current-plan/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "APPROVED")
