from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile, User


class ProfileInline(admin.TabularInline):
    model = Profile
    extra = 0
    fields = ("name", "profile_type", "is_default", "is_active", "created_at")
    readonly_fields = ("created_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_display = ("id", "username", "email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("id",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "profile_type", "is_default", "is_active", "created_at")
    list_filter = ("profile_type", "is_default", "is_active")
    search_fields = ("name", "user__username", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    ordering = ("user", "id")
