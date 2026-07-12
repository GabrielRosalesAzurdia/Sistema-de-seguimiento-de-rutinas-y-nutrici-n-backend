from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import MyProgressPredictionView, MLPredictionAdminViewSet

router = DefaultRouter()
router.register("predictions", MLPredictionAdminViewSet, basename="ml-prediction")

urlpatterns = [
    path("me/progress/", MyProgressPredictionView.as_view(), name="my-progress-prediction"),
] + router.urls
