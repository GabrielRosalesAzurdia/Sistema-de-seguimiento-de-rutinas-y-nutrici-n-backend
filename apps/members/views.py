from rest_framework import viewsets, permissions, generics, status
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
    ChangePasswordSerializer,
)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Permite iniciar sesión (coach o miembro) usando email + contraseña."""
    username_field = "email"

    def validate(self, attrs):
        data = super().validate(attrs)
        # Evita un round-trip extra a /me/ para saber si la app debe
        # forzar la pantalla de "Crear tu contraseña" tras el login
        # (contraseña temporal generada al dar de alta al miembro).
        data["must_change_password"] = self.user.must_change_password
        return data


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class ChangePasswordView(APIView):
    """Cambia la contraseña del usuario autenticado (coach o miembro) y
    limpia el flag must_change_password — usado tanto por el flujo
    obligatorio de primer login (contraseña temporal) como por la
    opción normal 'Cambiar contraseña' desde Perfil."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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
