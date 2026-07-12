from django.contrib import admin
from .models import WorkoutSessionLog, WorkoutExerciseEntry, DailyNutritionLog, BodyMeasurementLog


class WorkoutExerciseEntryInline(admin.TabularInline):
    model = WorkoutExerciseEntry
    extra = 0


@admin.register(WorkoutSessionLog)
class WorkoutSessionLogAdmin(admin.ModelAdmin):
    list_display = ["member", "routine", "duration_minutes", "calories_burned", "completed_at"]
    list_filter = ["routine"]
    inlines = [WorkoutExerciseEntryInline]


@admin.register(DailyNutritionLog)
class DailyNutritionLogAdmin(admin.ModelAdmin):
    list_display = ["member", "date", "status"]
    list_filter = ["status", "date"]


@admin.register(BodyMeasurementLog)
class BodyMeasurementLogAdmin(admin.ModelAdmin):
    list_display = ["member", "date", "weight_kg", "body_fat_percentage", "body_water_percentage"]
