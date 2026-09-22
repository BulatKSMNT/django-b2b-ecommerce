from django.db import migrations


def preserve_existing(apps, schema_editor):
    Cycle = apps.get_model("leads", "LeadHandlingCycle")
    Interaction = apps.get_model("leads", "LeadInteraction")
    Lead = apps.get_model("leads", "Lead")
    alias = schema_editor.connection.alias
    for cycle in Cycle.objects.using(alias).select_related("policy").iterator():
        # Retain actual deadlines; priorities and advance warnings did not exist.
        snapshot = {}
        if cycle.policy_id:
            snapshot = {
                "policy_id": cycle.policy_id, "version": cycle.policy.version,
                "response_minutes": cycle.policy.response_minutes,
                "resolution_minutes": cycle.policy.resolution_minutes,
                "effective_response_minutes": (
                    (cycle.response_due_at - cycle.started_at).total_seconds() / 60
                    if cycle.response_due_at else None
                ),
                "effective_resolution_minutes": (
                    (cycle.resolution_due_at - cycle.started_at).total_seconds() / 60
                    if cycle.resolution_due_at else None
                ),
                "default_priority": None, "priority_overrides": {}, "warning_percent": None,
                "applied_priority": None, "priority_source": "legacy", "legacy": True,
                "response_basis": "outbound_attempt", "score": None,
            }
        attempts = Interaction.objects.using(alias).filter(
            lead_id=cycle.lead_id, cycle_id=cycle.pk, direction="outbound", occurred_at__gte=cycle.started_at,
        )
        if cycle.ended_at:
            attempts = attempts.filter(occurred_at__lte=cycle.ended_at)
        first_response = attempts.order_by("occurred_at", "pk").values_list("occurred_at", flat=True).first()
        Cycle.objects.using(alias).filter(pk=cycle.pk).update(
            policy_snapshot=snapshot, priority_source="legacy", first_response_at=first_response,
        )
    Lead.objects.using(alias).filter(next_action_at__isnull=False, next_action_revision=0).update(next_action_revision=1)
    # No recalculation, invented outbound attempts, new warnings or notifications.


class Migration(migrations.Migration):
    dependencies = [("leads", "0005_sla_snapshots_and_reminders")]
    operations = [migrations.RunPython(preserve_existing, migrations.RunPython.noop)]
