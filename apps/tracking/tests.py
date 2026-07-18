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
    """VD1 no cambió en la ronda de feedback v4: el denominador sigue
    siendo la meta individual (planned_training_days) que define el
    coach, sin tope al 100% si el miembro la supera."""

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

    def test_deactivated_member_is_excluded_from_metrics(self):
        # Feedback prueba E2E v3: un miembro desactivado seguía
        # contando para VD1/VD2 aunque ya no forme parte del gimnasio.
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        metrics = compute_study_metrics()
        self.assertFalse(any(m["member"] == self.member for m in metrics))


class StudyMetricsVD2ActiveDaysTests(TestCase):
    """Feedback prueba E2E v4: el Anteproyecto (Capítulo I) define el
    denominador de VD2 como "días activos en el sistema", no la meta
    individual planned_nutrition_days (esa sigue siendo el denominador
    de VD1 únicamente). Día activo = desde
    max(start_date, created_at) hasta el cutoff del rango (hoy si no
    hay fin, o el fin si ya pasó), acotado siempre al rango
    solicitado."""

    def setUp(self):
        user = User.objects.create_user(
            username="vd2activo@test.com", email="vd2activo@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=user, first_name="VD2", first_last_name="Activo", age=25, height_cm="170.0",
            planned_training_days=10, planned_nutrition_days=10, participates_in_study=True,
        )

    def _backdate(self, start_date, created_at_date):
        self.member.start_date = start_date
        self.member.save(update_fields=["start_date"])
        Member.objects.filter(pk=self.member.pk).update(
            created_at=timezone.make_aware(
                timezone.datetime.combine(created_at_date, timezone.datetime.min.time())
            )
        )
        self.member.refresh_from_db()

    def test_vd2_uses_active_days_as_denominator(self):
        today = timezone.localdate()
        activation = today - timedelta(days=9)  # 10 días activos: activation..today
        self._backdate(start_date=activation, created_at_date=activation)
        for i in range(3):
            DailyNutritionLog.objects.create(member=self.member, date=today - timedelta(days=i), status="HECHO")
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["active_days"], 10)
        self.assertEqual(row["days_with_log"], 3)
        self.assertEqual(row["vd2"], 30.0)

    def test_activation_date_uses_later_of_start_date_and_created_at(self):
        today = timezone.localdate()
        # start_date muy retroactivo (30 días atrás) pero el registro
        # del Member se creó realmente hace solo 5 días -> el
        # denominador debe arrancar en created_at, no en start_date.
        self._backdate(start_date=today - timedelta(days=30), created_at_date=today - timedelta(days=4))
        DailyNutritionLog.objects.create(member=self.member, date=today, status="HECHO")
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["active_days"], 5)  # created_at..hoy = 5 días

    def test_active_days_clamped_to_requested_range(self):
        today = timezone.localdate()
        self._backdate(start_date=today - timedelta(days=60), created_at_date=today - timedelta(days=60))
        DailyNutritionLog.objects.create(member=self.member, date=today - timedelta(days=5), status="HECHO")
        start = (today - timedelta(days=9)).isoformat()
        end = today.isoformat()
        metrics = compute_study_metrics(start, end)
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["active_days"], 10)  # acotado al rango solicitado, no a los 60 días reales

    def test_vd2_is_zero_when_member_activates_after_range_cutoff(self):
        today = timezone.localdate()
        self._backdate(start_date=today, created_at_date=today)
        start = (today - timedelta(days=20)).isoformat()
        end = (today - timedelta(days=10)).isoformat()
        metrics = compute_study_metrics(start, end)
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["active_days"], 0)
        self.assertEqual(row["vd2"], 0)


