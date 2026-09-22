from django.core.exceptions import PermissionDenied

from apps.accounts.access import require_employee
from apps.accounts.models import EmployeeProfile


def visible_leads(user, queryset):
    if require_employee(user) == EmployeeProfile.Role.MANAGER:
        return queryset.filter(assignee=user)
    return queryset


def require_lead_access(user, lead):
    if require_employee(user) == EmployeeProfile.Role.MANAGER and lead.assignee_id != user.pk:
        raise PermissionDenied("Нет доступа к этой заявке.")
