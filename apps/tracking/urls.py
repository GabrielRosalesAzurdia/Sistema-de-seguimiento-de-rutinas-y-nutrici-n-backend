from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    WorkoutSessionLogViewSet, DailyNutritionLogViewSet,
    BodyMeasurementLogViewSet, StudyExportView,
)

router = DefaultRouter()
router.register("workout-logs", WorkoutSessionLogViewSet, basename="workout-log")
router.register("nutrition-logs", DailyNutritionLogViewSet, basename="nutrition-log")
router.register("measurement-logs", BodyMeasurementLogViewSet, basename="measurement-log")

urlpatterns = [
    path("study-export/", StudyExportView.as_view(), name="study-export"),
] + router.urls
