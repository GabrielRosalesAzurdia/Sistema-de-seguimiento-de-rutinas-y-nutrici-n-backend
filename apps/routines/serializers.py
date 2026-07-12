from rest_framework import serializers
from .models import Routine, RoutineExercise, Exercise


class ExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercise
        fields = ["id", "name", "category", "icon", "reference_photo", "is_active"]


class RoutineExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)
    exercise_id = serializers.PrimaryKeyRelatedField(
        queryset=Exercise.objects.all(), source="exercise", write_only=True
    )

    class Meta:
        model = RoutineExercise
        fields = ["id", "order", "exercise", "exercise_id"]


class RoutineSerializer(serializers.ModelSerializer):
    """Rutina con su lista de ejercicios vigentes, en orden. Usada tanto
    en el listado 'Rutinas' de la app como en el detalle de una rutina."""

    exercises = RoutineExerciseSerializer(many=True, read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Routine
        fields = [
            "id",
            "category",
            "category_display",
            "estimated_duration_min_low",
            "estimated_duration_min_high",
            "estimated_calories",
            "exercises",
        ]
