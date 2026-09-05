from django.utils import timezone
from rest_framework import views, viewsets, permissions
from rest_framework.response import Response

from .models import MLPrediction
from .serializers import MLPredictionSerializer
from .services import compute_recent_adherence, predict_days_to_goal


class MyProgressPredictionView(views.APIView):
    """
    Calcula y devuelve la predicción de días para alcanzar la meta del
    miembro autenticado, usada en el indicador 'DIAS PARA META' del
    dashboard de la app.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = request.user.member_profile

        # Constancia reciente calculada con los denominadores reales del
        # estudio (planned_training_days y días activos), no constantes
        # fijas — ver apps/ml_predictions/services.py::compute_recent_adherence.
        training_adherence, nutrition_adherence = compute_recent_adherence(member)

        # Una predicción por miembro por día: si ya se calculó una hoy
        # (p. ej. el dashboard hace varias cargas/refrescos), se
        # reutiliza en vez de crear una fila nueva en cada GET (antes
        # esto inundaba la tabla de MLPrediction con filas RANDOM_FOREST
        # repetidas — feedback de la prueba E2E). Excepción: si la
        # predicción del día quedó en null por datos insuficientes, NO
        # se reutiliza — se recalcula en cada carga hasta que el
        # miembro cruce el umbral de sesiones (si no, un miembro que
        # cruza el umbral a mitad del día seguía viendo el guion hasta
        # el día siguiente).
        today_prediction = MLPrediction.objects.filter(
            member=member, created_at__date=timezone.localdate()
        ).order_by("-created_at").first()
        if today_prediction and today_prediction.predicted_days_to_goal is not None:
            return Response(MLPredictionSerializer(today_prediction).data)

        result = predict_days_to_goal(member, training_adherence, nutrition_adherence)
        # El origen del valor (modelo entrenado vs. heurística de
        # respaldo) se persiste tal cual lo reporta el servicio: todos
        # los valores posibles están en MLPrediction.ModelType, incluido
        # HEURISTIC_PLACEHOLDER, así que ya no hace falta reescribirlo.
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
