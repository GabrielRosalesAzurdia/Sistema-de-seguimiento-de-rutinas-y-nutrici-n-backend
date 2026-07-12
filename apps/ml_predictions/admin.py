from django.contrib import admin
from .models import MLPrediction


@admin.register(MLPrediction)
class MLPredictionAdmin(admin.ModelAdmin):
    list_display = ["member", "model_type", "predicted_days_to_goal", "created_at"]
    list_filter = ["model_type"]
