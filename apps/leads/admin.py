from django.contrib import admin
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Lead, LeadItem


class LeadItemInline(admin.TabularInline):
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


@admin.action(description="Отметить как «В работе»")
def mark_in_progress(modeladmin, request, queryset):
    queryset.update(
        status=Lead.Status.IN_PROGRESS,
        processed_by=request.user,
        processed_at=timezone.now(),
    )


@admin.action(description="Отметить как «Завершена»")
def mark_completed(modeladmin, request, queryset):
    queryset.update(
        status=Lead.Status.COMPLETED,
        processed_by=request.user,
        processed_at=timezone.now(),
    )


@admin.action(description="Отметить как «Отменена»")
def mark_canceled(modeladmin, request, queryset):
    queryset.update(
        status=Lead.Status.CANCELED,
        processed_by=request.user,
        processed_at=timezone.now(),
    )


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
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
    actions = (mark_in_progress, mark_completed, mark_canceled)

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
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

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("profile", "profile__user", "processed_by", "visitor", "score")
            .annotate(
                _items_count=Count("items"),
                _total_quantity=Sum("items__quantity"),
            )
        )

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
class LeadItemAdmin(admin.ModelAdmin):
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
