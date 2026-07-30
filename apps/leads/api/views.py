from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.analytics.api.serializers import LeadScoreSerializer
from apps.analytics.services import score_lead_by_id
from apps.leads.api.serializers import (
    LeadContactCreateSerializer,
    LeadDetailSerializer,
    LeadListSerializer,
)
from apps.leads.models import Lead, LeadItem
from apps.leads.services import create_contact_lead
from apps.tracking.models import UserEvent
from apps.tracking.services import record_event


@extend_schema_view(
    list=extend_schema(summary="List leads"),
    retrieve=extend_schema(summary="Retrieve lead details"),
)
class LeadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin/staff API for leads plus public contact lead creation endpoint.

    Regular list/detail endpoints are protected because leads contain personal data.
    """

    permission_classes = [IsAdminUser]

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "fullname",
        "email",
        "phone_number",
        "comment",
    ]

    ordering_fields = [
        "created_at",
        "updated_at",
        "source",
        "status",
    ]

    ordering = [
        "-created_at",
    ]

    def get_queryset(self):
        item_prefetch = Prefetch(
            "items",
            queryset=LeadItem.objects.select_related(
                "product",
                "product__category",
            ).order_by("id"),
        )

        return (
            Lead.objects.select_related(
                "profile",
                "visitor",
                "processed_by",
                "score",
            )
            .prefetch_related(item_prefetch)
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return LeadListSerializer

        if self.action == "contact":
            return LeadContactCreateSerializer

        return LeadDetailSerializer

    @extend_schema(
        summary="Create contact lead",
        request=LeadContactCreateSerializer,
        responses={201: LeadDetailSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="contact",
        permission_classes=[AllowAny],
    )
    def contact(self, request):
        """
        Public endpoint for creating a contact lead via REST API.

        This reuses the existing LeadForm and create_contact_lead service.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form = serializer.validated_data["_form"]
        lead = create_contact_lead(request, form)

        record_event(
            request,
            UserEvent.EventType.LEAD_CONTACT_CREATED,
            lead=lead,
            metadata={"source": "api"},
        )

        response_serializer = LeadDetailSerializer(
            lead,
            context=self.get_serializer_context(),
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Get current lead score",
        responses={200: LeadScoreSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="score",
        permission_classes=[IsAdminUser],
    )
    def score(self, request, pk=None):
        """
        Return existing lead score.

        Does not recalculate the score.
        Use POST /api/v1/leads/{id}/score/recalculate/ for recalculation.
        """
        lead = self.get_object()

        try:
            score_obj = lead.score
        except ObjectDoesNotExist:
            return Response(
                {
                    "detail": "Score has not been calculated yet.",
                    "lead_id": lead.id,
                    "hint": "Use POST /api/v1/leads/{id}/score/recalculate/.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LeadScoreSerializer(
            score_obj,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    @extend_schema(
        summary="Recalculate lead score",
        responses={200: LeadScoreSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="score/recalculate",
        permission_classes=[IsAdminUser],
    )
    def recalculate_score(self, request, pk=None):
        """
        Recalculate rule-based lead score using analytics service.
        """
        lead = self.get_object()
        score_obj = score_lead_by_id(lead.id)

        if score_obj is None:
            return Response(
                {"detail": "Lead not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LeadScoreSerializer(
            score_obj,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)
