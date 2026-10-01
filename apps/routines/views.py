from django.utils import timezone
from rest_framework import viewsets, permissions, views
from rest_framework.response import Response
from common.permissions import IsCoachOrReadOnly
from .models import Routine, Exercise, RoutineExercise, ScheduledRoutineDay
from .serializers import RoutineSerializer, ExerciseSerializer, RoutineExerciseSerializer


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


class TodayRoutineView(views.APIView):
    """Rutina de hoy del miembro según el calendario semanal por género. Devuelve 204 si no hay género asignado o es día de descanso."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        member = getattr(request.user, "member_profile", None)
        if not member or not member.gender:
            return Response(status=204)

        today = timezone.localdate()
        scheduled = ScheduledRoutineDay.objects.filter(
            day_of_week=today.weekday(), gender=member.gender
        ).first()
        if not scheduled:
            return Response(status=204)

        routine = (
            Routine.objects.filter(category=scheduled.category)
            .prefetch_related("exercises__exercise")
            .first()
        )
        if not routine:
            return Response(status=204)

        return Response(RoutineSerializer(routine).data)
