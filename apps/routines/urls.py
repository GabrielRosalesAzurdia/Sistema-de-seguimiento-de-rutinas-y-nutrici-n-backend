from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RoutineViewSet, ExerciseViewSet, RoutineExerciseViewSet, TodayRoutineView

router = DefaultRouter()
router.register("exercises", ExerciseViewSet, basename="exercise")
router.register("routine-exercises", RoutineExerciseViewSet, basename="routine-exercise")
router.register("", RoutineViewSet, basename="routine")

urlpatterns = [
    path("me/today/", TodayRoutineView.as_view(), name="routine-today"),
] + router.urls
