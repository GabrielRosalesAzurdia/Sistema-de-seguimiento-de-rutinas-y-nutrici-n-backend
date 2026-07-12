from rest_framework import serializers
from .models import Member


class MemberAdminSerializer(serializers.ModelSerializer):
    """Serializer completo para el panel de administración (coach)."""

    full_name = serializers.ReadOnlyField()
    imc = serializers.ReadOnlyField()

    class Meta:
        model = Member
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class MemberAppSerializer(serializers.ModelSerializer):
    """
    Serializer de solo lectura para la app móvil (pantalla Perfil).

    IMPORTANTE: no incluye email/telefono (solo panel admin, ver
    Cuestionario Requerimientos 2, nota post reunión) y el peso /
    medidas corporales son de SOLO LECTURA: el usuario no puede
    editarlas desde la app, únicamente el coach vía panel admin.
    """

    full_name = serializers.ReadOnlyField()
    imc = serializers.ReadOnlyField()

    class Meta:
        model = Member
        fields = [
            "id",
            "full_name",
            "age",
            "height_cm",
            "current_weight_kg",
            "goal_weight_kg",
            "body_fat_percentage",
            "body_water_percentage",
            "left_arm_cm",
            "right_arm_cm",
            "left_leg_cm",
            "right_leg_cm",
            "left_calf_cm",
            "right_calf_cm",
            "hip_cm",
            "back_cm",
            "chest_cm",
            "waist_cm",
            "fitness_goal",
            "activity_level",
            "imc",
        ]
        read_only_fields = fields


class MemberAppEditableSerializer(serializers.ModelSerializer):
    """
    Subconjunto de campos que el usuario SÍ puede editar desde la
    app (pantalla 'Editar Perfil'): nombre, edad, altura y meta/nivel
    de actividad. Peso y medidas corporales quedan explícitamente
    fuera por decisión de negocio.
    """

    class Meta:
        model = Member
        fields = [
            "first_name",
            "second_name",
            "first_last_name",
            "second_last_name",
            "age",
            "height_cm",
            "fitness_goal",
            "activity_level",
        ]
