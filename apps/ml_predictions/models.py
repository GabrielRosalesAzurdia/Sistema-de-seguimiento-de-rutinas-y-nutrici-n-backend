from django.db import models
from apps.members.models import Member


class MLPrediction(models.Model):
    """
    Predicción de progreso hacia la meta del usuario, generada con los
    modelos scikit-learn (LinearRegression / RandomForestRegressor)
    descritos en el Marco Metodológico del anteproyecto. Alimenta el
    indicador "DIAS PARA META" del dashboard y, opcionalmente, la
    generación de un NutritionPlan.
    """

    class ModelType(models.TextChoices):
        LINEAR_REGRESSION = "LINEAR_REGRESSION", "Regresión Lineal"
        RANDOM_FOREST = "RANDOM_FOREST", "Random Forest Regressor"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="ml_predictions")
    model_type = models.CharField(max_length=30, choices=ModelType.choices)
    model_version = models.CharField(max_length=50, default="v1")

    # Features usadas como insumo (ver ml/training/ para el detalle
    # de ingeniería de características)
    input_features = models.JSONField(
        help_text="Snapshot de las variables usadas: edad, IMC, nivel de "
                   "actividad, % constancia entrenamiento, % constancia "
                   "nutricional, peso actual, peso meta, etc."
    )

    predicted_days_to_goal = models.PositiveSmallIntegerField(null=True, blank=True)
    predicted_weight_trajectory = models.JSONField(
        null=True, blank=True,
        help_text="Serie de pesos proyectados (opcional, para graficar).",
    )

    mae = models.FloatField(null=True, blank=True, help_text="Error absoluto medio del modelo en validación.")
    r2_score = models.FloatField(null=True, blank=True, help_text="Coeficiente de determinación R^2.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Predicción de ML"
        verbose_name_plural = "Predicciones de ML"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.member} - {self.model_type} - {self.created_at:%Y-%m-%d}"
