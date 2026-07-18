from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.members.models import User, Member
from apps.routines.models import Routine, RoutineCategory
from .models import WorkoutSessionLog, DailyNutritionLog
from .services import compute_total_calories_burned, compute_workout_streak, compute_study_metrics


class WorkoutStreakAndCaloriesTests(TestCase):
    """Track F.3 — cálculo puro de racha/calorías, la regla más fácil
    de romper sin darse cuenta al tocar WorkoutSessionLog."""

    def setUp(self):
        user = User.objects.create_user(
            username="racha@test.com", email="racha@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=user, first_name="Test", first_last_name="User", age=25, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.routine = Routine.objects.create(category=RoutineCategory.PECHO)

    def _log_on(self, day):
        log = WorkoutSessionLog.objects.create(
            member=self.member, routine=self.routine, duration_minutes=45, calories_burned=300,
        )
        WorkoutSessionLog.objects.filter(pk=log.pk).update(
            completed_at=timezone.make_aware(
                timezone.datetime.combine(day, timezone.datetime.min.time()) + timedelta(hours=12)
            )
        )

    def test_streak_counts_consecutive_days_ending_today(self):
        today = timezone.localdate()
        for i in range(3):
            self._log_on(today - timedelta(days=i))
        self.assertEqual(compute_workout_streak(self.member), 3)

    def test_streak_breaks_on_gap(self):
        today = timezone.localdate()
        self._log_on(today)
        self._log_on(today - timedelta(days=2))  # hueco en day-1
        self.assertEqual(compute_workout_streak(self.member), 1)

    def test_streak_counts_from_yesterday_if_today_missing(self):
        today = timezone.localdate()
        self._log_on(today - timedelta(days=1))
        self._log_on(today - timedelta(days=2))
        self.assertEqual(compute_workout_streak(self.member), 2)

    def test_streak_is_zero_with_no_logs(self):
        self.assertEqual(compute_workout_streak(self.member), 0)

    def test_total_calories_sum(self):
        for i in range(3):
            self._log_on(timezone.localdate() - timedelta(days=i))
        self.assertEqual(compute_total_calories_burned(self.member), 900)

    def test_total_calories_zero_with_no_logs(self):
        self.assertEqual(compute_total_calories_burned(self.member), 0)


class IsCoachPermissionTests(TestCase):
    """Límites de permisos (common/permissions.py, Track E.1): un
    miembro normal no debe poder entrar a endpoints coach-only."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", email="coach@test.com", password="pass1234", is_staff=True
        )
        self.member_user = User.objects.create_user(
            username="member", email="member@test.com", password="pass1234", is_staff=False
        )
        Member.objects.create(
            user=self.member_user, first_name="M", first_last_name="N", age=20, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=30,
        )

    def test_non_coach_cannot_list_members_admin(self):
        client = APIClient()
        client.force_authenticate(self.member_user)
        response = client.get("/api/members/")
        self.assertEqual(response.status_code, 403)

    def test_coach_can_list_members_admin(self):
        client = APIClient()
        client.force_authenticate(self.coach)
        response = client.get("/api/members/")
        self.assertEqual(response.status_code, 200)

    def test_non_coach_cannot_access_study_export(self):
        client = APIClient()
        client.force_authenticate(self.member_user)
        response = client.get("/api/tracking/study-export/")
        self.assertEqual(response.status_code, 403)


class CaloriesBurnedDerivedFromRoutineTests(TestCase):
    """Feedback: calories_burned se quedaba en NULL/0 porque nada lo
    derivaba de la rutina completada — ahora el serializer lo fuerza
    desde `routine.estimated_calories`, ignorando lo que mande el
    cliente."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="calorias@test.com", email="calorias@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=self.user, first_name="Cal", first_last_name="Test", age=25, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.routine = Routine.objects.create(
            category=RoutineCategory.PECHO, estimated_calories=400,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_calories_burned_is_set_from_routine_even_if_client_sends_none(self):
        response = self.client.post("/api/tracking/workout-logs/", {
            "routine": self.routine.pk, "duration_minutes": 40, "exercise_entries": [],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        log = WorkoutSessionLog.objects.get(pk=response.data["id"])
        self.assertEqual(log.calories_burned, 400)


class StudyMetricsPlannedDaysTests(TestCase):
    """Feedback: VD1/VD2 usaban un placeholder (planificadas =
    completadas, o "días activos" confuso). Ahora el denominador es la
    meta individual (planned_training_days/planned_nutrition_days) que
    define el coach, sin tope al 100% si el miembro la supera."""

    def setUp(self):
        user = User.objects.create_user(
            username="estudio@test.com", email="estudio@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=user, first_name="Estudio", first_last_name="Test", age=25, height_cm="170.0",
            planned_training_days=10, planned_nutrition_days=10, participates_in_study=True,
        )
        self.routine = Routine.objects.create(category=RoutineCategory.PECHO, estimated_calories=300)

    def test_vd1_uses_planned_training_days_as_denominator(self):
        for i in range(5):
            WorkoutSessionLog.objects.create(
                member=self.member, routine=self.routine, duration_minutes=30, calories_burned=300,
            )
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["planned"], 10)
        self.assertEqual(row["completed"], 5)
        self.assertEqual(row["vd1"], 50.0)

    def test_vd1_can_exceed_100_percent_without_cap(self):
        for i in range(15):
            WorkoutSessionLog.objects.create(
                member=self.member, routine=self.routine, duration_minutes=30, calories_burned=300,
            )
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["vd1"], 150.0)

    def test_vd2_uses_planned_nutrition_days_as_denominator(self):
        today = timezone.localdate()
        for i in range(3):
            DailyNutritionLog.objects.create(member=self.member, date=today - timedelta(days=i), status="HECHO")
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["planned_nutrition"], 10)
        self.assertEqual(row["days_with_log"], 3)
        self.assertEqual(row["vd2"], 30.0)

    def test_deactivated_member_is_excluded_from_metrics(self):
        # Feedback prueba E2E v3: un miembro desactivado seguía
        # contando para VD1/VD2 aunque ya no forme parte del gimnasio.
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        metrics = compute_study_metrics()
        self.assertFalse(any(m["member"] == self.member for m in metrics))
