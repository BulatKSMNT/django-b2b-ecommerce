from django.contrib import admin

from unfold.admin import ModelAdmin, TabularInline
from .models import LeadScore, PageDailyMetric, ProductDailyMetric


@admin.register(PageDailyMetric)
class PageDailyMetricAdmin(ModelAdmin):
    list_display = ("date", "path", "route_name", "hits", "unique_visitors", "unique_profiles", "avg_duration_ms")
    list_filter = ("date", "route_name")
    search_fields = ("path", "route_name")
    readonly_fields = [field.name for field in PageDailyMetric._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ProductDailyMetric)
class ProductDailyMetricAdmin(ModelAdmin):
    list_display = (
        "date",
        "product_name",
        "category_name",
        "product_views",
        "cart_adds",
        "favorite_adds",
        "lead_count",
    )
    list_filter = ("date", "category_name")
    search_fields = ("product_name", "category_name")
    readonly_fields = [field.name for field in ProductDailyMetric._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(LeadScore)
class LeadScoreAdmin(ModelAdmin):
    list_display = ("lead", "score", "priority", "model_name", "model_version", "predicted_at")
    list_filter = ("priority", "model_name", "model_version")
    search_fields = ("lead__fullname", "lead__email", "lead__phone_number")
    readonly_fields = [field.name for field in LeadScore._meta.fields if field.name != "id"]
