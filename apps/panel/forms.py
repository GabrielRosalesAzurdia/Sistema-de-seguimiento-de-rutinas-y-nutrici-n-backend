from django import forms
from apps.members.models import Member


class MemberForm(forms.ModelForm):
    """
    Formulario compartido para "Agregar Miembro" y "Editar Miembro"
    (mismos campos en ambos mockups: docs/mockups/admin_panel/03 y 04).

    Nota: el mockup no incluye `height_cm` (requerido por el modelo),
    ni `gender`/`neck_cm`/`activity_level` — estos tres últimos se
    agregaron después del mockup (calendario semanal por género y
    fórmula Navy Method de % grasa corporal), así que se incluyen
    aquí aunque no aparezcan en la captura original.
    """

    class Meta:
        model = Member
        fields = [
            # Datos personales
            "first_name", "second_name", "first_last_name", "second_last_name",
            "phone", "email", "age", "start_date",
            # Datos físicos
            "gender", "height_cm", "neck_cm", "current_weight_kg",
            "left_arm_cm", "right_arm_cm", "chest_cm",
            "left_leg_cm", "right_leg_cm", "hip_cm",
            "left_calf_cm", "right_calf_cm", "back_cm", "waist_cm",
            "fitness_goal", "activity_level",
            "next_payment_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "next_payment_date": forms.DateInput(attrs={"type": "date"}),
        }
