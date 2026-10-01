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
        # Le dice a la app si debe forzar "Crear tu contraseña" antes del Dashboard.
        data["must_change_password"] = self.user.must_change_password
        return data


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class ChangePasswordView(APIView):
    """Cambia la contraseña del usuario autenticado y limpia must_change_password."""

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
    """CRUD completo de miembros para el panel de administración."""
    queryset = Member.objects.all()
    serializer_class = MemberAdminSerializer
    permission_classes = [IsCoach]


class MyProfileView(generics.RetrieveUpdateAPIView):
    """El miembro solo ve y edita su propio perfil; no puede tocar peso ni medidas corporales."""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.member_profile

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return MemberAppEditableSerializer
        return MemberAppSerializer
