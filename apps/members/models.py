from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """
    Usuario de autenticación único para todo el sistema.

    - is_staff=True  -> coach / dueño del gimnasio, accede al panel Django
      admin y a los endpoints administrativos del API (Django REST
      Framework).
    - is_staff=False -> miembro del gimnasio, solo accede a la app móvil
      Flutter a través de su Member vinculado (ver Member.user).

    Se usa email como identificador de login en ambos casos.
    """
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.email


class FitnessGoal(models.TextChoices):
    """
    Meta fitness del usuario. 'Tonificar' se trata internamente como
    'Perder peso' según decisión de reunión 2 (15/abr/2026).
    """
    GANAR_PESO = "GANAR_PESO", "Ganar peso"
    PERDER_PESO = "PERDER_PESO", "Perder peso"
    MANTENER_PESO = "MANTENER_PESO", "Mantener peso"
    TONIFICAR = "TONIFICAR", "Tonificar"


class ActivityLevel(models.TextChoices):
    SEDENTARIO = "SEDENTARIO", "Sedentario"
    MODERADO = "MODERADO", "Moderado"
    ACTIVO = "ACTIVO", "Activo"
    MUY_ACTIVO = "MUY_ACTIVO", "Muy activo"


class Gender(models.TextChoices):
    """
    Alcance limitado a lo que requiere el calendario semanal de
    rutinas (cada día de la semana asigna una categoría distinta
    según género, ver ScheduledRoutineDay en apps.routines) y la
    fórmula U.S. Navy de % de grasa corporal, que usa una variante de
    cálculo distinta por género.
    """
    HOMBRE = "HOMBRE", "Hombre"
    MUJER = "MUJER", "Mujer"


class Member(models.Model):
    """
    Usuario del gimnasio (miembro). Datos personales completos son
    visibles solo en el panel de administración; la app móvil solo
    expone al usuario su propio perfil sin correo/teléfono editables
    y SIN campo de peso editable (el peso lo ingresa únicamente el
    coach, ver decisión de reunión: "el peso será ingresado solo por
    el coach no por los usuarios para evitar datos erróneos").
    """

    # --- Cuenta / autenticación de la app ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        null=True,
        blank=True,
        help_text="Cuenta de autenticación ligada a este miembro (login en la app).",
    )

    # --- Datos personales (solo visibles/editables en el panel admin) ---
    first_name = models.CharField("Primer nombre", max_length=100)
    second_name = models.CharField("Segundo nombre", max_length=100, blank=True)
    first_last_name = models.CharField("Primer apellido", max_length=100)
    second_last_name = models.CharField("Segundo apellido", max_length=100, blank=True)
    email = models.EmailField("Correo", blank=True)
    phone = models.CharField("Teléfono", max_length=20, blank=True)
    age = models.PositiveSmallIntegerField("Edad")
    height_cm = models.DecimalField("Altura (cm)", max_digits=5, decimal_places=1)
    gender = models.CharField(
        "Género", max_length=10, choices=Gender.choices, null=True, blank=True,
        help_text="Determina la rutina asignada del calendario semanal y la "
                   "fórmula de % de grasa corporal usada.",
    )

    # --- Datos físicos (peso y medidas: SOLO el coach los edita) ---
    current_weight_kg = models.DecimalField(
        "Peso actual (kg)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    goal_weight_kg = models.DecimalField(
        "Peso meta (kg)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    body_fat_percentage = models.DecimalField(
        "% Grasa corporal", max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="Calculado por el sistema a partir de medidas registradas por el coach.",
    )
    body_water_percentage = models.DecimalField(
        "% Agua corporal", max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="Calculado por el sistema a partir de medidas registradas por el coach.",
    )
    left_arm_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    right_arm_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    left_leg_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    right_leg_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    left_calf_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    right_calf_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    hip_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    back_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    chest_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    waist_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    neck_cm = models.DecimalField(
        "Cuello (cm)", max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Requerido para calcular % de grasa corporal (U.S. Navy Method).",
    )

    # --- Objetivo y nivel de actividad ---
    fitness_goal = models.CharField(
        max_length=20, choices=FitnessGoal.choices, default=FitnessGoal.MANTENER_PESO
    )
    activity_level = models.CharField(
        max_length=20, choices=ActivityLevel.choices, default=ActivityLevel.MODERADO
    )

    # --- Membresía / pagos (solo panel admin) ---
    start_date = models.DateField("Fecha de inicio", default=timezone.now)
    next_payment_date = models.DateField("Siguiente pago", null=True, blank=True)
    is_paid = models.BooleanField("Pagado", default=False)
    is_active = models.BooleanField("Activo", default=True)

    # --- Consentimiento informado (viabilidad operacional del estudio) ---
    informed_consent_signed = models.BooleanField(
        "Consentimiento informado firmado", default=False
    )
    participates_in_study = models.BooleanField(
        "Participa en el estudio (oct-nov 2026)", default=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Miembro"
        verbose_name_plural = "Miembros"
        ordering = ["first_name", "first_last_name"]

    def __str__(self):
        return f"{self.first_name} {self.first_last_name}"

    def save(self, *args, **kwargs):
        from .services import calculate_body_composition

        # Solo se sobreescribe si hay suficientes medidas para calcular
        # (cintura/cuello/altura, +cadera en mujeres) — si faltan
        # (p. ej. neck_cm todavía no medido), se preserva el valor que
        # ya estuviera guardado en vez de borrarlo con None.
        body_fat, body_water = calculate_body_composition(self)
        if body_fat is not None:
            self.body_fat_percentage = body_fat
        if body_water is not None:
            self.body_water_percentage = body_water
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        parts = [self.first_name, self.second_name, self.first_last_name, self.second_last_name]
        return " ".join(p for p in parts if p)

    @property
    def imc(self):
        """Índice de Masa Corporal, usado como insumo para los modelos de ML."""
        if not self.current_weight_kg or not self.height_cm:
            return None
        height_m = float(self.height_cm) / 100
        return round(float(self.current_weight_kg) / (height_m ** 2), 2)
