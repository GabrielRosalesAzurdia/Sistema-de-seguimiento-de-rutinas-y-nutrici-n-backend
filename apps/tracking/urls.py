from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    WorkoutSessionLogViewSet, MyWorkoutHistoryViewSet, MyExerciseProgressView,
    DailyNutritionLogViewSet, BodyMeasurementLogViewSet, StudyExportView,
    StudyDailyExportView, StudyKeyExportView,
    MyTrackingSummaryView, MyWeightHistoryView,
)

router = DefaultRouter()
router.register("workout-logs", WorkoutSessionLogViewSet, basename="workout-log")
router.register("me/workout-history", MyWorkoutHistoryViewSet, basename="my-workout-history")
router.register("nutrition-logs", DailyNutritionLogViewSet, basename="nutrition-log")
router.register("measurement-logs", BodyMeasurementLogViewSet, basename="measurement-log")

urlpatterns = [
    path("study-export/", StudyExportView.as_view(), name="study-export"),
    path("study-export-daily/", StudyDailyExportView.as_view(), name="study-export-daily"),
    path("study-export-key/", StudyKeyExportView.as_view(), name="study-export-key"),
    path("me/summary/", MyTrackingSummaryView.as_view(), name="my-tracking-summary"),
    path("me/weight-history/", MyWeightHistoryView.as_view(), name="my-weight-history"),
    path(
        "me/exercise-progress/<int:exercise_id>/",
        MyExerciseProgressView.as_view(),
        name="my-exercise-progress",
    ),
] + router.urls
