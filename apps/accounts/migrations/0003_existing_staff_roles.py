from django.db import migrations


def migrate_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Employee = apps.get_model("accounts", "EmployeeProfile")
    alias = schema_editor.connection.alias
    for user in User.objects.using(alias).filter(is_staff=True).iterator():
        Employee.objects.using(alias).get_or_create(
            user_id=user.pk,
            defaults={
                "role": "administrator" if user.is_superuser else "supervisor",
                "is_active": user.is_active,
                "is_available": user.is_active,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_employee_profile")]
    operations = [migrations.RunPython(migrate_staff, migrations.RunPython.noop)]
