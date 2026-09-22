from django.db import migrations


# Values stay stable for existing API consumers; labels become more precise.
STATUS_MAP = {
    "new": "new",
    "in_progress": "in_progress",
    "completed": "completed",
    "canceled": "canceled",
}


def import_existing(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    Cycle = apps.get_model("leads", "LeadHandlingCycle")
    Policy = apps.get_model("leads", "SLAPolicy")
    Employee = apps.get_model("accounts", "EmployeeProfile")
    alias = schema_editor.connection.alias
    Policy.objects.using(alias).get_or_create(
        version=1, defaults={"response_minutes": 240, "resolution_minutes": 1440}
    )
    employees = set(Employee.objects.using(alias).values_list("user_id", flat=True))
    for lead in Lead.objects.using(alias).all().iterator():
        status = STATUS_MAP[lead.status]  # Unknown legacy states must be reviewed explicitly.
        assignee_id = lead.processed_by_id if lead.processed_by_id in employees else None
        # NEW must remain claimable; processed_by is retained as historical metadata.
        if status == "new":
            assignee_id = None
        Lead.objects.using(alias).filter(pk=lead.pk).update(status=status, assignee_id=assignee_id)
        closed = status in {"completed", "canceled"}
        end = max(lead.created_at, lead.processed_at or lead.updated_at) if closed else None
        Cycle.objects.using(alias).create(
            lead_id=lead.pk, number=1, started_at=lead.created_at, ended_at=end,
            result=status if closed else "", is_imported=True,
            # No invented contact timestamps, SLA deadlines, results or notifications.
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_existing_staff_roles"),
        ("leads", "0003_lead_management"),
    ]
    # Data import is intentionally irreversible: reversing later cycles loses history.
    operations = [migrations.RunPython(import_existing)]
