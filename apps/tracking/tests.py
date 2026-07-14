from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.members.models import User, Member
from apps.routines.models import Routine, RoutineCategory
from .models import WorkoutSessionLog
from .services import compute_total_calories_burned, compute_workout_streak


class WorkoutStreakAndCaloriesTests(TestCase):
    """Track F.3 — cálculo puro de racha/calorías, la regla más fácil
    de romper sin darse cuenta al tocar WorkoutSessionLog."""

    def setUp(self):
        self.member = Member.objects.create(
            first_name="Test", first_last_name="User", age=25, height_cm="170.0"
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
            user=self.member_user, first_name="M", first_last_name="N", age=20, height_cm="170.0"
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
