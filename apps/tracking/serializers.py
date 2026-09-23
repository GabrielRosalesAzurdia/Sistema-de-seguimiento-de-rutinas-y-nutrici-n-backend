from rest_framework import serializers
from .models import (
    WorkoutSessionLog, WorkoutExerciseEntry, DailyNutritionLog, BodyMeasurementLog,
)


class WorkoutExerciseEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutExerciseEntry
        fields = ["id", "exercise", "initial_weight_lb", "final_weight_lb", "reps_completed"]


class WorkoutExerciseEntryHistorySerializer(serializers.ModelSerializer):
    """Igual a WorkoutExerciseEntrySerializer pero con el nombre del
    ejercicio anidado, para que la pantalla de Historial no tenga que
    resolverlo aparte a partir del id."""

    exercise_name = serializers.CharField(source="exercise.name", read_only=True)

    class Meta:
        model = WorkoutExerciseEntry
        fields = ["id", "exercise", "exercise_name", "initial_weight_lb", "final_weight_lb", "reps_completed"]


class WorkoutSessionHistorySerializer(serializers.ModelSerializer):
    """Solo lectura, para la pantalla de Historial del usuario: agrega
    la categoría de la rutina (con su etiqueta legible) y el nombre de
    cada ejercicio, que WorkoutSessionLogSerializer no trae porque está
    pensado para el registro (POST), no para mostrar el historial."""

    exercise_entries = WorkoutExerciseEntryHistorySerializer(many=True, read_only=True)
    routine_category = serializers.CharField(source="routine.category", read_only=True)
    routine_category_display = serializers.CharField(source="routine.get_category_display", read_only=True)

    class Meta:
        model = WorkoutSessionLog
        fields = [
            "id", "routine", "routine_category", "routine_category_display",
            "duration_minutes", "calories_burned", "completed_at", "exercise_entries",
        ]


class WorkoutSessionLogSerializer(serializers.ModelSerializer):
    exercise_entries = WorkoutExerciseEntrySerializer(many=True)

    class Meta:
        model = WorkoutSessionLog
        fields = [
            "id", "member", "routine", "duration_minutes",
            "calories_burned", "completed_at", "exercise_entries",
        ]
        read_only_fields = ["member", "completed_at"]

    def create(self, validated_data):
        entries_data = validated_data.pop("exercise_entries")
        member = self.context["request"].user.member_profile
        # calories_burned se deriva siempre de la rutina (el cliente
        # móvil no lo envía, y aunque lo hiciera, la fuente de verdad
        # es la calorías estimadas de la rutina completada).
        validated_data["calories_burned"] = validated_data["routine"].estimated_calories
        session = WorkoutSessionLog.objects.create(member=member, **validated_data)
        for entry in entries_data:
            WorkoutExerciseEntry.objects.create(session=session, **entry)
        return session


class DailyNutritionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyNutritionLog
        fields = ["id", "member", "date", "status", "created_at"]
        read_only_fields = ["member", "created_at"]

    def create(self, validated_data):
        member = self.context["request"].user.member_profile
        validated_data["member"] = member
        # Un registro por día: si ya existe, se actualiza (evita duplicados
        # si el usuario cambia de opinión el mismo día).
        obj, _ = DailyNutritionLog.objects.update_or_create(
            member=member, date=validated_data["date"],
            defaults={"status": validated_data["status"]},
        )
        return obj


class BodyMeasurementLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BodyMeasurementLog
        fields = "__all__"
        read_only_fields = ["recorded_by"]
