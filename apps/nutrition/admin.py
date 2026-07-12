from django.contrib import admin
from .models import NutritionPlan, MealSuggestion


class MealSuggestionInline(admin.TabularInline):
    model = MealSuggestion
    extra = 0


@admin.register(NutritionPlan)
class NutritionPlanAdmin(admin.ModelAdmin):
    list_display = ["member", "status", "total_calories", "is_current", "created_at"]
    list_filter = ["status", "is_current", "generated_by_ml"]
    inlines = [MealSuggestionInline]
