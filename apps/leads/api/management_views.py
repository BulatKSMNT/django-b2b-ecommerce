from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.accounts.access import employee_role, require_supervisor
from apps.accounts.employee_services import create_employee, update_employee
from apps.accounts.models import EmployeeProfile
from apps.leads.access import visible_leads
from apps.leads.management_service import LeadConflict, create_sla_policy, execute_operation, mark_notification_read
from apps.leads.models import Lead, Notification, SLAPolicy
from .management_serializers import (
    AssignSerializer, ClaimSerializer, CloseSerializer, CommentCreateSerializer,
    CommentSerializer, ConflictSerializer, CurrentEmployeeSerializer, CycleSerializer, EmployeeCreateSerializer, EmployeeSerializer,
    EventSerializer, InteractionCreateSerializer, InteractionSerializer, NextActionSerializer,
    NotificationSerializer, OperationResponseSerializer, QueueSerializer, ReopenSerializer,
    SLAPolicySerializer, StatusSerializer,
)


class IsEmployee(BasePermission):
    def has_permission(self, request, view):
        return employee_role(request.user) in EmployeeProfile.Role.values


class ServiceErrorsMixin:
    def handle_exception(self, exc):
        if isinstance(exc, LeadConflict):
            return Response({"code": "conflict", "detail": str(exc)}, status=409)
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        if isinstance(exc, (Lead.DoesNotExist, EmployeeProfile.DoesNotExist, Notification.DoesNotExist)):
            exc = Http404()
        return super().handle_exception(exc)


IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=True,
    description="1–128 символов. Область ключа: сотрудник + заявка. Повторите исходное тело запроса.",
)


def operation_schema(serializer):
    return extend_schema(
        request=serializer, responses={
            200: OperationResponseSerializer, 400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 409: ConflictSerializer,
        },
        parameters=[IDEMPOTENCY],
    )


class LeadManagementMixin(ServiceErrorsMixin):
    def _operation(self, serializer_class, operation):
        try:
            lead_id = int(self.kwargs["pk"])
        except (ValueError, TypeError):
            raise Http404
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        # Non-claim routes use the same 404 policy as detail, including related resources.
        if operation != "claim":
            self.get_object()
        result = execute_operation(
            lead_id=lead_id, actor=self.request.user, operation=operation,
            idempotency_key=self.request.headers.get("Idempotency-Key"),
            **serializer.validated_data,
        )
        return Response(result)

    def _related(self, relation, serializer_class):
        queryset = getattr(self.get_object(), relation).all()
        page = self.paginate_queryset(queryset)
        serializer = serializer_class(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @extend_schema(responses=QueueSerializer(many=True), filters=False)
    @action(detail=False, methods=["get"], filter_backends=[])
    def queue(self, request):
        queryset = Lead.objects.filter(status=Lead.Status.NEW, assignee__isnull=True).order_by("created_at", "pk")
        page = self.paginate_queryset(queryset)
        serializer = QueueSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @operation_schema(ClaimSerializer)
    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        return self._operation(ClaimSerializer, "claim")

    @operation_schema(AssignSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        require_supervisor(request.user)
        return self._operation(AssignSerializer, "assign")

    @operation_schema(StatusSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        return self._operation(StatusSerializer, "change_status")

    @operation_schema(CloseSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._operation(CloseSerializer, "close")

    @operation_schema(ReopenSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._operation(ReopenSerializer, "reopen")

    @operation_schema(NextActionSerializer)
    @action(detail=True, methods=["post"], url_path="next-action")
    def next_action(self, request, pk=None):
        return self._operation(NextActionSerializer, "set_next_action")

    @extend_schema(responses=CommentSerializer(many=True))
    @action(detail=True, methods=["get"])
    def comments(self, request, pk=None):
        return self._related("comments", CommentSerializer)

    @operation_schema(CommentCreateSerializer)
    @comments.mapping.post
    def add_comment(self, request, pk=None):
        return self._operation(CommentCreateSerializer, "add_comment")

    @extend_schema(responses=InteractionSerializer(many=True))
    @action(detail=True, methods=["get"])
    def interactions(self, request, pk=None):
        return self._related("interactions", InteractionSerializer)

    @operation_schema(InteractionCreateSerializer)
    @interactions.mapping.post
    def register_interaction(self, request, pk=None):
        return self._operation(InteractionCreateSerializer, "register_interaction")

    @extend_schema(responses=EventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        return self._related("history_events", EventSerializer)

    @extend_schema(responses=CycleSerializer(many=True))
    @action(detail=True, methods=["get"])
    def cycles(self, request, pk=None):
        return self._related("cycles", CycleSerializer)


class NotificationViewSet(ServiceErrorsMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsEmployee]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(
            recipient=self.request.user,
            event__lead__in=visible_leads(self.request.user, Lead.objects.all()),
        ).select_related("event")

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification = mark_notification_read(actor=request.user, notification_id=notification.pk)
        return Response(self.get_serializer(notification).data)


class SLAPolicyViewSet(ServiceErrorsMixin, mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsEmployee]
    serializer_class = SLAPolicySerializer
    queryset = SLAPolicy.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_supervisor(request.user)

    def perform_create(self, serializer):
        serializer.instance = create_sla_policy(actor=self.request.user, **serializer.validated_data)


class EmployeeViewSet(ServiceErrorsMixin, viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    permission_classes = [IsEmployee]
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EmployeeProfile.objects.none()
        if self.action != "me":
            require_supervisor(self.request.user)
        return EmployeeProfile.objects.select_related("user").order_by("id")

    @extend_schema(responses=CurrentEmployeeSerializer)
    @action(detail=False, methods=["get"])
    def me(self, request):
        profile = self.get_queryset().filter(user=request.user).first()
        return Response({
            "employee_id": profile.pk if profile else None,
            "user_id": request.user.pk, "username": request.user.username,
            "role": employee_role(request.user),
            "is_available": bool(profile and profile.is_available and profile.is_active),
        })

    @extend_schema(request=EmployeeCreateSerializer, responses={201: EmployeeSerializer})
    def create(self, request):
        serializer = EmployeeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = create_employee(actor=request.user, **serializer.validated_data)
        return Response(EmployeeSerializer(employee).data, status=201)

    @extend_schema(request=EmployeeSerializer, responses=EmployeeSerializer)
    def partial_update(self, request, pk=None):
        self.get_object()
        serializer = EmployeeSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        employee = update_employee(actor=request.user, employee_id=pk, **serializer.validated_data)
        return Response(EmployeeSerializer(employee).data)
