from django.http import Http404
from django.utils import timezone
from rest_framework import viewsets, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsCoach
from .models import NutritionPlan
from .serializers import NutritionPlanSerializer, NutritionPlanReviewSerializer


class MyCurrentPlanView(generics.RetrieveAPIView):
    """Pantalla 'Nutrición' de la app: plan vigente y APROBADO del miembro."""

    serializer_class = NutritionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        member = self.request.user.member_profile
        try:
            return NutritionPlan.objects.filter(
                member=member, is_current=True, status="APPROVED"
            ).latest("created_at")
        except NutritionPlan.DoesNotExist:
            # Antes esto se propagaba como 500 sin manejar. El mockup y
            # el mobile (NutritionService.getMyCurrentPlan) ya esperan
            # "sin plan todavía" como un estado normal (plan pendiente
            # de aprobación), no un error de servidor.
            raise Http404("El miembro no tiene un plan nutricional aprobado todavía.")


class NutritionPlanAdminViewSet(viewsets.ModelViewSet):
    """CRUD de planes para el panel admin (Dietas por Revisar / Aprobadas)."""

    queryset = NutritionPlan.objects.all().prefetch_related("meals")
    serializer_class = NutritionPlanSerializer
    permission_classes = [IsCoach]
    filterset_fields = ["status", "member"]


class ReviewNutritionPlanView(generics.UpdateAPIView):
    """Aprobar o rechazar un plan pendiente (requisito: el coach debe
    aprobar todo plan antes de que llegue al usuario)."""

    queryset = NutritionPlan.objects.all()
    serializer_class = NutritionPlanReviewSerializer
    permission_classes = [IsCoach]

    def perform_update(self, serializer):
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())
