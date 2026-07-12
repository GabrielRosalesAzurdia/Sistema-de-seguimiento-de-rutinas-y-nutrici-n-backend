from rest_framework import serializers
from .models import NutritionPlan, MealSuggestion


class MealSuggestionSerializer(serializers.ModelSerializer):
    meal_time_display = serializers.CharField(source="get_meal_time_display", read_only=True)

    class Meta:
        model = MealSuggestion
        fields = [
            "id", "meal_time", "meal_time_display", "carbs_g", "protein_g",
            "fats_g", "calories", "suggestion_1", "suggestion_2", "suggestion_3",
        ]


class NutritionPlanSerializer(serializers.ModelSerializer):
    meals = MealSuggestionSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = NutritionPlan
        fields = [
            "id", "member", "status", "status_display", "total_calories",
            "protein_g", "carbs_g", "fats_g", "generated_by_ml",
            "is_current", "created_at", "reviewed_at", "meals",
        ]
        read_only_fields = ["created_at", "reviewed_at"]


class NutritionPlanReviewSerializer(serializers.ModelSerializer):
    """Usado por el coach para aprobar/rechazar un plan pendiente."""

    class Meta:
        model = NutritionPlan
        fields = ["status"]
