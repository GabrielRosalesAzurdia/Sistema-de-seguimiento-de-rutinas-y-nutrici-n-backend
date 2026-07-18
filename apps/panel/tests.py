import datetime

from django.test import TestCase, Client
from django.urls import reverse

from apps.members.models import Member, User
from apps.nutrition.models import NutritionPlan, MealSuggestion, MealTime
from .utils import add_one_month
from .views import MealSuggestionFormSet


class AddOneMonthTests(TestCase):
    def test_adds_a_month(self):
        self.assertEqual(add_one_month(datetime.date(2026, 6, 1)), datetime.date(2026, 7, 1))

    def test_rolls_over_year(self):
        self.assertEqual(add_one_month(datetime.date(2026, 12, 15)), datetime.date(2027, 1, 15))

    def test_clamps_day_to_shorter_month(self):
        self.assertEqual(add_one_month(datetime.date(2026, 1, 31)), datetime.date(2026, 2, 28))


class MemberCreateViewTests(TestCase):
    """Feedback: al crear un miembro no se creaba su User (no podía
    loguearse en la app) — ahora el panel lo crea con contraseña
    autogenerada, mostrada una sola vez."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach@test.com", email="coach@test.com", password="pass1234", is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.coach)

    def test_creating_member_creates_linked_user_with_password(self):
        response = self.client.post(reverse("panel:member-create"), {
            "first_name": "Nueva", "first_last_name": "Persona",
            "email": "nueva.persona@test.com", "phone": "555",
            "age": 22, "start_date": "2026-07-01",
            "gender": "MUJER", "height_cm": "160.0",
            "fitness_goal": "PERDER_PESO", "activity_level": "MODERADO",
            "planned_training_days": 20, "planned_nutrition_days": 30,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        member = Member.objects.get(first_name="Nueva")
        self.assertIsNotNone(member.user_id)
        self.assertEqual(member.user.email, "nueva.persona@test.com")
        self.assertTrue(member.user.has_usable_password())
        self.assertIsNotNone(member.next_payment_date)
        self.assertEqual(member.next_payment_date, add_one_month(member.start_date))


class MarkPaidRecalculatesNextPaymentTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach2@test.com", email="coach2@test.com", password="pass1234", is_staff=True
        )
        member_user = User.objects.create_user(
            username="miembro2@test.com", email="miembro2@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=member_user, first_name="Ana", first_last_name="Gomez", age=30, height_cm="160.0",
            start_date=datetime.date(2026, 1, 1), planned_training_days=20, planned_nutrition_days=30,
        )
        self.client = Client()
        self.client.force_login(self.coach)

    def test_mark_paid_advances_next_payment_one_month_from_today(self):
        from django.utils import timezone
        self.client.post(reverse("panel:member-update", args=[self.member.pk]), {
            "first_name": self.member.first_name, "first_last_name": self.member.first_last_name,
            "email": self.member.user.email, "age": 30, "start_date": "2026-01-01",
            "height_cm": "160.0", "fitness_goal": "PERDER_PESO", "activity_level": "MODERADO",
            "planned_training_days": 20, "planned_nutrition_days": 30,
            "mark_paid": "1",
        })
        self.member.refresh_from_db()
        self.assertEqual(self.member.next_payment_date, add_one_month(timezone.localdate()))


class NutritionPlanSupersedeTests(TestCase):
    """Feedback prueba E2E v3: al aprobar un plan sucesor, el plan
    viejo se quedaba con status=APPROVED para siempre (solo
    is_current pasaba a False), así que aparecía duplicado en
    'Aprobadas y en Seguimiento', y "Rechazarlo" disparaba otra
    generación automática, acumulando planes 'activos' para el mismo
    miembro. Ahora el plan viejo pasa a status=SUPERSEDED y su
    detalle queda de solo lectura."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach3@test.com", email="coach3@test.com", password="pass1234", is_staff=True
        )
        member_user = User.objects.create_user(
            username="miembro3@test.com", email="miembro3@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=member_user, first_name="Luis", first_last_name="Perez", age=28, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.client = Client()
        self.client.force_login(self.coach)

    def _make_plan(self, status, is_current=False):
        plan = NutritionPlan.objects.create(
            member=self.member, status=status, total_calories=2000,
            protein_g=140, carbs_g=200, fats_g=60, is_current=is_current,
        )
        for meal_time, _label in MealTime.choices:
            MealSuggestion.objects.create(
                plan=plan, meal_time=meal_time, carbs_g=40, protein_g=28,
                fats_g=12, calories=400,
            )
        return plan

    def _meal_post_data(self, plan, action):
        formset = MealSuggestionFormSet(instance=plan)
        prefix = formset.prefix
        data = {
            "action": action,
            f"{prefix}-TOTAL_FORMS": str(len(formset.forms)),
            f"{prefix}-INITIAL_FORMS": str(len(formset.forms)),
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
        for form in formset.forms:
            for field in ["id", "carbs_g", "protein_g", "fats_g", "calories",
                          "suggestion_1", "suggestion_2", "suggestion_3"]:
                bound = form[field]
                value = bound.value()
                data[bound.html_name] = "" if value is None else value
        return data

    def test_approving_successor_supersedes_old_plan_instead_of_duplicating(self):
        old_plan = self._make_plan("APPROVED", is_current=True)
        new_plan = self._make_plan("PENDING_REVIEW")

        response = self.client.post(
            reverse("panel:nutrition-plan-detail", args=[new_plan.pk]),
            self._meal_post_data(new_plan, "approve"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        old_plan.refresh_from_db()
        new_plan.refresh_from_db()
        self.assertEqual(old_plan.status, "SUPERSEDED")
        self.assertFalse(old_plan.is_current)
        self.assertEqual(new_plan.status, "APPROVED")
        self.assertTrue(new_plan.is_current)

        response = self.client.get(reverse("panel:nutrition-review"))
        approved_ids = [p.pk for p in response.context["approved"]]
        self.assertEqual(approved_ids, [new_plan.pk])

    def test_rejecting_superseded_plan_is_blocked_and_does_not_duplicate(self):
        old_plan = self._make_plan("SUPERSEDED", is_current=False)
        plans_before = NutritionPlan.objects.filter(member=self.member).count()

        response = self.client.post(
            reverse("panel:nutrition-plan-detail", args=[old_plan.pk]),
            self._meal_post_data(old_plan, "reject"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        old_plan.refresh_from_db()
        self.assertEqual(old_plan.status, "SUPERSEDED")
        self.assertEqual(
            NutritionPlan.objects.filter(member=self.member).count(), plans_before
        )
