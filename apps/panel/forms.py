from django import forms
from apps.members.models import Member, User


class MemberPersonalDataForm(forms.ModelForm):
    """
    Datos personales + membresía + metas del miembro (mockups admin
    panel 03/04). El correo vive en `user.email` (no en `Member`);
    este form expone un campo "Correo" que la vista sincroniza con el
    `User` asociado. Las medidas físicas (peso, medidas corporales) NO
    van aquí — se editan por separado en `MemberFitnessUpdateForm`,
    cada actualización de esas queda registrada como un nuevo
    `BodyMeasurementLog` (decisión del feedback de la prueba E2E).
    """

    email = forms.EmailField(label="Correo")

    class Meta:
        model = Member
        fields = [
            "first_name", "second_name", "first_last_name", "second_last_name",
            "phone", "age", "start_date", "gender", "height_cm",
            "goal_weight_kg", "fitness_goal", "activity_level",
            "planned_training_days", "planned_nutrition_days",
            "next_payment_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "next_payment_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields["email"].initial = self.instance.user.email
            # La fecha de inicio (fecha en que el miembro se unió al gym)
            # no debe volver a pedirse ni poder cambiarse después de
            # creado el miembro (feedback de la prueba E2E) — Django
            # repuebla el valor desde la instancia automáticamente.
            self.fields["start_date"].disabled = True
        self.fields["planned_training_days"].help_text = (
            "Meta mensual de días de entrenamiento (no semanal)."
        )
        self.fields["planned_nutrition_days"].help_text = (
            "Meta mensual de días de seguimiento nutricional (no semanal)."
        )
        # Reordenar para que "Correo" aparezca junto al resto de datos
        # de contacto en el template.
        self.order_fields(
            ["first_name", "second_name", "first_last_name", "second_last_name",
             "email", "phone", "age", "start_date", "gender", "height_cm",
             "goal_weight_kg", "fitness_goal", "activity_level",
             "planned_training_days", "planned_nutrition_days",
             "next_payment_date"]
        )

    def clean_email(self):
        email = self.cleaned_data["email"]
        existing = User.objects.filter(email=email)
        if self.instance and self.instance.pk and self.instance.user_id:
            existing = existing.exclude(pk=self.instance.user_id)
        if existing.exists():
            raise forms.ValidationError(
                "Ya existe un usuario registrado con este correo."
            )
        return email


class MemberFitnessUpdateForm(forms.ModelForm):
    """
    "Actualización de datos fitness" (peso + medidas corporales +
    cuello). Cada guardado crea un `BodyMeasurementLog` nuevo con la
    fecha del día, además de actualizar el snapshot "actual" en
    `Member` (dispara el recálculo de % grasa/agua vía `Member.save()`).
    """

    class Meta:
        model = Member
        fields = [
            "current_weight_kg", "neck_cm",
            "left_arm_cm", "right_arm_cm", "chest_cm",
            "left_leg_cm", "right_leg_cm", "hip_cm",
            "left_calf_cm", "right_calf_cm", "back_cm", "waist_cm",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # BodyMeasurementLog.weight_kg no es opcional: cada
        # actualización de datos fitness registra un peso.
        self.fields["current_weight_kg"].required = True
