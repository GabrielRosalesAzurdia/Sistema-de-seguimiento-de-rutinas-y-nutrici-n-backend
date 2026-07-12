from django.db import models
from apps.members.models import Member


class MealTime(models.TextChoices):
    """
    5 tiempos de comida (D3, reunión 2: se agregó una 'Refacción de la
    tarde' a los 4 tiempos originales).
    """
    DESAYUNO = "DESAYUNO", "Desayuno"
    REFACCION_I = "REFACCION_I", "Refacción I"
    ALMUERZO = "ALMUERZO", "Almuerzo"
    REFACCION_II = "REFACCION_II", "Refacción II"
    CENA = "CENA", "Cena"


class NutritionPlanStatus(models.TextChoices):
    """
    Todo plan generado (manual o por el modelo de ML) debe ser
    revisado y aprobado por el coach antes de llegar al usuario
    (ver panel admin, pantalla 'Nutrición': Dietas por Revisar /
    Dietas Aprobadas y en Seguimiento).
    """
    PENDING_REVIEW = "PENDING_REVIEW", "Pendiente de revisión"
    APPROVED = "APPROVED", "Aprobada y en seguimiento"
    REJECTED = "REJECTED", "Rechazada"


class NutritionPlan(models.Model):
    """
    Plan nutricional diario de un miembro: solo macros (grasas,
    carbohidratos, proteínas) y calorías totales; la app "solo maneja
    macros", sin alimentos típicos locales (E3, reunión 2: No aplica).
    """
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="nutrition_plans")
    status = models.CharField(
        max_length=20, choices=NutritionPlanStatus.choices,
        default=NutritionPlanStatus.PENDING_REVIEW,
    )
    total_calories = models.PositiveSmallIntegerField()
    protein_g = models.PositiveSmallIntegerField()
    carbs_g = models.PositiveSmallIntegerField()
    fats_g = models.PositiveSmallIntegerField()

    # Trazabilidad de cómo se generó el plan (insumo del modelo de ML)
    generated_by_ml = models.BooleanField(default=False)
    ml_prediction = models.ForeignKey(
        "ml_predictions.MLPrediction", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="nutrition_plans",
    )

    reviewed_by = models.ForeignKey(
        "members.User", null=True, blank=True, on_delete=models.SET_NULL,
        limit_choices_to={"is_staff": True},
    )
    is_current = models.BooleanField(
        default=True, help_text="Solo un plan 'actual' por miembro a la vez."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Plan nutricional"
        verbose_name_plural = "Planes nutricionales"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Plan de {self.member} ({self.get_status_display()})"


class MealSuggestion(models.Model):
    """Sugerencias de comida (hasta 3) por tiempo de comida dentro de un plan."""

    plan = models.ForeignKey(NutritionPlan, on_delete=models.CASCADE, related_name="meals")
    meal_time = models.CharField(max_length=20, choices=MealTime.choices)
    carbs_g = models.PositiveSmallIntegerField()
    protein_g = models.PositiveSmallIntegerField()
    fats_g = models.PositiveSmallIntegerField()
    calories = models.PositiveSmallIntegerField()
    suggestion_1 = models.CharField(max_length=255, blank=True)
    suggestion_2 = models.CharField(max_length=255, blank=True)
    suggestion_3 = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Sugerencia de comida"
        verbose_name_plural = "Sugerencias de comida"
        ordering = ["plan", "meal_time"]

    def __str__(self):
        return f"{self.get_meal_time_display()} - {self.plan}"
