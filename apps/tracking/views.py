import csv
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import viewsets, permissions, views
from rest_framework.response import Response

from common.permissions import IsCoach, IsOwnerOrCoach
from apps.members.models import Member
from .models import WorkoutSessionLog, DailyNutritionLog, BodyMeasurementLog
from .serializers import (
    WorkoutSessionLogSerializer, DailyNutritionLogSerializer, BodyMeasurementLogSerializer,
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


class StudyExportView(views.APIView):
    """
    Exportación CSV de VD1 (constancia al entrenamiento) y VD2
    (constancia nutricional) para el período de implementación
    octubre-noviembre 2026, replicando la pantalla 'Datos del estudio'
    del panel admin (Exportador de Datos de Estudio).

    Uso: GET /api/tracking/study-export/?start=2026-10-01&end=2026-11-30
    """
    permission_classes = [IsCoach]

    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="estudio_constancia.csv"'
        writer = csv.writer(response)
        writer.writerow(["Nombre", "Sesiones planificadas", "Sesiones completadas", "VD1 %", "Días activos", "Días con registro nutricional", "VD2 %"])

        members = Member.objects.filter(participates_in_study=True)
        for member in members:
            workouts = member.workout_logs.all()
            nutrition_logs = member.nutrition_logs.all()
            if start:
                workouts = workouts.filter(completed_at__date__gte=start)
                nutrition_logs = nutrition_logs.filter(date__gte=start)
            if end:
                workouts = workouts.filter(completed_at__date__lte=end)
                nutrition_logs = nutrition_logs.filter(date__lte=end)

            completed = workouts.count()
            # NOTA: "planificadas" depende de la definición operacional acordada
            # con el asesor (p.ej. sesiones esperadas por semana * semanas activas).
            # Placeholder: usar completadas como referencia hasta implementar el
            # cálculo real de sesiones planificadas por miembro.
            planned = completed
            vd1 = round((completed / planned) * 100, 1) if planned else 0

            days_active = (member.workout_logs.count() or 0)
            days_with_log = nutrition_logs.count()
            vd2 = round((days_with_log / days_active) * 100, 1) if days_active else 0

            writer.writerow([
                member.full_name, planned, completed, vd1, days_active, days_with_log, vd2,
            ])

        return response
