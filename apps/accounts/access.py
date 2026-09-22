from django.core.exceptions import PermissionDenied

from .models import EmployeeProfile


def employee_role(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return EmployeeProfile.Role.ADMINISTRATOR
    return EmployeeProfile.objects.filter(user=user, is_active=True).values_list(
        "role", flat=True
    ).first()


def require_employee(user):
    role = employee_role(user)
    if role not in EmployeeProfile.Role.values:
        raise PermissionDenied("Требуется активный профиль сотрудника.")
    return role


def require_supervisor(user):
    role = require_employee(user)
    if role == EmployeeProfile.Role.MANAGER:
        raise PermissionDenied("Требуется роль руководителя.")
    return role


def require_administrator(user):
    if require_employee(user) != EmployeeProfile.Role.ADMINISTRATOR:
        raise PermissionDenied("Требуется роль администратора.")


class SupervisorDataAdminMixin:
    """Prevent managers with legacy Django permissions from reading customer data."""

    def has_module_permission(self, request):
        return self._allowed(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return self._allowed(request) and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request) and super().has_delete_permission(request, obj)

    def _allowed(self, request):
        return employee_role(request.user) in {
            EmployeeProfile.Role.SUPERVISOR, EmployeeProfile.Role.ADMINISTRATOR
        }
