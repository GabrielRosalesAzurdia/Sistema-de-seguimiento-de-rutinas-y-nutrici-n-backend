from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import MyCurrentPlanView, NutritionPlanAdminViewSet, ReviewNutritionPlanView

router = DefaultRouter()
router.register("plans", NutritionPlanAdminViewSet, basename="nutrition-plan")

urlpatterns = [
    path("me/current-plan/", MyCurrentPlanView.as_view(), name="my-current-plan"),
    path("plans/<int:pk>/review/", ReviewNutritionPlanView.as_view(), name="review-plan"),
] + router.urls
