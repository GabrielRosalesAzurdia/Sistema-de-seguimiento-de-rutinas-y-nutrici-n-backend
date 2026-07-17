from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from apps.members.views import EmailTokenObtainPairView, ChangePasswordView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Panel de administración web (coach)
    path("panel/", include("apps.panel.urls")),
    # Autenticación
    path("api/auth/login/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    # Apps
    path("api/members/", include("apps.members.urls")),
    path("api/routines/", include("apps.routines.urls")),
    path("api/nutrition/", include("apps.nutrition.urls")),
    path("api/tracking/", include("apps.tracking.urls")),
    path("api/ml/", include("apps.ml_predictions.urls")),
]
