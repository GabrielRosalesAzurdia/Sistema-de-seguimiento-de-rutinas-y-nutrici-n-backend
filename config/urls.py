from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from apps.members.views import EmailTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Autenticación
    path("api/auth/login/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Apps
    path("api/members/", include("apps.members.urls")),
    path("api/routines/", include("apps.routines.urls")),
    path("api/nutrition/", include("apps.nutrition.urls")),
    path("api/tracking/", include("apps.tracking.urls")),
    path("api/ml/", include("apps.ml_predictions.urls")),
]
