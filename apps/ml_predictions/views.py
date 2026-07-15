from datetime import timedelta
from django.utils import timezone
from rest_framework import views, viewsets, permissions
from rest_framework.response import Response

from apps.tracking.models import WorkoutSessionLog, DailyNutritionLog
from .models import MLPrediction
from .serializers import MLPredictionSerializer
from .services import predict_days_to_goal


class MyProgressPredictionView(views.APIView):
    """
    Calcula y devuelve la predicción de días para alcanzar la meta del
    miembro autenticado, usada en el indicador 'DIAS PARA META' del
    dashboard de la app.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile
        window_start = timezone.now() - timedelta(days=30)

        recent_workouts = WorkoutSessionLog.objects.filter(
            member=member, completed_at__gte=window_start
        ).count()
        # Referencia simple: se asume ~12 sesiones planificadas en 30 días
        # (aprox. 3 por semana) hasta contar con la definición operacional
        # final de "planificadas" acordada con el asesor.
        training_adherence = min(recent_workouts / 12, 1.0)

        recent_nutrition_days = DailyNutritionLog.objects.filter(
            member=member, date__gte=window_start.date()
        ).count()
        nutrition_adherence = min(recent_nutrition_days / 30, 1.0)

        # Una predicción por miembro por día: si ya se calculó una hoy
        # (p. ej. el dashboard hace varias cargas/refrescos), se
        # reutiliza en vez de crear una fila nueva en cada GET (antes
        # esto inundaba la tabla de MLPrediction con filas RANDOM_FOREST
        # repetidas — feedback de la prueba E2E).
        today_prediction = MLPrediction.objects.filter(
            member=member, created_at__date=timezone.localdate()
        ).order_by("-created_at").first()
        if today_prediction:
            return Response(MLPredictionSerializer(today_prediction).data)

        result = predict_days_to_goal(member, training_adherence, nutrition_adherence)

        prediction = MLPrediction.objects.create(
            member=member,
            model_type=result["model_type"] if result["model_type"] in dict(MLPrediction.ModelType.choices) else MLPrediction.ModelType.RANDOM_FOREST,
            input_features=result["input_features"],
            predicted_days_to_goal=result["days_to_goal"],
        )

        return Response(MLPredictionSerializer(prediction).data)


class MLPredictionAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """Histórico de predicciones, solo lectura para el panel admin."""

    queryset = MLPrediction.objects.all()
    serializer_class = MLPredictionSerializer
    permission_classes = [permissions.IsAdminUser]
