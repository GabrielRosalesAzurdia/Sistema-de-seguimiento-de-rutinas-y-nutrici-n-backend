from rest_framework import viewsets, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from common.permissions import IsCoach
from .models import Member
from .serializers import (
    MemberAdminSerializer,
    MemberAppSerializer,
    MemberAppEditableSerializer,
)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Permite iniciar sesión (coach o miembro) usando email + contraseña."""
    username_field = "email"


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class MemberAdminViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de miembros para el panel de administración.
    Usado por las pantallas 'Miembros' / 'Agregar Miembro' del mockup
    del panel web (peso, medidas, meta, fecha de inicio/pago, etc.)
    """
    queryset = Member.objects.all()
    serializer_class = MemberAdminSerializer
    permission_classes = [IsCoach]
    filterset_fields = ["is_active", "is_paid", "fitness_goal"]
    search_fields = ["first_name", "first_last_name", "email"]


class MyProfileView(generics.RetrieveUpdateAPIView):
    """
    Pantalla 'Perfil' / 'Editar Perfil' de la app: el miembro solo ve y
    edita su propio perfil, sin poder tocar peso ni medidas corporales.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.member_profile

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return MemberAppEditableSerializer
        return MemberAppSerializer
