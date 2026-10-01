from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import Member


class ChangePasswordSerializer(serializers.Serializer):
    """Usado por ChangePasswordView (flujo obligatorio de primer login
    con contraseña temporal, y 'Cambiar contraseña' desde Perfil)."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value

    def validate_new_password(self, value):
        validate_password(value, user=self.context["request"].user)
        return value


class MemberAdminSerializer(serializers.ModelSerializer):
    """Serializer completo para el panel de administración (coach)."""

    full_name = serializers.ReadOnlyField()
    imc = serializers.ReadOnlyField()

    class Meta:
        model = Member
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class MemberAppSerializer(serializers.ModelSerializer):
    """Solo lectura para la app (pantalla Perfil). Sin email/teléfono; peso y medidas no son editables desde la app."""

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
    """Campos editables desde 'Editar Perfil' en la app: nombre, edad, altura y meta/nivel de actividad. Sin peso ni medidas."""

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