class StudyMetricsSecondaryIndicatorsTests(TestCase):
    """6 indicadores secundarios de la matriz operacional (feedback
    prueba E2E v4), calculados sobre la MISMA ventana [comp_start,
    cutoff] que ya delimita "días activos" de VD2 — así que un
    miembro que se unió a mitad del rango solicitado ve sus
    semanas/mitades contadas desde su propia fecha de activación."""

    def setUp(self):
        user = User.objects.create_user(
            username="indicadores@test.com", email="indicadores@test.com", password="pass1234"
        )
        self.member = Member.objects.create(
            user=user, first_name="Indicadores", first_last_name="Test", age=25, height_cm="170.0",
            planned_training_days=20, planned_nutrition_days=20, participates_in_study=True,
        )
        self.routine = Routine.objects.create(category=RoutineCategory.PECHO, estimated_calories=300)

    def _backdate(self, start_date, created_at_date):
        self.member.start_date = start_date
        self.member.save(update_fields=["start_date"])
        Member.objects.filter(pk=self.member.pk).update(
            created_at=timezone.make_aware(
                timezone.datetime.combine(created_at_date, timezone.datetime.min.time())
            )
        )
        self.member.refresh_from_db()

    def _log_workout_on(self, day):
        log = WorkoutSessionLog.objects.create(
            member=self.member, routine=self.routine, duration_minutes=40, calories_burned=300,
        )
        WorkoutSessionLog.objects.filter(pk=log.pk).update(
            completed_at=timezone.make_aware(
                timezone.datetime.combine(day, timezone.datetime.min.time()) + timedelta(hours=12)
            )
        )

    def test_num_weeks_uses_activation_date_not_range_start_when_member_joins_mid_range(self):
        today = timezone.localdate()
        # Rango solicitado: 21 días -> 3 semanas si se contaran desde
        # range_start. Pero el miembro se activó hace solo 6 días, así
        # que la ventana real es de 7 días -> num_weeks debe ser 1.
        activation = today - timedelta(days=6)
        self._backdate(start_date=activation, created_at_date=activation)
        for i in range(3):
            self._log_workout_on(today - timedelta(days=i))
        start = (today - timedelta(days=20)).isoformat()
        end = today.isoformat()
        metrics = compute_study_metrics(start, end)
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["active_days"], 7)
        self.assertEqual(row["vd1_weekly_freq"], 3.0)  # 3 sesiones / 1 semana, no / 3 semanas

    def test_week_bucket_not_multiple_of_seven(self):
        today = timezone.localdate()
        activation = today - timedelta(days=9)  # 10 días -> num_weeks = ceil(10/7) = 2
        self._backdate(start_date=activation, created_at_date=activation)
        for i in [9, 8, 7, 2, 1]:  # 3 logs en semana 1, 2 logs en semana 2 (incompleta)
            self._log_workout_on(today - timedelta(days=i))
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["vd1_weekly_freq"], 2.5)  # 5 sesiones / 2 semanas

    def test_vd2_weeks_min_pct(self):
        today = timezone.localdate()
        activation = today - timedelta(days=13)  # 14 días -> num_weeks = 2
        self._backdate(start_date=activation, created_at_date=activation)
        for i in [13, 12, 11]:  # semana 1: 3 registros -> cumple mínimo
            DailyNutritionLog.objects.create(member=self.member, date=today - timedelta(days=i), status="HECHO")
        DailyNutritionLog.objects.create(member=self.member, date=today, status="HECHO")  # semana 2: 1 registro
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["vd2_weeks_min_pct"], 50.0)

    def test_variation_is_second_half_minus_first_half(self):
        today = timezone.localdate()
        activation = today - timedelta(days=9)  # 10 días -> mitades de 5 días c/u
        self._backdate(start_date=activation, created_at_date=activation)
        self._log_workout_on(activation)  # 1 sesión en la primera mitad -> 1/20 = 5%
        for i in range(3):
            self._log_workout_on(today - timedelta(days=i))  # 3 sesiones en la segunda mitad -> 3/20 = 15%
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertEqual(row["vd1_variation"], 10.0)  # 15% - 5%

    def test_variation_is_blank_with_less_than_two_weeks(self):
        today = timezone.localdate()
        activation = today - timedelta(days=5)  # 6 días -> num_weeks = 1
        self._backdate(start_date=activation, created_at_date=activation)
        metrics = compute_study_metrics()
        row = next(m for m in metrics if m["member"] == self.member)
        self.assertIsNone(row["vd1_variation"])
        self.assertIsNone(row["vd2_variation"])
