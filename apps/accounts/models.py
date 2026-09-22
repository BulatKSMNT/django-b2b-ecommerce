from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField("Email", unique=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class Profile(models.Model):
    class ProfileType(models.TextChoices):
        PERSONAL = "personal", "Личный"
        COMPANY = "company", "Компания"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="profiles",
        verbose_name="Пользователь",
    )
    name = models.CharField("Название профиля", max_length=255)
    profile_type = (models.CharField
(
        "Тип профиля",
        max_length=20,
        choices=ProfileType.choices,
        default=ProfileType.PERSONAL,
    ))
    is_default = models.BooleanField("Профиль по умолчанию", default=False)
    is_active = models.BooleanField("Активный", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class EmployeeProfile(models.Model):
    """Employee access is independent of customer profiles and Django admin access."""

    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        SUPERVISOR = "supervisor", "Руководитель"
        ADMINISTRATOR = "administrator", "Администратор"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="employee_profile"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MANAGER)
    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"
