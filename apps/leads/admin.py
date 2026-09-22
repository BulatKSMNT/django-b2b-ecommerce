from django.contrib import admin
from django.db.models import Count, Sum
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from uuid import uuid4

from apps.accounts.access import employee_role, require_employee
from .access import require_lead_access, visible_leads
from .management_service import LeadConflict, execute_operation
from unfold.admin import ModelAdmin, TabularInline
from .models import Lead, LeadItem, LeadInteraction


class ReadOnlyAdminMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LeadOperationForm(forms.Form):
    operation = forms.ChoiceField(choices=[
        ("claim", "Взять заявку"), ("assign", "Назначить ответственного"),
        ("change_status", "Изменить статус"), ("add_comment", "Добавить комментарий"),
        ("register_interaction", "Зарегистрировать контакт"),
        ("set_next_action", "Запланировать действие"), ("close", "Закрыть"), ("reopen", "Открыть повторно"),
    ])
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    idempotency_key = forms.CharField(max_length=128, widget=forms.HiddenInput)
    assignee_id = forms.IntegerField(required=False, min_value=1)
    status = forms.ChoiceField(choices=[("", "---------"), *Lead.Status.choices], required=False)
    text = forms.CharField(widget=forms.Textarea, required=False, max_length=10000, label="Комментарий / описание / причина / результат")
    channel = forms.ChoiceField(choices=LeadInteraction.Channel.choices, required=False)
    direction = forms.ChoiceField(choices=LeadInteraction.Direction.choices, required=False)
    contact_result = forms.ChoiceField(choices=LeadInteraction.Result.choices, required=False)
    next_action_at = forms.DateTimeField(required=False)

    def operation_data(self):
        data = self.cleaned_data
        operation = data["operation"]
        if operation == "assign":
            return {"assignee_id": data["assignee_id"]}
        if operation == "change_status":
            return {"status": data["status"]}
        if operation == "close":
            return {"status": data["status"], "result": data["text"]}
        if operation == "reopen":
            return {"reason": data["text"]}
        if operation == "add_comment":
            return {"text": data["text"]}
        if operation == "register_interaction":
            return {"channel": data["channel"], "direction": data["direction"], "result": data["contact_result"], "description": data["text"]}
        if operation == "set_next_action":
            return {"next_action": data["text"], "next_action_at": data["next_action_at"]}
        return {}


class LeadItemInline(ReadOnlyAdminMixin, TabularInline):
    model = LeadItem
    extra = 0
    autocomplete_fields = ("product",)
    fields = (
        "product",
        "product_name",
        "category_name",
        "quantity",
        "product_price",
        "line_total",
        "product_url",
        "snapshot",
    )
    readonly_fields = (
        "product_name",
        "category_name",
        "quantity",
        "product_price",
        "line_total",
        "product_url",
        "snapshot",
    )
    can_delete = False


