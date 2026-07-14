import csv
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import viewsets, permissions, views
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from common.permissions import IsCoach, IsOwnerOrCoach
from apps.members.models import Member
from .models import WorkoutSessionLog, DailyNutritionLog, BodyMeasurementLog
from .serializers import (
    WorkoutSessionLogSerializer, DailyNutritionLogSerializer, BodyMeasurementLogSerializer,
)
from .services import compute_study_metrics, compute_total_calories_burned, compute_workout_streak


class WorkoutSessionLogViewSet(viewsets.ModelViewSet):
    """Registro de rutina completada (pantalla 'Registrar')."""

    serializer_class = WorkoutSessionLogSerializer
    permission_classes = [IsOwnerOrCoach]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return WorkoutSessionLog.objects.all().prefetch_related("exercise_entries")
        return WorkoutSessionLog.objects.filter(member=user.member_profile)


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
    """
    Historial de peso del propio miembro autenticado, para la gráfica
    del dashboard (docs/mockups/app/03_dashboard.jpeg — línea de peso
    dentro de la card "PESO ACTUAL / META"). `BodyMeasurementLogViewSet`
    es coach-only y sin filtro "mío"; esta vista es de solo lectura y
    exclusiva para que el propio miembro vea su historial.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile
        logs = BodyMeasurementLog.objects.filter(member=member).order_by("date")
        return Response([
            {"date": log.date, "weight_kg": log.weight_kg} for log in logs
        ])


class MyTrackingSummaryView(views.APIView):
    """
    Resumen del miembro autenticado para las cards "CALORÍAS QUEMADAS
    EN TOTAL" y "RACHA" del dashboard (antes ausentes, ver
    docs/mockups/app/03_dashboard.jpeg).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile
        return Response({
            "total_calories_burned": compute_total_calories_burned(member),
            "streak_days": compute_workout_streak(member),
        })


class StudyExportView(views.APIView):
    """
    Exportación CSV de VD1 (constancia al entrenamiento) y VD2
    (constancia nutricional) para el período de implementación
    octubre-noviembre 2026, replicando la pantalla 'Datos del estudio'
    del panel admin (Exportador de Datos de Estudio).

    Uso: GET /api/tracking/study-export/?start=2026-10-01&end=2026-11-30

    Acepta JWT (consumo API normal) o sesión de Django (link directo
    desde la pantalla "Datos del estudio" del panel, que autentica por
    sesión en vez de JWT).
    """
    permission_classes = [IsCoach]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="estudio_constancia.csv"'
        writer = csv.writer(response)
        writer.writerow(["Nombre", "Sesiones planificadas", "Sesiones completadas", "VD1 %", "Días activos", "Días con registro nutricional", "VD2 %"])

        for m in compute_study_metrics(start, end):
            writer.writerow([
                m["name"], m["planned"], m["completed"], m["vd1"],
                m["days_active"], m["days_with_log"], m["vd2"],
            ])

        return response
