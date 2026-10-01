from django.utils import timezone
from rest_framework import views, viewsets, permissions
from rest_framework.response import Response

from .models import MLPrediction
from .serializers import MLPredictionSerializer
from .services import compute_recent_adherence, predict_days_to_goal


class MyProgressPredictionView(views.APIView):
    """Calcula la predicción de días para la meta del miembro autenticado,
    para el indicador 'DIAS PARA META' del dashboard de la app."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile

        training_adherence, nutrition_adherence = compute_recent_adherence(member)

        # * Una predicción por miembro por día; se reutiliza salvo que haya
        # quedado en null, caso en que se recalcula hasta cruzar el umbral.
        today_prediction = MLPrediction.objects.filter(
            member=member, created_at__date=timezone.localdate()
        ).order_by("-created_at").first()
        if today_prediction and today_prediction.predicted_days_to_goal is not None:
            return Response(MLPredictionSerializer(today_prediction).data)

        result = predict_days_to_goal(member, training_adherence, nutrition_adherence)
        model_type = result["model_type"]

        if today_prediction:
            today_prediction.model_type = model_type
            today_prediction.input_features = result["input_features"]
            today_prediction.predicted_days_to_goal = result["days_to_goal"]
            today_prediction.save()
            prediction = today_prediction
        else:
            prediction = MLPrediction.objects.create(
                member=member,
                model_type=model_type,
                input_features=result["input_features"],
                predicted_days_to_goal=result["days_to_goal"],
            )

        return Response(MLPredictionSerializer(prediction).data)


class MLPredictionAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """Histórico de predicciones, solo lectura para el panel admin."""

    queryset = MLPrediction.objects.all()
    serializer_class = MLPredictionSerializer
    permission_classes = [permissions.IsAdminUser]
