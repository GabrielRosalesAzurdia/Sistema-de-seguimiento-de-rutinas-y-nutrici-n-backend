from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import MemberAdminViewSet, MyProfileView

router = DefaultRouter()
router.register("", MemberAdminViewSet, basename="member")

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="my-profile"),
] + router.urls
