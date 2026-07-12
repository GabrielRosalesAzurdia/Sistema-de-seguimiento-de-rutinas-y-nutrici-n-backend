from rest_framework.routers import DefaultRouter
from .views import RoutineViewSet, ExerciseViewSet, RoutineExerciseViewSet

router = DefaultRouter()
router.register("exercises", ExerciseViewSet, basename="exercise")
router.register("routine-exercises", RoutineExerciseViewSet, basename="routine-exercise")
router.register("", RoutineViewSet, basename="routine")

urlpatterns = router.urls
