from rest_framework import viewsets, permissions
from .models import Routine, Exercise, RoutineExercise
from .serializers import RoutineSerializer, ExerciseSerializer, RoutineExerciseSerializer


class IsCoachOrReadOnly(permissions.BasePermission):
    """Los miembros (app) solo leen; el coach (panel) puede editar."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return bool(request.user and request.user.is_staff)


class RoutineViewSet(viewsets.ModelViewSet):
    queryset = Routine.objects.all().prefetch_related("exercises__exercise")
    serializer_class = RoutineSerializer
    permission_classes = [IsCoachOrReadOnly]


class ExerciseViewSet(viewsets.ModelViewSet):
    queryset = Exercise.objects.filter(is_active=True)
    serializer_class = ExerciseSerializer
    permission_classes = [IsCoachOrReadOnly]


class RoutineExerciseViewSet(viewsets.ModelViewSet):
    """Usado por el panel admin para editar semanalmente qué ejercicios
    integran cada rutina (pantalla 'Editar ejercicios')."""

    queryset = RoutineExercise.objects.all()
    serializer_class = RoutineExerciseSerializer
    permission_classes = [IsCoachOrReadOnly]
