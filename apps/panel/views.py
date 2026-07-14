from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, CreateView, UpdateView

from apps.members.models import Member
from .forms import MemberForm
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


class MembersListView(CoachRequiredMixin, ListView):
    """Pantalla 'Miembros' (docs/mockups/admin_panel/02_miembros_listado.jpeg)."""

    model = Member
    template_name = "panel/members_list.html"
    context_object_name = "members"
    paginate_by = 25

    def get_queryset(self):
        qs = Member.objects.all().order_by("first_name", "first_last_name")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(first_name__icontains=query)
                | Q(first_last_name__icontains=query)
                | Q(email__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        return context


class MemberFormActionMixin:
    """Botones compartidos por 'Agregar'/'Editar Miembro'
    (docs/mockups/admin_panel/03 y 04): Guardar / Pagado / (editar:
    Desactivar Usuario) — todos reenvían el mismo form, distinguidos
    por el nombre del botón presionado."""

    form_class = MemberForm
    template_name = "panel/member_form.html"
    success_url = reverse_lazy("panel:members-list")

    def form_valid(self, form):
        response = super().form_valid(form)
        if "mark_paid" in self.request.POST:
            self.object.is_paid = True
            self.object.save()
            messages.success(self.request, f"{self.object.full_name} marcado como pagado.")
        elif "deactivate" in self.request.POST:
            self.object.is_active = False
            self.object.save()
            messages.success(self.request, f"{self.object.full_name} desactivado.")
        else:
            messages.success(self.request, f"{self.object.full_name} guardado.")
        return response


class MemberCreateView(MemberFormActionMixin, CoachRequiredMixin, CreateView):
    """Pantalla 'Agregar Miembro' (docs/mockups/admin_panel/04)."""


class MemberUpdateView(MemberFormActionMixin, CoachRequiredMixin, UpdateView):
    """Pantalla 'Editar Miembro' (docs/mockups/admin_panel/03)."""

    model = Member
