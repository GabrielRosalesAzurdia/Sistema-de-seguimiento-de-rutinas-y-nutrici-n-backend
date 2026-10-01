from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """Usuario único de autenticación: is_staff=True es el coach (panel), is_staff=False es el miembro (app). Login por email."""
    email = models.EmailField(unique=True)
    must_change_password = models.BooleanField(
        "Debe cambiar su contraseña", default=False,
        help_text="True mientras el usuario siga usando la contraseña "
                   "temporal generada por el panel al darlo de alta.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.email


class FitnessGoal(models.TextChoices):
    # * TONIFICAR se trata igual que PERDER_PESO en cálculo de macros/predicción, solo se muestra distinto en la UI.
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
    """Determina la categoría del calendario semanal de rutinas y la variante de la fórmula U.S. Navy de % de grasa."""
    HOMBRE = "HOMBRE", "Hombre"
    MUJER = "MUJER", "Mujer"


class Member(models.Model):
    """Miembro del gimnasio. Datos personales completos solo en el panel; la app expone un perfil reducido sin correo/teléfono/peso editables."""
    # * El peso/medidas los ingresa únicamente el coach desde el panel; la app nunca expone esos campos como editables.

    # Todo miembro tiene cuenta de login creada junto con él (contraseña autogenerada); el correo vive en `user.email` (ver property `email`).
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        help_text="Cuenta de autenticación ligada a este miembro (login en la app).",
    )

    # --- Datos personales (solo visibles/editables en el panel admin) ---
    first_name = models.CharField("Primer nombre", max_length=100)
    second_name = models.CharField("Segundo nombre", max_length=100, blank=True)
    first_last_name = models.CharField("Primer apellido", max_length=100)
    second_last_name = models.CharField("Segundo apellido", max_length=100, blank=True)
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
    left_arm_cm = models.DecimalField(
        "Brazo izquierdo (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    right_arm_cm = models.DecimalField(
        "Brazo derecho (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    left_leg_cm = models.DecimalField(
        "Pierna izquierda (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    right_leg_cm = models.DecimalField(
        "Pierna derecha (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    left_calf_cm = models.DecimalField(
        "Pantorrilla izquierda (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    right_calf_cm = models.DecimalField(
        "Pantorrilla derecha (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    hip_cm = models.DecimalField(
        "Cadera (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    back_cm = models.DecimalField(
        "Espalda (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    chest_cm = models.DecimalField(
        "Pecho (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    waist_cm = models.DecimalField(
        "Cintura (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
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
    last_payment_date = models.DateField(
        "Último pago registrado", null=True, blank=True,
        help_text="Se actualiza automáticamente al marcar 'Pagado'. Si es "
                   "nulo, el miembro nunca ha sido marcado como pagado.",
    )
    is_paid = models.BooleanField("Pagado", default=False)
    is_active = models.BooleanField("Activo", default=True)

    # * Metas de constancia (VD1/VD2) definidas por el coach; si el miembro las supera, el % puede pasar de 100%, no se limita.
    planned_training_days = models.PositiveSmallIntegerField(
        "Días planificados de rutina",
        help_text="Total de sesiones de entrenamiento que el coach planifica "
        "para el miembro durante el período de medición (actualmente un mes), "
        "no un valor semanal.",
    )
    planned_nutrition_days = models.PositiveSmallIntegerField(
        "Días planificados de dieta",
        help_text="Total de días de seguimiento nutricional que el coach "
        "planifica para el miembro durante el período de medición (actualmente "
        "un mes), no un valor semanal.",
    )

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

        # Solo sobreescribe si hay medidas suficientes para calcular; si faltan, conserva el valor ya guardado.
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
    def email(self):
        """Correo único del miembro — vive en `user.email` (login),
        no hay un campo `Member.email` separado que pueda divergir."""
        return self.user.email

    @property
    def payment_status_display(self):
        """Próximo pago formateado (YYYY-MM-DD), o "PENDIENTE DE PAGO" si nunca pagó o la fecha ya llegó/pasó. Siempre devuelve string."""
        today = timezone.localdate()
        if (
            self.last_payment_date is None
            or self.next_payment_date is None
            or self.next_payment_date <= today
        ):
            return "PENDIENTE DE PAGO"
        return self.next_payment_date.strftime("%Y-%m-%d")

    @property
    def imc(self):
        """Índice de Masa Corporal, usado como insumo para los modelos de ML."""
        if not self.current_weight_kg or not self.height_cm:
            return None
        height_m = float(self.height_cm) / 100
        return round(float(self.current_weight_kg) / (height_m ** 2), 2)
