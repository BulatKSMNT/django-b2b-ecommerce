from rest_framework import serializers

from apps.accounts.models import EmployeeProfile
from apps.analytics.models import LeadScore
from apps.analytics.api.serializers import LeadScoreSerializer, LeadScoringStatusSerializer
from apps.leads.api.management_serializers import (
    CommentSerializer, CurrentEmployeeSerializer, CycleSerializer, EmployeeSerializer,
    EventSerializer, InteractionSerializer, QueueSerializer, VersionSerializer,
)
from apps.leads.api.serializers import LeadDetailSerializer
from apps.leads.api.sla_serializers import LeadSLASerializer
from apps.leads.models import Lead, LeadInteraction
from apps.tracking.models import UserEvent


class CRMErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField()


class CRMErrorSerializer(serializers.Serializer):
    error = CRMErrorDetailSerializer()


class CRMPermissionsSerializer(serializers.Serializer):
    view_team = serializers.BooleanField()
    assign_leads = serializers.BooleanField()
    manage_sla = serializers.BooleanField()
    manage_employees = serializers.BooleanField()


class CRMMeSerializer(CurrentEmployeeSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    permissions = CRMPermissionsSerializer()


class CRMQueueActionsSerializer(serializers.Serializer):
    claim = serializers.BooleanField()
    assign = serializers.BooleanField()


class CRMActionsSerializer(CRMQueueActionsSerializer):
    transition = serializers.BooleanField()
    reopen = serializers.BooleanField()
    add_comment = serializers.BooleanField()
    register_interaction = serializers.BooleanField()
    set_next_action = serializers.BooleanField()


class CRMTransitionOptionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    label = serializers.CharField()
    requires_result = serializers.BooleanField()


class CRMLeadDetailSerializer(LeadDetailSerializer):
    current_cycle = CycleSerializer(read_only=True, allow_null=True)
    available_actions = CRMActionsSerializer(read_only=True)
    available_transitions = CRMTransitionOptionSerializer(many=True, read_only=True)

    class Meta(LeadDetailSerializer.Meta):
        fields = [*LeadDetailSerializer.Meta.fields, "current_cycle", "available_actions", "available_transitions"]


class CRMLeadScoreSerializer(LeadScoreSerializer):
    scoring = LeadScoringStatusSerializer(source="lead", read_only=True)

    class Meta(LeadScoreSerializer.Meta):
        fields = [*LeadScoreSerializer.Meta.fields, "scoring"]


class CRMQueueSerializer(QueueSerializer):
    available_actions = CRMQueueActionsSerializer(read_only=True)
    sla = LeadSLASerializer(source="*", read_only=True, allow_null=True)

    class Meta(QueueSerializer.Meta):
        fields = [*QueueSerializer.Meta.fields, "available_actions", "sla"]


class CRMTransitionSerializer(VersionSerializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    result = serializers.CharField(max_length=10000, required=False)

    def validate(self, attrs):
        if attrs["status"] in {"completed", "canceled"}:
            if not attrs.get("result"):
                raise serializers.ValidationError({"result": "Результат или причина закрытия обязательны."})
        elif "result" in attrs:
            raise serializers.ValidationError({"result": "Поле допускается только при закрытии."})
        return attrs


class CRMTimelineSerializer(EventSerializer):
    comment = CommentSerializer(source="crm_comment", read_only=True, allow_null=True)
    interaction = InteractionSerializer(source="crm_interaction", read_only=True, allow_null=True)

    class Meta(EventSerializer.Meta):
        fields = [*EventSerializer.Meta.fields, "comment", "interaction"]


class CRMBehaviorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    product_id = serializers.IntegerField(allow_null=True)
    product_name = serializers.CharField(allow_null=True, allow_blank=True)
    route_name = serializers.CharField(allow_blank=True)
    duration_ms = serializers.IntegerField(allow_null=True)
    association = serializers.ChoiceField(choices=["lead", "profile", "visitor"])


class CRMTeamSerializer(EmployeeSerializer):
    user_is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    assigned_count = serializers.IntegerField(read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    overdue_count = serializers.IntegerField(read_only=True)
    warning_count = serializers.IntegerField(read_only=True)
    awaiting_response_count = serializers.IntegerField(read_only=True)
    due_today_count = serializers.IntegerField(read_only=True)
    next_action_overdue_count = serializers.IntegerField(read_only=True)

    class Meta(EmployeeSerializer.Meta):
        fields = [*EmployeeSerializer.Meta.fields, "user_is_active", "assigned_count", "open_count", "overdue_count",
                  "warning_count", "awaiting_response_count", "due_today_count", "next_action_overdue_count"]


class CRMLeadCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    open = serializers.IntegerField()
    completed = serializers.IntegerField()
    canceled = serializers.IntegerField()
    sla_overdue = serializers.IntegerField()
    sla_warning = serializers.IntegerField()
    next_action_overdue = serializers.IntegerField()
    next_action_warning = serializers.IntegerField()
    awaiting_response = serializers.IntegerField()
    requires_attention = serializers.IntegerField()
    created_today = serializers.IntegerField()
    next_actions_today = serializers.IntegerField()


class CRMDashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    created_from = serializers.DateTimeField(allow_null=True)
    created_to = serializers.DateTimeField(allow_null=True)
    leads = CRMLeadCountsSerializer()
    by_status = serializers.DictField(child=serializers.IntegerField())
    queue_count = serializers.IntegerField()
    unread_notifications = serializers.IntegerField()


class CRMReadAllSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()


class CRMChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CRMDictionariesSerializer(serializers.Serializer):
    statuses = CRMChoiceSerializer(many=True)
    sources = CRMChoiceSerializer(many=True)
    priorities = CRMChoiceSerializer(many=True)
    roles = CRMChoiceSerializer(many=True)
    channels = CRMChoiceSerializer(many=True)
    directions = CRMChoiceSerializer(many=True)
    interaction_results = CRMChoiceSerializer(many=True)
    event_kinds = CRMChoiceSerializer(many=True)
    behavior_kinds = CRMChoiceSerializer(many=True)


class DateRangeQuerySerializer(serializers.Serializer):
    created_from = serializers.DateTimeField(required=False)
    created_to = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs.get("created_from") and attrs.get("created_to") and attrs["created_from"] > attrs["created_to"]:
            raise serializers.ValidationError({"created_to": "Конец периода должен быть не раньше начала."})
        return attrs


class PageQuerySerializer(DateRangeQuerySerializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    ordering = serializers.CharField(max_length=200, required=False)
    ordering_fields = {"id", "created_at"}
    default_ordering = "-created_at"

    def validate_ordering(self, value):
        fields = value.split(",")
        if any(field.lstrip("-") not in self.ordering_fields or field.startswith("--") for field in fields):
            raise serializers.ValidationError("Недопустимое поле сортировки.")
        return value


class LeadQuerySerializer(PageQuerySerializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices, required=False)
    source = serializers.ChoiceField(choices=Lead.Source.choices, required=False)
    priority = serializers.ChoiceField(choices=LeadScore.Priority.choices, required=False)
    assignee_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    unassigned = serializers.BooleanField(required=False)
    overdue = serializers.BooleanField(required=False)
    warning = serializers.BooleanField(required=False)
    attention = serializers.BooleanField(required=False)
    awaiting_response = serializers.BooleanField(required=False)
    next_action_today = serializers.BooleanField(required=False)
    next_action_overdue = serializers.BooleanField(required=False)
    next_action_warning = serializers.BooleanField(required=False)
    next_action_before = serializers.DateTimeField(required=False)
    ordering_fields = {"id", "created_at", "updated_at", "status", "source", "next_action_at", "score"}


class QueueQuerySerializer(PageQuerySerializer):
    source = serializers.ChoiceField(choices=Lead.Source.choices, required=False)
    ordering_fields = {"id", "created_at", "source"}
    default_ordering = "created_at"


class CommentQuerySerializer(PageQuerySerializer):
    cycle_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    author_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)


class InteractionQuerySerializer(CommentQuerySerializer):
    channel = serializers.ChoiceField(choices=LeadInteraction.Channel.choices, required=False)
    direction = serializers.ChoiceField(choices=LeadInteraction.Direction.choices, required=False)
    result = serializers.ChoiceField(choices=LeadInteraction.Result.choices, required=False)
    ordering_fields = {"id", "created_at", "occurred_at"}
    default_ordering = "-occurred_at"


EVENT_KINDS = [
    ("created", "Создана"), ("claim", "Взята в работу"), ("assign", "Ответственный назначен"),
    ("change_status", "Статус изменён"), ("close", "Закрыта"), ("reopen", "Открыта повторно"),
    ("add_comment", "Комментарий добавлен"), ("register_interaction", "Контакт зарегистрирован"),
    ("set_next_action", "Действие запланировано"),
    ("sla_response_warning", "Приближается срок реакции"), ("sla_response_overdue", "Просрочена реакция"),
    ("sla_resolution_warning", "Приближается срок закрытия"), ("sla_resolution_overdue", "Просрочено закрытие"),
    ("next_action_warning", "Приближается следующее действие"), ("next_action_overdue", "Просрочено следующее действие"),
]


class TimelineQuerySerializer(PageQuerySerializer):
    kind = serializers.ChoiceField(choices=EVENT_KINDS, required=False)
    cycle_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)


BEHAVIOR_KINDS = [("page_view", "Посещение страницы"), *[
    choice for choice in UserEvent.EventType.choices
    if choice[0] in {"product_view", "cart_add", "cart_update", "cart_remove", "cart_clear", "favorite_add", "favorite_remove",
                     "lead_contact_created", "lead_product_created", "lead_cart_created"}
]]


class BehaviorQuerySerializer(PageQuerySerializer):
    kind = serializers.ChoiceField(choices=BEHAVIOR_KINDS, required=False)
    ordering_fields = {"id", "occurred_at", "kind"}
    default_ordering = "-occurred_at"


class TeamQuerySerializer(PageQuerySerializer):
    role = serializers.ChoiceField(choices=EmployeeProfile.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    is_available = serializers.BooleanField(required=False)
    ordering_fields = {"id", "username", "created_at", "open_count", "overdue_count", "assigned_count",
                       "warning_count", "awaiting_response_count", "due_today_count", "next_action_overdue_count"}
    default_ordering = "username"


class AssignableQuerySerializer(PageQuerySerializer):
    ordering_fields = {"id", "username", "created_at"}
    default_ordering = "username"


class NotificationQuerySerializer(PageQuerySerializer):
    unread = serializers.BooleanField(required=False)
    kind = serializers.ChoiceField(choices=EVENT_KINDS, required=False)
    lead_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    ordering_fields = {"id", "created_at", "read_at"}
