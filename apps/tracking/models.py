from django.db import models
from apps.members.models import Member
from apps.routines.models import Routine, Exercise


class WorkoutSessionLog(models.Model):
    """Registro de una sesión de entrenamiento completada: peso
    inicial/final y repeticiones por ejercicio, más tiempo total.
    Fuente principal de VD1 (% sesiones completadas / planificadas)."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="workout_logs")
    routine = models.ForeignKey(Routine, on_delete=models.PROTECT, related_name="logs")
    duration_minutes = models.PositiveSmallIntegerField("Tiempo (minutos)")
    calories_burned = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Calorías quemadas según rutina y tiempo.",
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de rutina completada"
        verbose_name_plural = "Registros de rutinas completadas"
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.member} - {self.routine} ({self.completed_at:%Y-%m-%d})"


class WorkoutExerciseEntry(models.Model):
    """Detalle por ejercicio dentro de una sesión: peso inicial, peso
    final y repeticiones realizadas."""

    session = models.ForeignKey(
        WorkoutSessionLog, on_delete=models.CASCADE, related_name="exercise_entries"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT)
    initial_weight_lb = models.DecimalField(max_digits=5, decimal_places=1)
    final_weight_lb = models.DecimalField(max_digits=5, decimal_places=1)
    reps_completed = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "Detalle de ejercicio registrado"
        verbose_name_plural = "Detalles de ejercicios registrados"

    def __str__(self):
        return f"{self.exercise.name} - {self.session}"


class NutritionCheckStatus(models.TextChoices):
    """Semáforo diario único de nutrición: un solo registro por día,
    tres opciones, mostrado en el dashboard."""
    HECHO = "HECHO", "Hecho"
    PARCIALMENTE = "PARCIALMENTE", "Parcialmente"
    SE_ME_FUE = "SE_ME_FUE", "Se me fue"


class DailyNutritionLog(models.Model):
    """Registro diario de constancia nutricional: cualquiera de las 3
    respuestas del semáforo cuenta como "día con registro" para VD2."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="nutrition_logs")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=NutritionCheckStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro nutricional diario"
        verbose_name_plural = "Registros nutricionales diarios"
        unique_together = ["member", "date"]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.member} - {self.date} - {self.get_status_display()}"


class BodyMeasurementLog(models.Model):
    """Historial mensual de peso y medidas corporales, ingresado
    exclusivamente por el coach desde el panel admin."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="measurement_logs")
    recorded_by = models.ForeignKey(
        "members.User", on_delete=models.SET_NULL, null=True,
        limit_choices_to={"is_staff": True},
    )
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    body_fat_percentage = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    body_water_percentage = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        verbose_name = "Registro de medidas corporales"
        verbose_name_plural = "Registros de medidas corporales"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.member} - {self.date} - {self.weight_kg}kg"
