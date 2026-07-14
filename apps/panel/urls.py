from django.urls import path
from . import views

app_name = "panel"

urlpatterns = [
    path("login/", views.PanelLoginView.as_view(), name="login"),
    path("logout/", views.PanelLogoutView.as_view(), name="logout"),
    path("", views.DashboardView.as_view(), name="dashboard"),
]
