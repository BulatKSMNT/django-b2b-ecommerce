from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .access import require_administrator
from .models import EmployeeProfile, User


@transaction.atomic
def create_employee(*, actor, role="manager", is_available=True, user_id=None, **credentials):
    require_administrator(actor)
    if role not in EmployeeProfile.Role.values or type(is_available) is not bool:
        raise ValidationError("Некорректные параметры сотрудника.")
    if user_id is not None:
        if credentials:
            raise ValidationError("Передайте user_id или данные нового пользователя, не оба варианта.")
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if user is None:
            raise ValidationError({"user_id": "Пользователь не найден."})
    else:
        if not all(credentials.get(key) for key in ("username", "email", "password")):
            raise ValidationError("Нужны username, email и password нового сотрудника.")
        password = credentials.pop("password")
        user = User(**credentials)
        validate_password(password, user)
        user.set_password(password)
        user.full_clean()
    try:
        with transaction.atomic():
            user.save()
            return EmployeeProfile.objects.create(user=user, role=role, is_available=is_available)
    except IntegrityError:
        raise ValidationError("Пользователь или профиль сотрудника уже существует.")


@transaction.atomic
def update_employee(*, actor, employee_id, **changes):
    require_administrator(actor)
    employee = EmployeeProfile.objects.select_for_update().get(pk=employee_id)
    if employee.user_id == actor.pk or employee.user.is_superuser:
        raise ValidationError("Собственную роль и профиль суперпользователя через этот API менять нельзя.")
    if not changes or set(changes) - {"role", "is_active", "is_available"}:
        raise ValidationError("Передайте role, is_active или is_available.")
    for field, value in changes.items():
        if field == "role":
            if value not in EmployeeProfile.Role.values:
                raise ValidationError({field: "Неизвестная роль."})
        elif type(value) is not bool:
            raise ValidationError({field: "Ожидается логическое значение."})
        setattr(employee, field, value)
    employee.save(update_fields=[*changes, "updated_at"])
    return employee
