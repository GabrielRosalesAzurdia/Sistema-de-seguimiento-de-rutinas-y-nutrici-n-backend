from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Member


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ["email", "username", "is_staff", "is_active"]
    ordering = ["email"]


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = [
        "full_name", "age", "fitness_goal", "start_date",
        "next_payment_date", "is_paid", "is_active",
    ]
    list_filter = ["gender", "fitness_goal", "activity_level", "is_paid", "is_active"]
    search_fields = ["first_name", "first_last_name", "email", "phone"]
