from rest_framework import serializers

from apps.analytics.models import LeadScore
from apps.leads.sla import next_action_summary, sla_summary

SLA_STATES = ["not_configured", "pending", "warning", "overdue", "met", "breached", "closed"]
NEXT_ACTION_STATES = ["not_scheduled", "pending", "warning", "overdue", "closed"]


class DeadlineSerializer(serializers.Serializer):
    due_at = serializers.DateTimeField(allow_null=True)
    warning_at = serializers.DateTimeField(allow_null=True)
    fulfilled_at = serializers.DateTimeField(allow_null=True)
    state = serializers.ChoiceField(choices=SLA_STATES)


class LeadSLASerializer(serializers.Serializer):
    cycle_id = serializers.IntegerField()
    priority = serializers.ChoiceField(choices=LeadScore.Priority.choices, allow_null=True)
    priority_source = serializers.CharField(allow_null=True)
    policy_version = serializers.IntegerField(allow_null=True)
    response = DeadlineSerializer()
    resolution = DeadlineSerializer()

    def to_representation(self, instance):
        data = sla_summary(instance, self.context.get("now"))
        return super().to_representation(data) if data is not None else None


class NextActionReminderSerializer(serializers.Serializer):
    revision = serializers.IntegerField()
    due_at = serializers.DateTimeField(allow_null=True)
    warning_at = serializers.DateTimeField(allow_null=True)
    state = serializers.ChoiceField(choices=NEXT_ACTION_STATES)

    def to_representation(self, instance):
        return super().to_representation(next_action_summary(instance, self.context.get("now")))


class PriorityDeadlineSerializer(serializers.Serializer):
    response_minutes = serializers.IntegerField(min_value=1, max_value=525600)
    resolution_minutes = serializers.IntegerField(min_value=1, max_value=525600)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError("Допустимы только response_minutes и resolution_minutes.")
        return super().to_internal_value(data)
