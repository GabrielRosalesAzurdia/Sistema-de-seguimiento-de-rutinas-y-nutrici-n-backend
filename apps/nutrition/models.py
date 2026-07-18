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
    SUPERSEDED = "SUPERSEDED", "Reemplazada"


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

    # Snapshot de lo que la heurística/ML sugirió originalmente, previo a
    # cualquier edición del coach — permite comparar sugerido vs. aprobado
    # como insumo de reentrenamiento futuro (no hay reentrenamiento en vivo).
    ml_suggested_calories = models.PositiveSmallIntegerField(null=True, blank=True)
    ml_suggested_protein_g = models.PositiveSmallIntegerField(null=True, blank=True)
    ml_suggested_carbs_g = models.PositiveSmallIntegerField(null=True, blank=True)
    ml_suggested_fats_g = models.PositiveSmallIntegerField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        "members.User", null=True, blank=True, on_delete=models.SET_NULL,
        limit_choices_to={"is_staff": True},
    )
    is_current = models.BooleanField(
        default=False,
        help_text="Solo un plan 'actual' por miembro a la vez — se activa "
                   "al aprobar (ver NutritionPlanDetailView).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Plan nutricional"
        verbose_name_plural = "Planes nutricionales"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Plan de {self.member} ({self.get_status_display()})"

    def recompute_totals_from_meals(self):
        """Resincroniza los totales del plan a partir de sus 5 comidas —
        se llama tras guardar el formset de revisión, para que una
        edición de macros por comida se refleje en el total del plan.
        No hace save(); el caller decide cuándo persistir."""
        totals = self.meals.aggregate(
            calories=models.Sum("calories"),
            protein_g=models.Sum("protein_g"),
            carbs_g=models.Sum("carbs_g"),
            fats_g=models.Sum("fats_g"),
        )
        self.total_calories = totals["calories"] or 0
        self.protein_g = totals["protein_g"] or 0
        self.carbs_g = totals["carbs_g"] or 0
        self.fats_g = totals["fats_g"] or 0


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
        # Orden de consumo (Desayuno, Refacción I, Almuerzo, Refacción
        # II, Cena), no orden alfabético del valor guardado — "meal_time"
        # a secas ordenaba ALMUERZO/CENA/DESAYUNO/... (bug reportado en
        # la prueba E2E).
        ordering = [
            "plan",
            models.Case(
                *[
                    models.When(meal_time=value, then=models.Value(index))
                    for index, (value, _label) in enumerate(MealTime.choices)
                ],
                output_field=models.IntegerField(),
            ),
        ]

    def __str__(self):
        return f"{self.get_meal_time_display()} - {self.plan}"
