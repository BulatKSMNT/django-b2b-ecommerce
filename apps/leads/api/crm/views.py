from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.access import require_supervisor
from apps.accounts.models import EmployeeProfile
from apps.analytics.api.serializers import LeadScoringStatusSerializer
from apps.analytics.models import LeadScore
from apps.leads import crm_services as services
from apps.leads import management_service as operations
from apps.leads.api.management_serializers import (
    AssignSerializer, ClaimSerializer, CommentCreateSerializer, CommentSerializer,
    EmployeeSerializer, InteractionCreateSerializer, InteractionSerializer,
    NextActionSerializer, NotificationSerializer, ReopenSerializer, SLAPolicySerializer,
)
from apps.leads.api.serializers import LeadListSerializer
from apps.leads.models import Lead, LeadInteraction, Notification, SLAPolicy
from .base import CRMBaseMixin, date_filter, operation_schema, schema, text_filter
from .serializers import (
    BEHAVIOR_KINDS, EVENT_KINDS, AssignableQuerySerializer, BehaviorQuerySerializer,
    CommentQuerySerializer, CRMDashboardSerializer, CRMDictionariesSerializer,
    CRMLeadDetailSerializer, CRMLeadScoreSerializer, CRMMeSerializer, CRMQueueSerializer, CRMReadAllSerializer,
    CRMTeamSerializer, CRMTimelineSerializer, CRMTransitionSerializer, CRMBehaviorSerializer,
    DateRangeQuerySerializer, InteractionQuerySerializer, LeadQuerySerializer,
    NotificationQuerySerializer, QueueQuerySerializer, TeamQuerySerializer, TimelineQuerySerializer,
)


class CRMMeView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = CRMMeSerializer

    @schema(response=CRMMeSerializer)
    def get(self, request):
        return Response(self.get_serializer(services.current_employee(request.user)).data)


class CRMDashboardView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = CRMDashboardSerializer

    @schema(response=CRMDashboardSerializer, query=DateRangeQuerySerializer)
    def get(self, request):
        return Response(self.get_serializer(services.dashboard(request.user, **self.query(DateRangeQuerySerializer))).data)


class CRMQueueView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = CRMQueueSerializer

    @schema(response=CRMQueueSerializer, query=QueueQuerySerializer, many=True)
    def get(self, request):
        params = self.query(QueueQuerySerializer)
        queryset = Lead.objects.filter(status="new", assignee__isnull=True).prefetch_related("cycles")
        queryset = date_filter(queryset, params)
        if params.get("source"):
            queryset = queryset.filter(source=params["source"])
        if params.get("search"):
            search = params["search"].lstrip("#")
            if search.isdecimal() and len(search) <= 19 and int(search) <= 9223372036854775807:
                queryset = queryset.filter(pk=int(search))
            else:
                queryset = queryset.none()
        employee = services.current_employee(request.user)

        def prepare(page):
            for lead in page:
                lead.available_actions = services.lead_actions(request.user, lead, queue=True, employee=employee)
            return page

        return self.page_response(self.ordered(queryset, params, QueueQuerySerializer), CRMQueueSerializer, prepare=prepare)


