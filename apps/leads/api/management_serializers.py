from rest_framework import serializers

from apps.accounts.models import EmployeeProfile
from apps.leads.models import Lead, LeadComment, LeadEvent, LeadHandlingCycle, LeadInteraction, Notification, SLAPolicy
from .sla_serializers import PriorityDeadlineSerializer


class OperationResponseSerializer(serializers.Serializer):
    lead_id = serializers.IntegerField()
    version = serializers.IntegerField()
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    assignee_id = serializers.IntegerField(allow_null=True)
    cycle_id = serializers.IntegerField()
    event_id = serializers.IntegerField()
    resource_id = serializers.IntegerField(allow_null=True)


class ConflictSerializer(serializers.Serializer):
    code = serializers.CharField(default="conflict")
    detail = serializers.CharField()


class VersionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class ClaimSerializer(VersionSerializer):
    expected_version = serializers.IntegerField(min_value=1, required=False)


class AssignSerializer(VersionSerializer):
    assignee_id = serializers.IntegerField(min_value=1)


class StatusSerializer(VersionSerializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)


class CloseSerializer(StatusSerializer):
    status = serializers.ChoiceField(choices=["completed", "canceled"])
    result = serializers.CharField(max_length=10000)


class ReopenSerializer(VersionSerializer):
    reason = serializers.CharField(max_length=10000)


class CommentCreateSerializer(VersionSerializer):
    text = serializers.CharField(max_length=10000)


class InteractionCreateSerializer(VersionSerializer):
    channel = serializers.ChoiceField(choices=LeadInteraction.Channel.choices)
    direction = serializers.ChoiceField(choices=LeadInteraction.Direction.choices)
    result = serializers.ChoiceField(choices=LeadInteraction.Result.choices)
    description = serializers.CharField(max_length=10000)
    occurred_at = serializers.DateTimeField(required=False)


class NextActionSerializer(VersionSerializer):
    next_action = serializers.CharField(max_length=10000)
    next_action_at = serializers.DateTimeField()


class QueueSerializer(serializers.ModelSerializer):
    """Whitelist only. Do not embed score features, customer names or free text."""
    class Meta:
        model = Lead
        fields = ["id", "source", "status", "created_at", "version"]


class CycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadHandlingCycle
        fields = [
            "id", "number", "started_at", "ended_at", "policy_id", "response_due_at", "resolution_due_at",
            "first_contact_at", "first_response_at", "response_warning_at", "resolution_warning_at",
            "priority", "priority_source", "policy_snapshot", "result", "result_description", "is_imported",
        ]


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadComment
        fields = ["id", "cycle_id", "author_id", "text", "created_at"]


class InteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadInteraction
        fields = ["id", "cycle_id", "author_id", "channel", "direction", "result", "description", "occurred_at", "created_at"]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadEvent
        fields = ["id", "cycle_id", "actor_id", "kind", "data", "version", "reminder_revision", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    lead_id = serializers.IntegerField(source="event.lead_id", read_only=True)
    kind = serializers.CharField(source="event.kind", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "event_id", "lead_id", "kind", "created_at", "read_at"]


class SLAPolicySerializer(serializers.ModelSerializer):
    priority_overrides = serializers.DictField(child=PriorityDeadlineSerializer(), required=False)
    warning_percent = serializers.IntegerField(min_value=1, max_value=99, required=False)

    class Meta:
        model = SLAPolicy
        fields = ["id", "version", "response_minutes", "resolution_minutes", "default_priority", "priority_overrides", "warning_percent", "created_by_id", "created_at"]
        read_only_fields = ["id", "version", "created_by_id", "created_at"]
        extra_kwargs = {"response_minutes": {"required": True, "min_value": 1}, "resolution_minutes": {"required": True, "min_value": 1}}


class EmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = EmployeeProfile
        fields = ["id", "user_id", "username", "first_name", "last_name", "role", "is_active", "is_available"]
        read_only_fields = ["id", "user_id", "username", "first_name", "last_name"]


class EmployeeCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1, required=False)
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=EmployeeProfile.Role.choices, default="manager")
    is_available = serializers.BooleanField(default=True)


class CurrentEmployeeSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(allow_null=True)
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    role = serializers.ChoiceField(choices=EmployeeProfile.Role.choices)
    is_available = serializers.BooleanField()
