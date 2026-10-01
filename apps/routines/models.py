from django.db import models
from apps.members.models import Gender


class RoutineCategory(models.TextChoices):
    """* Las 9 categorías de rutina. CARDIO se muestra como "Workout". Las últimas 2 son exclusivas del calendario de mujeres."""
    PIERNA_CUADRICEPS = "PIERNA_CUADRICEPS", "Pierna - Cuádriceps"
    PECHO = "PECHO", "Pecho"
    BRAZOS_ESPALDA = "BRAZOS_ESPALDA", "Brazos y Espalda"
    CARDIO = "CARDIO", "Workout"
    ABS = "ABS", "ABS"
    PIERNA_GLUTEOS = "PIERNA_GLUTEOS", "Pierna - Glúteos"
    HOMBRO = "HOMBRO", "Hombro"
    PIERNA_CUADRICEPS_CIRCUITO = "PIERNA_CUADRICEPS_CIRCUITO", "Pierna Cuádriceps + Circuito"
    PECHO_HOMBRO_TRICEPS = "PECHO_HOMBRO_TRICEPS", "Pecho, Hombro y Tríceps"


class Exercise(models.Model):
    """Catálogo predefinido de ejercicios/máquinas del gimnasio, con ícono/foto de referencia propios."""
    name = models.CharField("Nombre", max_length=150, unique=True)
    category = models.CharField(max_length=30, choices=RoutineCategory.choices)
    icon = models.ImageField(upload_to="exercise_icons/", null=True, blank=True)
    reference_photo = models.ImageField(upload_to="exercise_photos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Ejercicio"
        verbose_name_plural = "Ejercicios (catálogo predefinido)"
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Routine(models.Model):
    """Rutina por categoría; el coach solo actualiza los ejercicios que la integran (RoutineExercise), no la rutina en sí."""
    category = models.CharField(
        max_length=30, choices=RoutineCategory.choices, unique=True
    )
    estimated_duration_min_low = models.PositiveSmallIntegerField(default=60)
    estimated_duration_min_high = models.PositiveSmallIntegerField(default=90)
    estimated_calories = models.PositiveSmallIntegerField(
        default=400, help_text="Calorías aproximadas quemadas al completar la rutina."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rutina"
        verbose_name_plural = "Rutinas"

    def __str__(self):
        return self.get_category_display()


class RoutineExercise(models.Model):
    """Ejercicio que integra una rutina, con su orden de ejecución. La app solo muestra el orden, no marca completado por ejercicio."""
    routine = models.ForeignKey(Routine, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "Ejercicio de rutina"
        verbose_name_plural = "Ejercicios de rutina"
        ordering = ["routine", "order"]
        unique_together = ["routine", "exercise"]

    def __str__(self):
        return f"{self.routine} - {self.order}. {self.exercise.name}"


class Weekday(models.IntegerChoices):
    LUNES = 0, "Lunes"
    MARTES = 1, "Martes"
    MIERCOLES = 2, "Miércoles"
    JUEVES = 3, "Jueves"
    VIERNES = 4, "Viernes"
    SABADO = 5, "Sábado"
    DOMINGO = 6, "Domingo"


class ScheduledRoutineDay(models.Model):
    """Calendario semanal: categoría de rutina asignada a cada género por día. Sin fila = día de descanso, no un error."""
    day_of_week = models.PositiveSmallIntegerField("Día", choices=Weekday.choices)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    category = models.CharField(max_length=30, choices=RoutineCategory.choices)

    class Meta:
        verbose_name = "Día de calendario semanal"
        verbose_name_plural = "Calendario semanal de rutinas"
        unique_together = ["day_of_week", "gender"]
        ordering = ["day_of_week", "gender"]

    def __str__(self):
        return (
            f"{self.get_day_of_week_display()} - {self.get_gender_display()} - "
            f"{self.get_category_display()}"
        )
