"""Control de acceso del panel: solo el coach (is_staff) puede ver cualquier pantalla."""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class CoachRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "panel:login"

    def test_func(self):
        return bool(self.request.user and self.request.user.is_staff)
