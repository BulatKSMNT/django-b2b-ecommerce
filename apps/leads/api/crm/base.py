import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import F, Q
from django.http import Http404
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leads.api.management_views import IDEMPOTENCY, IsEmployee
from apps.leads.api.management_serializers import OperationResponseSerializer
from apps.leads.management_service import LeadConflict
from .serializers import CRMErrorSerializer

logger = logging.getLogger(__name__)


def schema(*, response, query=None, request=None, operation=False, many=False, success=200):
    parameters = [query] if query else []
    if operation:
        parameters.append(IDEMPOTENCY)
    return extend_schema(
        tags=["CRM"], request=request,
        responses={success: response(many=True) if many else response,
                   **{code: CRMErrorSerializer for code in (400, 401, 403, 404, 405, 406, 409, 415, 429, 500)}},
        parameters=parameters,
    )


def operation_schema(request):
    return schema(response=OperationResponseSerializer, request=request, operation=True)


class CRMPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CRMAutoSchema(AutoSchema):
    def _get_request_for_media_type(self, serializer, direction="request"):
        # This command requires all its arguments even though the HTTP verb is PATCH.
        # Spectacular otherwise assumes a partial model update and removes `required`.
        if self.method == "PATCH" and getattr(self.view, "action", None) == "next_action":
            component = self.resolve_serializer(serializer() if isinstance(serializer, type) else serializer, direction)
            return component.ref, True
        return super()._get_request_for_media_type(serializer, direction)


class CRMBaseMixin:
    permission_classes = [IsEmployee]
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser]
    schema = CRMAutoSchema()
    pagination_class = CRMPagination
    filter_backends = []
    lookup_value_regex = r"\d+"

    def handle_exception(self, exc):
        if isinstance(exc, LeadConflict):
            response = Response({"detail": str(exc)}, status=409)
        else:
            if isinstance(exc, DjangoValidationError):
                exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
            if isinstance(exc, ObjectDoesNotExist):
                exc = Http404()
            try:
                response = super().handle_exception(exc)
            except Exception:
                logger.exception("Unexpected CRM API error")
                response = Response({"detail": "Внутренняя ошибка сервера."}, status=500)
        codes = {
            400: "validation_error", 401: "not_authenticated", 403: "permission_denied",
            404: "not_found", 405: "method_not_allowed", 406: "not_acceptable",
            409: "conflict", 415: "unsupported_media_type", 429: "throttled", 500: "internal_error",
        }
        payload = response.data
        message = payload.get("detail") if isinstance(payload, dict) else None
        response.data = {"error": {
            "code": codes.get(response.status_code, "request_error"),
            "message": str(message or "Проверьте параметры запроса."),
            "details": {} if message else payload,
        }}
        return response

    def validated(self, serializer_class, data):
        serializer = serializer_class(data=data)
        if isinstance(data, dict):
            allowed = {name for name, field in serializer.fields.items() if not field.read_only}
            extra = set(data) - allowed
            if extra:
                raise exceptions.ValidationError({key: ["Неизвестное или неизменяемое поле."] for key in sorted(extra)})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def query(self, serializer_class):
        # Ambiguous repeated filters must not silently change meaning.
        for key, values in self.request.query_params.lists():
            if len(values) != 1:
                raise exceptions.ValidationError({key: "Передайте одно значение."})
        return self.validated(serializer_class, self.request.query_params.dict())

    def ordered(self, queryset, params, query_class, mapping=None, tie_fields=("id",)):
        mapping = mapping or {}
        ordering = params.get("ordering", query_class.default_ordering).split(",")
        for field in tie_fields:
            if field not in [value.lstrip("-") for value in ordering]:
                ordering.append(field)
        expressions = []
        for field in ordering:
            name = mapping.get(field.lstrip("-"), field.lstrip("-"))
            expression = F(name)
            expressions.append(expression.desc(nulls_last=True) if field.startswith("-") else expression.asc(nulls_last=True))
        return queryset.order_by(*expressions)

    def page_response(self, queryset, serializer_class, *, prepare=None):
        page = self.paginate_queryset(queryset)
        objects = prepare(page) if prepare else page
        return self.get_paginated_response(serializer_class(objects, many=True, context=self.get_serializer_context()).data)


def date_filter(queryset, params, field="created_at"):
    if params.get("created_from"):
        queryset = queryset.filter(**{f"{field}__gte": params["created_from"]})
    if params.get("created_to"):
        queryset = queryset.filter(**{f"{field}__lte": params["created_to"]})
    return queryset


def text_filter(queryset, search, fields):
    if search:
        query = Q()
        for field in fields:
            query |= Q(**{f"{field}__icontains": search})
        queryset = queryset.filter(query)
    return queryset


class CRMNotFoundView(CRMBaseMixin, APIView):
    @extend_schema(exclude=True)
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        raise Http404
