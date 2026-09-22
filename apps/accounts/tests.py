from django.test import TestCase
from django.core.exceptions import PermissionDenied

from .access import employee_role, require_administrator, require_employee, require_supervisor
from .models import EmployeeProfile, User


class EmployeeAccessTests(TestCase):
    def test_staff_flag_alone_does_not_grant_employee_access(self):
        user = User.objects.create_user(username="staff", email="staff@test.ru", is_staff=True)
        with self.assertRaises(PermissionDenied):
            require_employee(user)

    def test_role_hierarchy_and_inactive_employee(self):
        user = User.objects.create_user(username="manager", email="manager@test.ru")
        employee = EmployeeProfile.objects.create(user=user)
        self.assertEqual(require_employee(user), "manager")
        with self.assertRaises(PermissionDenied):
            require_supervisor(user)
        employee.role = "supervisor"
        employee.save()
        self.assertEqual(require_supervisor(user), "supervisor")
        with self.assertRaises(PermissionDenied):
            require_administrator(user)
        employee.role = "administrator"
        employee.save()
        require_administrator(user)
        employee.is_active = False
        employee.save()
        self.assertIsNone(employee_role(user))

    def test_active_superuser_can_bootstrap_employees(self):
        user = User.objects.create_superuser("root", "root@test.ru", "test")
        require_administrator(user)
        user.is_active = False
        user.save()
        with self.assertRaises(PermissionDenied):
            require_employee(user)
