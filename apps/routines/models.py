from django.db import models
from apps.members.models import Gender


class RoutineCategory(models.TextChoices):
    """
    Las 7 categorías de rutina confirmadas en reunión 2 (15/abr/2026):
    Pierna-Cuádriceps, Pecho, Brazos y Espalda, Cardio, ABS,
    Pierna-Glúteos y Hombro (agregada en esa misma reunión).
    """
    PIERNA_CUADRICEPS = "PIERNA_CUADRICEPS", "Pierna - Cuádriceps"
    PECHO = "PECHO", "Pecho"
    BRAZOS_ESPALDA = "BRAZOS_ESPALDA", "Brazos y Espalda"
    CARDIO = "CARDIO", "Cardio"
    ABS = "ABS", "ABS"
    PIERNA_GLUTEOS = "PIERNA_GLUTEOS", "Pierna - Glúteos"
    HOMBRO = "HOMBRO", "Hombro"


class Exercise(models.Model):
    """
    Catálogo predefinido de ejercicios/máquinas del gimnasio, con
    nomenclatura propia del gym (p. ej. 'Polea abierta'). Se mapea un
    ícono/foto de referencia una sola vez para no requerir subir
    imágenes repetidamente desde el panel (duda técnica planteada por
    el coach en reunión 2, E2).
    """
    name = models.CharField("Nombre", max_length=150, unique=True)
    category = models.CharField(max_length=20, choices=RoutineCategory.choices)
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
    """
    Rutina semanal por categoría (p. ej. 'Brazos y Espalda'). Las
    rutinas en sí ya están creadas de antemano; lo que se actualiza
    semanalmente son los ejercicios que la integran (RoutineExercise),
    editado por el coach desde el panel de administración.
    """
    category = models.CharField(
        max_length=20, choices=RoutineCategory.choices, unique=True
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
    """
    Ejercicios que integran una rutina en la semana vigente, con su
    orden de ejecución (la app solo muestra el orden, no permite
    marcar completado por ejercicio individual; ver Cuestionario
    Requerimientos, B5).
    """
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
    """
    Calendario semanal de rutinas: qué categoría le toca a cada género
    en cada día de la semana (decisión de negocio confirmada con el
    desarrollador/coach, ver CLAUDE.md). Editable libremente por el
    coach desde el panel admin (p. ej. reasignar un día a Cardio para
    un género en particular).

    Un día de la semana sin fila para un género = no hay rutina
    asignada ese día para ese género (día de descanso), no es un
    error — el enpoint `me/today/` lo maneja como "sin rutina hoy".
    """
    day_of_week = models.PositiveSmallIntegerField("Día", choices=Weekday.choices)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    category = models.CharField(max_length=20, choices=RoutineCategory.choices)

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
