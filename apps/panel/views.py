from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .mixins import CoachRequiredMixin


class PanelLoginView(LoginView):
    template_name = "panel/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("panel:dashboard")


class PanelLogoutView(LogoutView):
    next_page = reverse_lazy("panel:login")


class DashboardView(CoachRequiredMixin, TemplateView):
    """Placeholder — el contenido real (stats, actividad reciente) se
    construye en un paso posterior del roadmap."""

    template_name = "panel/dashboard.html"