class CRMLeadViewSet(CRMBaseMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = LeadListSerializer
    queryset = Lead.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return services.lead_read_queryset(self.request.user)

    @schema(response=LeadListSerializer, query=LeadQuerySerializer, many=True)
    def list(self, request):
        params = self.query(LeadQuerySerializer)
        queryset = date_filter(self.get_queryset(), params)
        for field in ("status", "source", "assignee_id"):
            if field in params:
                queryset = queryset.filter(**{field: params[field]})
        if "priority" in params:
            queryset = queryset.filter(score__priority=params["priority"])
        if "unassigned" in params:
            queryset = queryset.filter(assignee__isnull=params["unassigned"])
        if "overdue" in params:
            queryset = services.with_overdue(queryset).filter(sla_overdue=params["overdue"])
        if "warning" in params:
            queryset = services.with_warning(queryset).filter(sla_warning=params["warning"])
        now = timezone.now()
        if "attention" in params:
            queryset = services.with_warning(services.with_overdue(queryset, now), now)
            condition = services.attention_filter(now)
            queryset = queryset.filter(condition if params["attention"] else ~condition)
        if "awaiting_response" in params:
            queryset = services.with_awaiting_response(queryset).filter(awaiting_response=params["awaiting_response"])
        if "next_action_today" in params:
            day_start, day_end = services.today_bounds(now)
            condition = Q(next_action_at__gte=day_start, next_action_at__lt=day_end) & ~Q(status__in=operations.CLOSED_STATUSES)
            queryset = queryset.filter(condition if params["next_action_today"] else ~condition)
        for name, condition in (
            ("next_action_overdue", Q(next_action_at__lte=now)),
            ("next_action_warning", Q(next_action_remind_at__lte=now, next_action_at__gt=now)),
        ):
            if name in params:
                condition &= ~Q(status__in=operations.CLOSED_STATUSES)
                queryset = queryset.filter(condition if params[name] else ~condition)
        if "next_action_before" in params:
            queryset = queryset.filter(next_action_at__lte=params["next_action_before"])
        queryset = text_filter(queryset, params.get("search"), ("fullname", "phone_number", "email", "comment"))
        return self.page_response(self.ordered(queryset, params, LeadQuerySerializer, {"score": "score__score"}), LeadListSerializer)

    @schema(response=CRMLeadDetailSerializer)
    def retrieve(self, request, pk=None):
        lead = self.get_object()
        lead.current_cycle = lead.cycles.filter(ended_at__isnull=True).first()
        lead.available_actions = services.lead_actions(request.user, lead, lead.current_cycle)
        lead.available_transitions = [
            {"status": status, "label": Lead.Status(status).label,
             "requires_result": status in operations.CLOSED_STATUSES}
            for status in operations.allowed_status_transitions(lead, lead.current_cycle)
        ]
        return Response(CRMLeadDetailSerializer(lead, context=self.get_serializer_context()).data)

    def _operate(self, serializer_class, function, *, claim=False):
        if not claim:
            self.get_object()
        data = self.validated(serializer_class, self.request.data)
        return Response(function(
            actor=self.request.user, lead_id=self.kwargs["pk"],
            idempotency_key=self.request.headers.get("Idempotency-Key"), **data,
        ))

    @operation_schema(ClaimSerializer)
    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        return self._operate(ClaimSerializer, operations.claim_lead, claim=True)

    @operation_schema(AssignSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        require_supervisor(request.user)
        return self._operate(AssignSerializer, operations.assign_lead)

    @operation_schema(CRMTransitionSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        return self._operate(CRMTransitionSerializer, services.transition_lead)

    @operation_schema(ReopenSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._operate(ReopenSerializer, operations.reopen_lead)

    @operation_schema(NextActionSerializer)
    @action(detail=True, methods=["patch"], url_path="next-action")
    def next_action(self, request, pk=None):
        return self._operate(NextActionSerializer, operations.set_next_action)

    @schema(response=CommentSerializer, query=CommentQuerySerializer, many=True)
    @action(detail=True, methods=["get"])
    def comments(self, request, pk=None):
        params = self.query(CommentQuerySerializer)
        queryset = date_filter(self.get_object().comments.all(), params)
        for field in ("cycle_id", "author_id"):
            if field in params:
                queryset = queryset.filter(**{field: params[field]})
        queryset = text_filter(queryset, params.get("search"), ("text",))
        return self.page_response(self.ordered(queryset, params, CommentQuerySerializer), CommentSerializer)

    @operation_schema(CommentCreateSerializer)
    @comments.mapping.post
    def add_comment(self, request, pk=None):
        return self._operate(CommentCreateSerializer, operations.add_comment)

    @schema(response=InteractionSerializer, query=InteractionQuerySerializer, many=True)
    @action(detail=True, methods=["get"])
    def interactions(self, request, pk=None):
        params = self.query(InteractionQuerySerializer)
        queryset = date_filter(self.get_object().interactions.all(), params)
        for field in ("cycle_id", "author_id", "channel", "direction", "result"):
            if field in params:
                queryset = queryset.filter(**{field: params[field]})
        queryset = text_filter(queryset, params.get("search"), ("description",))
        return self.page_response(self.ordered(queryset, params, InteractionQuerySerializer), InteractionSerializer)

    @operation_schema(InteractionCreateSerializer)
    @interactions.mapping.post
    def register_interaction(self, request, pk=None):
        return self._operate(InteractionCreateSerializer, operations.register_interaction)

    @schema(response=CRMTimelineSerializer, query=TimelineQuerySerializer, many=True)
    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        lead = self.get_object()
        params = self.query(TimelineQuerySerializer)
        queryset = date_filter(lead.history_events.all(), params)
        for field in ("kind", "cycle_id"):
            if field in params:
                queryset = queryset.filter(**{field: params[field]})
        # Search only public event details, never stored idempotency receipts.
        queryset = text_filter(queryset, params.get("search"), ("kind", "data__reason", "data__result", "data__next_action"))
        return self.page_response(self.ordered(queryset, params, TimelineQuerySerializer), CRMTimelineSerializer,
                                  prepare=lambda page: services.enrich_timeline(page, lead))

    @schema(response=CRMBehaviorSerializer, query=BehaviorQuerySerializer, many=True)
    @action(detail=True, methods=["get"])
    def behavior(self, request, pk=None):
        lead = self.get_object()
        params = self.query(BehaviorQuerySerializer)
        queryset = services.behavior_queryset(request.user, lead, **{
            key: value for key, value in params.items() if key in {"kind", "search", "created_from", "created_to"}
        })
        return self.page_response(self.ordered(queryset, params, BehaviorQuerySerializer, tie_fields=("kind", "id")), CRMBehaviorSerializer)

    @schema(response=CRMLeadScoreSerializer)
    @action(detail=True, methods=["get"])
    def score(self, request, pk=None):
        lead = self.get_object()
        try:
            score = lead.score
        except ObjectDoesNotExist:
            return Response({"error": {
                "code": "not_found", "message": "Сохранённого результата скоринга нет.",
                "details": {"scoring": LeadScoringStatusSerializer(lead).data},
            }}, status=404)
        return Response(CRMLeadScoreSerializer(score).data)


class CRMTeamView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = CRMTeamSerializer

    @schema(response=CRMTeamSerializer, query=TeamQuerySerializer, many=True)
    def get(self, request):
        queryset = services.team_queryset(request.user)
        params = self.query(TeamQuerySerializer)
        queryset = date_filter(queryset, params)
        for field in ("role", "is_active", "is_available"):
            if field in params:
                queryset = queryset.filter(**{field: params[field]})
        queryset = text_filter(queryset, params.get("search"), ("user__username", "user__first_name", "user__last_name"))
        return self.page_response(self.ordered(queryset, params, TeamQuerySerializer, {"username": "user__username"}), CRMTeamSerializer)


class CRMAssignableView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = EmployeeSerializer

    @schema(response=EmployeeSerializer, query=AssignableQuerySerializer, many=True)
    def get(self, request):
        queryset = services.assignable_employees(request.user)
        params = self.query(AssignableQuerySerializer)
        queryset = text_filter(date_filter(queryset, params), params.get("search"), ("user__username", "user__first_name", "user__last_name"))
        return self.page_response(self.ordered(queryset, params, AssignableQuerySerializer, {"username": "user__username"}), EmployeeSerializer)


class CRMNotificationViewSet(CRMBaseMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return services.notifications_for(self.request.user)

    @schema(response=NotificationSerializer, query=NotificationQuerySerializer, many=True)
    def list(self, request):
        params = self.query(NotificationQuerySerializer)
        queryset = date_filter(self.get_queryset(), params)
        for field, lookup in (("unread", "read_at__isnull"), ("kind", "event__kind"), ("lead_id", "event__lead_id")):
            if field in params:
                queryset = queryset.filter(**{lookup: params[field]})
        queryset = text_filter(queryset, params.get("search"), ("event__kind",))
        return self.page_response(self.ordered(queryset, params, NotificationQuerySerializer), NotificationSerializer)

    @schema(response=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        self.validated(serializers.Serializer, request.data)
        notification = self.get_object()
        return Response(self.get_serializer(operations.mark_notification_read(actor=request.user, notification_id=notification.pk)).data)

    @schema(response=CRMReadAllSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.validated(serializers.Serializer, request.data)
        return Response(services.mark_all_notifications_read(request.user))


class CRMSLAPolicyViewSet(CRMBaseMixin, viewsets.GenericViewSet):
    serializer_class = SLAPolicySerializer
    queryset = SLAPolicy.objects.none()

    @schema(response=SLAPolicySerializer)
    @action(detail=False, methods=["get"])
    def current(self, request):
        require_supervisor(request.user)
        policy = SLAPolicy.objects.order_by("-version").first()
        if policy is None:
            raise Http404("SLA-политика не настроена.")
        return Response(self.get_serializer(policy).data)

    @schema(response=SLAPolicySerializer, request=SLAPolicySerializer, success=201)
    def create(self, request):
        require_supervisor(request.user)
        data = self.validated(SLAPolicySerializer, request.data)
        return Response(self.get_serializer(operations.create_sla_policy(actor=request.user, **data)).data, status=201)


class CRMDictionariesView(CRMBaseMixin, generics.GenericAPIView):
    serializer_class = CRMDictionariesSerializer

    @schema(response=CRMDictionariesSerializer)
    def get(self, request):
        choices = {
            "statuses": Lead.Status.choices, "sources": Lead.Source.choices,
            "priorities": LeadScore.Priority.choices, "roles": EmployeeProfile.Role.choices,
            "channels": LeadInteraction.Channel.choices, "directions": LeadInteraction.Direction.choices,
            "interaction_results": LeadInteraction.Result.choices,
            "event_kinds": EVENT_KINDS, "behavior_kinds": BEHAVIOR_KINDS,
        }
        return Response(self.get_serializer({key: [{"value": value, "label": label} for value, label in options]
                                             for key, options in choices.items()}).data)
