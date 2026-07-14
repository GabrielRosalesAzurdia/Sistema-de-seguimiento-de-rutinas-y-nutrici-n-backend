from django.contrib import admin
from .models import Routine, Exercise, RoutineExercise, ScheduledRoutineDay


class RoutineExerciseInline(admin.TabularInline):
    model = RoutineExercise
    extra = 1


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ["category", "estimated_calories", "updated_at"]
    inlines = [RoutineExerciseInline]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


@admin.register(ScheduledRoutineDay)
class ScheduledRoutineDayAdmin(admin.ModelAdmin):
    list_display = ["day_of_week", "gender", "category"]
    list_filter = ["gender", "day_of_week"]
    ordering = ["day_of_week", "gender"]
