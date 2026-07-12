from rest_framework import serializers
from .models import (
    WorkoutSessionLog, WorkoutExerciseEntry, DailyNutritionLog, BodyMeasurementLog,
)


class WorkoutExerciseEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutExerciseEntry
        fields = ["id", "exercise", "initial_weight_lb", "final_weight_lb", "reps_completed"]


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
