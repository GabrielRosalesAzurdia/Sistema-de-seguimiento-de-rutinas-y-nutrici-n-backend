from django import forms
from apps.members.models import Member


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
        # Reordenar para que "Correo" aparezca junto al resto de datos
        # de contacto en el template.
        self.order_fields(
            ["first_name", "second_name", "first_last_name", "second_last_name",
             "email", "phone", "age", "start_date", "gender", "height_cm",
             "goal_weight_kg", "fitness_goal", "activity_level",
             "planned_training_days", "planned_nutrition_days",
             "next_payment_date"]
        )


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