@admin.register(Lead)
class LeadAdmin(ReadOnlyAdminMixin, ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "status",
        "source",
        "score_display",
        "priority_display",
        "fullname",
        "phone_number",
        "email",
        "profile",
        "items_count_display",
        "total_quantity_display",
        "processed_by",
    )
    list_filter = ("status", "source", "created_at", "utm_source")
    search_fields = (
        "fullname",
        "phone_number",
        "email",
        "comment",
        "manager_comment",
        "utm_source",
        "utm_campaign",
    )
    autocomplete_fields = ("profile", "processed_by", "visitor")
    readonly_fields = (
        "created_at",
        "updated_at",
        "processed_at",
        "source_path",
        "referer",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    )
    inlines = (LeadItemInline,)
    actions = None

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "manage_link",
                    "assignee",
                    "version",
                    "next_action",
                    "next_action_at",
                    "status",
                    "source",
                    "profile",
                    "visitor",
                    "fullname",
                    "phone_number",
                    "email",
                )
            },
        ),
        (
            "Комментарий",
            {
                "fields": (
                    "comment",
                    "manager_comment",
                )
            },
        ),
        (
            "Маркетинг и источник",
            {
                "fields": (
                    "source_path",
                    "referer",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "utm_term",
                    "utm_content",
                )
            },
        ),
        (
            "Обработка",
            {
                "fields": (
                    "processed_by",
                    "processed_at",
                )
            },
        ),
        (
            "Техническое",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        return ["manage_link", *[field.name for field in Lead._meta.fields]]

    def get_list_filter(self, request):
        if employee_role(request.user) == "manager":
            return ("status", "source", "created_at")
        return self.list_filter

    def get_queryset(self, request):
        return visible_leads(request.user, super().get_queryset(request)).select_related(
            "profile", "profile__user", "processed_by", "visitor", "score"
        ).annotate(_items_count=Count("items"), _total_quantity=Sum("items__quantity"))

    def has_view_permission(self, request, obj=None):
        try:
            require_employee(request.user)
            if obj:
                require_lead_access(request.user, obj)
        except PermissionDenied:
            return False
        return super().has_view_permission(request, obj)

    @admin.display(description="Обработка заявки")
    def manage_link(self, obj):
        return format_html('<a href="{}">Выполнить действие</a>', reverse("admin:leads_lead_operate", args=[obj.pk]))

    def get_urls(self):
        return [path("<int:object_id>/operate/", self.admin_site.admin_view(self.operate), name="leads_lead_operate"), *super().get_urls()]

    def operate(self, request, object_id):
        if not request.user.has_perm("leads.change_lead"):
            raise PermissionDenied
        lead = self.get_object(request, object_id)
        if lead is None:
            from django.http import Http404
            raise Http404
        require_lead_access(request.user, lead)
        form = LeadOperationForm(request.POST or None, initial={"expected_version": lead.version, "idempotency_key": str(uuid4())})
        if request.method == "POST" and form.is_valid():
            try:
                execute_operation(
                    lead_id=lead.pk, actor=request.user,
                    operation=form.cleaned_data["operation"],
                    expected_version=form.cleaned_data["expected_version"],
                    idempotency_key=form.cleaned_data["idempotency_key"],
                    **form.operation_data(),
                )
            except (ValidationError, LeadConflict) as exc:
                form.add_error(None, str(exc))
            else:
                self.message_user(request, "Действие сохранено.")
                return redirect("admin:leads_lead_change", lead.pk)
        return TemplateResponse(request, "admin/leads/operate.html", {
            **self.admin_site.each_context(request), "title": f"Обработка заявки #{lead.pk}",
            "form": form, "opts": self.model._meta, "original": lead,
        })

    @admin.display(description="Скор")
    def score_display(self, obj):
        if hasattr(obj, "score") and obj.score:
            return obj.score.score
        return "-"

    @admin.display(description="Приоритет")
    def priority_display(self, obj):
        if hasattr(obj, "score") and obj.score:
            return obj.score.get_priority_display()
        return "-"

    @admin.display(description="Позиций")
    def items_count_display(self, obj):
        return obj._items_count or 0

    @admin.display(description="Кол-во")
    def total_quantity_display(self, obj):
        return obj._total_quantity or 0


@admin.register(LeadItem)
class LeadItemAdmin(ReadOnlyAdminMixin, ModelAdmin):
    list_display = (
        "id",
        "lead",
        "product_name",
        "category_name",
        "quantity",
        "product_price",
        "line_total",
        "created_at",
    )
    list_filter = ("created_at", "category_name")
    search_fields = ("product_name", "category_name", "lead__fullname", "lead__email")
    autocomplete_fields = ("lead", "product")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(lead__in=visible_leads(request.user, Lead.objects.all()))

    def has_view_permission(self, request, obj=None):
        try:
            require_employee(request.user)
            if obj:
                require_lead_access(request.user, obj.lead)
        except PermissionDenied:
            return False
        return super().has_view_permission(request, obj)
