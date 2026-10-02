import csv
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import mixins, viewsets, permissions, views
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from common.permissions import IsCoach, IsOwnerOrCoach
from apps.members.models import Member
from .models import WorkoutSessionLog, WorkoutExerciseEntry, DailyNutritionLog, BodyMeasurementLog
from .daily_export import build_daily_workbook, build_key_rows
from .serializers import (
    WorkoutSessionLogSerializer, WorkoutSessionHistorySerializer,
    DailyNutritionLogSerializer, BodyMeasurementLogSerializer,
)
from .services import (
    InvalidStudyRange,
    compute_study_metrics,
    compute_total_calories_burned,
    compute_workout_streak,
    parse_study_range,
)


class WorkoutSessionLogViewSet(viewsets.ModelViewSet):
    """Registro de rutina completada (pantalla 'Registrar')."""

    serializer_class = WorkoutSessionLogSerializer
    permission_classes = [IsOwnerOrCoach]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return WorkoutSessionLog.objects.all().prefetch_related("exercise_entries")
        return WorkoutSessionLog.objects.filter(member=user.member_profile)


class MyWorkoutHistoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Historial de sesiones del miembro autenticado, de solo lectura
    (pantalla 'Historial' de la app), paginado y ordenado por fecha descendente."""
    serializer_class = WorkoutSessionHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            WorkoutSessionLog.objects
            .filter(member=self.request.user.member_profile)
            .select_related("routine")
            .prefetch_related("exercise_entries__exercise")
        )


class MyExerciseProgressView(views.APIView):
    """Progreso de peso final para un ejercicio, a través de todas las
    sesiones históricas del miembro autenticado (gráfica de Historial)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exercise_id):
        member = request.user.member_profile
        entries = (
            WorkoutExerciseEntry.objects
            .filter(session__member=member, exercise_id=exercise_id)
            .select_related("session")
            .order_by("session__completed_at")
        )
        return Response([
            {
                "date": entry.session.completed_at.date(),
                "final_weight_lb": entry.final_weight_lb,
            }
            for entry in entries
        ])


class DailyNutritionLogViewSet(viewsets.ModelViewSet):
    """Semáforo diario de nutrición (dashboard: HECHO / PARCIALMENTE / SE_ME_FUE)."""

    serializer_class = DailyNutritionLogSerializer
    permission_classes = [IsOwnerOrCoach]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return DailyNutritionLog.objects.all()
        return DailyNutritionLog.objects.filter(member=user.member_profile)


class BodyMeasurementLogViewSet(viewsets.ModelViewSet):
    """Registro mensual de peso/medidas: SOLO el coach puede crear (panel admin)."""

    serializer_class = BodyMeasurementLogSerializer
    permission_classes = [IsCoach]
    queryset = BodyMeasurementLog.objects.all()

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class MyWeightHistoryView(views.APIView):
    """Historial de peso del propio miembro autenticado, para la gráfica
    del dashboard (card "PESO ACTUAL / META"). Solo lectura."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile
        logs = BodyMeasurementLog.objects.filter(member=member).order_by("date")
        return Response([
            {"date": log.date, "weight_kg": log.weight_kg} for log in logs
        ])


class MyTrackingSummaryView(views.APIView):
    """Resumen del miembro autenticado para las cards "CALORÍAS QUEMADAS
    EN TOTAL" y "RACHA" del dashboard."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile
        return Response({
            "total_calories_burned": compute_total_calories_burned(member),
            "streak_days": compute_workout_streak(member),
        })


class StudyExportView(views.APIView):
    """Exportación CSV de VD1/VD2 por miembro, para la pantalla 'Datos
    del estudio' del panel. Acepta JWT o sesión de Django."""
    permission_classes = [IsCoach]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        try:
            parse_study_range(start, end)
        except InvalidStudyRange as exc:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="estudio_constancia.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Nombre", "Sesiones planificadas", "Sesiones completadas", "VD1 %",
            "Días activos", "Días con registro nutricional", "VD2 %",
            "VD1 - Frecuencia semanal", "VD1 - Duración promedio (min)", "VD1 - Variación %",
            "VD2 - Frecuencia semanal", "VD2 - % semanas con mínimo", "VD2 - Variación %",
        ])

        for m in compute_study_metrics(start, end):
            writer.writerow([
                m["name"], m["planned"], m["completed"], m["vd1"],
                m["active_days"], m["days_with_log"], m["vd2"],
                m["vd1_weekly_freq"], m["vd1_avg_duration"], m["vd1_variation"] if m["vd1_variation"] is not None else "",
                m["vd2_weekly_freq"], m["vd2_weeks_min_pct"], m["vd2_variation"] if m["vd2_variation"] is not None else "",
            ])

        return response


class StudyDailyExportView(views.APIView):
    """Exportación diaria por participante (.xlsx para las fichas de
    observación). Solo códigos P01..., sin nombres: la clave va aparte."""
    permission_classes = [IsCoach]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        try:
            content = build_daily_workbook(
                request.query_params.get("start") or None,
                request.query_params.get("end") or None,
            )
        except InvalidStudyRange as exc:
            return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")

        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="estudio_diario.xlsx"'
        return response


class StudyKeyExportView(views.APIView):
    """clave_participantes.csv: código, nombre, fecha de alta y estado.
    Se descarga aparte del .xlsx diario."""
    permission_classes = [IsCoach]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="clave_participantes.csv"'
        writer = csv.writer(response)
        writer.writerow(["Código", "Nombre", "Fecha de alta", "Estado"])
        writer.writerows(build_key_rows())
        return response
