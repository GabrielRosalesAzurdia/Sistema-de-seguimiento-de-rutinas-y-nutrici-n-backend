"""
Clases de permisos DRF compartidas entre apps. Antes duplicadas
verbatim en apps/members, apps/nutrition, apps/routines y
apps/tracking (ver docs/backend_arquitectura.md sección 7).
"""
from rest_framework import permissions


class IsCoach(permissions.BasePermission):
    """Solo el coach (is_staff) — usado en todo lo administrativo:
    altas de miembros, revisión de dietas, medidas corporales, export CSV."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsCoachOrReadOnly(permissions.BasePermission):
    """Los miembros (app) solo leen; el coach (panel) puede editar."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)


class IsOwnerOrCoach(permissions.BasePermission):
    """Cualquier autenticado entra; get_queryset() de la vista es quien
    filtra: el miembro solo ve sus propios registros, el coach ve todo."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
