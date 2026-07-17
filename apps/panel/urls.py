from django.urls import path
from . import views

app_name = "panel"

urlpatterns = [
    path("login/", views.PanelLoginView.as_view(), name="login"),
    path("logout/", views.PanelLogoutView.as_view(), name="logout"),
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("miembros/", views.MembersListView.as_view(), name="members-list"),
    path("miembros/agregar/", views.MemberCreateView.as_view(), name="member-create"),
    path("miembros/<int:pk>/editar/", views.MemberUpdateView.as_view(), name="member-update"),
    path("miembros/<int:pk>/fitness/", views.MemberFitnessUpdateView.as_view(), name="member-fitness-update"),
    path(
        "miembros/<int:pk>/desactivar/",
        views.MemberToggleActiveView.as_view(), {"activate": False},
        name="member-deactivate",
    ),
    path(
        "miembros/<int:pk>/reactivar/",
        views.MemberToggleActiveView.as_view(), {"activate": True},
        name="member-reactivate",
    ),
    path(
        "miembros/<int:pk>/nutricion/generar/",
        views.GenerateNutritionPlanView.as_view(), name="nutrition-plan-generate",
    ),
    path("rutinas/", views.RoutinesListView.as_view(), name="routines-list"),
    path("rutinas/<str:category>/editar/", views.RoutineEditExercisesView.as_view(), name="routine-edit"),
    path("rutinas/calendario/", views.ScheduleUpdateView.as_view(), name="schedule-update"),
    path("nutricion/", views.NutritionReviewView.as_view(), name="nutrition-review"),
    path("nutricion/<int:pk>/revisar/", views.NutritionPlanDetailView.as_view(), name="nutrition-plan-detail"),
    path("estudio/", views.StudyDataView.as_view(), name="study-data"),
]
