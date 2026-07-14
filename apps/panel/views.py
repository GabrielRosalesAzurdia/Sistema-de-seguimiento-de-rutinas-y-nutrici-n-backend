from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView

from apps.members.models import Member, Gender
from apps.routines.models import (
    Routine, Exercise, RoutineExercise, RoutineCategory, ScheduledRoutineDay, Weekday,
)
from apps.nutrition.models import NutritionPlan
from apps.tracking.services import compute_study_metrics
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


class RoutinesListView(CoachRequiredMixin, TemplateView):
    """
    Pantalla 'Rutinas' (docs/mockups/admin_panel/05): sidebar con las 7
    categorías, ejercicios vigentes de la categoría seleccionada a la
    derecha. Incluye además la grilla del calendario semanal por
    género (Track B) — no está en el mockup original, se agregó por
    la decisión de negocio del calendario confirmada después.
    """

    template_name = "panel/routines_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.request.GET.get("category") or RoutineCategory.values[0]
        context["categories"] = RoutineCategory.choices
        context["selected_category"] = category
        context["routine"] = (
            Routine.objects.filter(category=category)
            .prefetch_related("exercises__exercise")
            .first()
        )
        context["weekdays"] = Weekday.choices
        context["genders"] = Gender.choices
        context["route_categories"] = RoutineCategory.choices
        schedule = {}
        for s in ScheduledRoutineDay.objects.all():
            schedule.setdefault(s.day_of_week, {})[s.gender] = s.category
        context["schedule"] = schedule
        return context


class RoutineEditExercisesView(CoachRequiredMixin, View):
    """Pantalla 'Editar ejercicios' (docs/mockups/admin_panel/06):
    selección múltiple del catálogo de la categoría (toggle), sin
    reordenar a mano — el orden se asigna según el orden de selección."""

    def get(self, request, category):
        routine = get_object_or_404(Routine, category=category)
        exercises = Exercise.objects.filter(category=category, is_active=True)
        selected_ids = set(routine.exercises.values_list("exercise_id", flat=True))
        return render(request, "panel/routine_edit.html", {
            "routine": routine, "exercises": exercises, "selected_ids": selected_ids,
        })

    def post(self, request, category):
        routine = get_object_or_404(Routine, category=category)
        selected_ids = request.POST.getlist("exercise_ids")
        RoutineExercise.objects.filter(routine=routine).delete()
        for order, exercise_id in enumerate(selected_ids, start=1):
            RoutineExercise.objects.create(routine=routine, exercise_id=exercise_id, order=order)
        messages.success(request, f"Ejercicios de {routine.get_category_display()} actualizados.")
        return redirect(f"{reverse('panel:routines-list')}?category={category}")


class ScheduleUpdateView(CoachRequiredMixin, View):
    """Guarda la grilla 7x2 del calendario semanal por género (Track B)."""

    def post(self, request):
        for day, _ in Weekday.choices:
            for gender, _ in Gender.choices:
                category = request.POST.get(f"schedule_{day}_{gender}")
                if category:
                    ScheduledRoutineDay.objects.update_or_create(
                        day_of_week=day, gender=gender, defaults={"category": category},
                    )
                else:
                    ScheduledRoutineDay.objects.filter(day_of_week=day, gender=gender).delete()
        messages.success(request, "Calendario semanal actualizado.")
        return redirect("panel:routines-list")


class NutritionReviewView(CoachRequiredMixin, TemplateView):
    """Pantalla 'Nutrición' (docs/mockups/admin_panel/07): dietas
    pendientes de revisión vs. aprobadas y en seguimiento."""

    template_name = "panel/nutrition_review.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending"] = NutritionPlan.objects.filter(
            status="PENDING_REVIEW"
        ).select_related("member").order_by("-created_at")
        context["approved"] = NutritionPlan.objects.filter(
            status="APPROVED"
        ).select_related("member").order_by("-created_at")
        return context


class NutritionPlanReviewActionView(CoachRequiredMixin, View):
    """Aprobar/rechazar un plan pendiente — misma lógica de negocio
    que apps.nutrition.views.ReviewNutritionPlanView (DRF), invocada
    aquí desde un form POST del panel en vez de un PATCH del API."""

    def post(self, request, pk):
        plan = get_object_or_404(NutritionPlan, pk=pk)
        action = request.POST.get("action")
        if action == "approve":
            plan.status = "APPROVED"
        elif action == "reject":
            plan.status = "REJECTED"
        else:
            messages.error(request, "Acción no reconocida.")
            return redirect("panel:nutrition-review")

        plan.reviewed_by = request.user
        plan.reviewed_at = timezone.now()
        plan.save()
        messages.success(request, f"Plan de {plan.member.full_name} actualizado.")
        return redirect("panel:nutrition-review")


class StudyDataView(CoachRequiredMixin, TemplateView):
    """
    Pantalla 'Datos del estudio' (docs/mockups/admin_panel/08): rango
    de fechas, promedios VD1/VD2 y tablas de detalle por miembro. El
    botón "Exportar a CSV" enlaza directo al endpoint DRF ya existente
    (GET /api/tracking/study-export/), que ahora también acepta sesión
    de Django además de JWT.
    """

    template_name = "panel/study_export.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start = self.request.GET.get("start", "")
        end = self.request.GET.get("end", "")
        metrics = compute_study_metrics(start or None, end or None)
        context["start"] = start
        context["end"] = end
        context["metrics"] = metrics
        context["avg_vd1"] = round(sum(m["vd1"] for m in metrics) / len(metrics), 1) if metrics else 0
        context["avg_vd2"] = round(sum(m["vd2"] for m in metrics) / len(metrics), 1) if metrics else 0
        return context
