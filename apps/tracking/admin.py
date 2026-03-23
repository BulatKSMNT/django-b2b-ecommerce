from django.contrib import admin

from .models import PageVisit, ProductView, UserEvent, Visitor


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "user", "session_key", "first_seen_at", "last_seen_at")
    search_fields = ("uuid", "session_key", "user__username", "user__email")
    list_filter = ("first_seen_at", "last_seen_at")
    readonly_fields = (
        "uuid",
        "session_key",
        "user",
        "first_ip_hash",
        "last_ip_hash",
        "first_user_agent",
        "last_user_agent",
        "first_seen_at",
        "last_seen_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(PageVisit)
class PageVisitAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "method",
        "path",
        "route_name",
        "status_code",
        "duration_ms",
        "user",
        "profile",
        "visitor",
    )
    list_filter = ("method", "status_code", "route_name", "created_at")
    search_fields = (
        "path",
        "full_path",
        "route_name",
        "referer",
        "user__username",
        "user__email",
        "profile__name",
    )
    list_select_related = ("visitor", "user", "profile")
    readonly_fields = (
        "visitor",
        "user",
        "profile",
        "method",
        "path",
        "full_path",
        "route_name",
        "query_string",
        "referer",
        "user_agent",
        "ip_hash",
        "status_code",
        "duration_ms",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "created_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(ProductView)
class ProductViewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "profile",
        "visitor",
        "view_count",
        "first_viewed_at",
        "last_viewed_at",
    )
    list_filter = ("last_viewed_at", "product__category")
    search_fields = ("product__name", "profile__name", "visitor__uuid", "user__email")
    list_select_related = ("product", "profile", "visitor", "user")
    readonly_fields = (
        "visitor",
        "user",
        "profile",
        "product",
        "first_viewed_at",
        "last_viewed_at",
        "view_count",
        "last_path",
    )

    def has_add_permission(self, request):
        return False


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "product",
        "lead",
        "user",
        "profile",
        "visitor",
    )
    list_filter = ("event_type", "created_at")
    search_fields = (
        "product__name",
        "lead__fullname",
        "lead__email",
        "user__username",
        "user__email",
        "profile__name",
        "path",
    )
    list_select_related = ("product", "lead", "user", "profile", "visitor")
    readonly_fields = (
        "visitor",
        "user",
        "profile",
        "product",
        "lead",
        "event_type",
        "path",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False
