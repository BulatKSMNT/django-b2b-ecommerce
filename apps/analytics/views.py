from datetime import timedelta

from django.contrib import admin
from django.db.models import Avg, Count, Q, Sum
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.leads.models import Lead, LeadItem
from apps.tracking.models import PageVisit, UserEvent

from .models import LeadScore, PageDailyMetric, ProductDailyMetric


def admin_analytics_dashboard(request):
    raw_days = request.GET.get("days", "7")
    allowed_days = {1, 7, 14, 30, 90}

    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        days = 7

    if days not in allowed_days:
        days = 7

    since = timezone.now() - timedelta(days=days)

    page_visits_qs = PageVisit.objects.filter(created_at__gte=since)
    events_qs = UserEvent.objects.filter(created_at__gte=since)
    leads_qs = Lead.objects.filter(created_at__gte=since)

    product_view_events = events_qs.filter(event_type=UserEvent.EventType.PRODUCT_VIEW)
    cart_add_events = events_qs.filter(event_type=UserEvent.EventType.CART_ADD)
    favorite_add_events = events_qs.filter(event_type=UserEvent.EventType.FAVORITE_ADD)

    overview = {
        "page_hits": page_visits_qs.count(),
        "unique_visitors": page_visits_qs.exclude(visitor__isnull=True).values("visitor_id").distinct().count(),
        "unique_profiles": page_visits_qs.exclude(profile__isnull=True).values("profile_id").distinct().count(),
        "avg_page_duration_ms": int(page_visits_qs.aggregate(avg=Avg("duration_ms"))["avg"] or 0),
        "product_views": product_view_events.count(),
        "cart_adds": cart_add_events.count(),
        "favorite_adds": favorite_add_events.count(),
        "leads_total": leads_qs.count(),
        "high_priority_leads": leads_qs.filter(score__priority="high").count(),
    }

    product_to_cart_rate = 0
    if overview["product_views"]:
        product_to_cart_rate = round(overview["cart_adds"] / overview["product_views"] * 100, 2)

    cart_to_lead_rate = 0
    cart_source_leads = leads_qs.filter(source=Lead.Source.CART).count()
    if overview["cart_adds"]:
        cart_to_lead_rate = round(cart_source_leads / overview["cart_adds"] * 100, 2)

    top_pages = list(
        page_visits_qs.values("path", "route_name")
        .annotate(
            hits=Count("id"),
            unique_visitors=Count("visitor", distinct=True),
            avg_duration_ms=Avg("duration_ms"),
        )
        .order_by("-hits", "path")[:10]
    )

    product_event_rows = list(
        events_qs.filter(product__isnull=False)
        .values("product_id", "product__name", "product__category__name")
        .annotate(
            product_views=Count("id", filter=Q(event_type=UserEvent.EventType.PRODUCT_VIEW)),
            cart_adds=Count("id", filter=Q(event_type=UserEvent.EventType.CART_ADD)),
            favorite_adds=Count("id", filter=Q(event_type=UserEvent.EventType.FAVORITE_ADD)),
        )
        .order_by("-product_views", "-cart_adds", "-favorite_adds")[:20]
    )

    lead_rows = list(
        LeadItem.objects.filter(lead__created_at__gte=since, product__isnull=False)
        .values("product_id")
        .annotate(
            lead_count=Count("lead_id", distinct=True),
            lead_quantity=Sum("quantity"),
        )
        .order_by()
    )
    lead_map = {row["product_id"]: row for row in lead_rows}

    top_products = []
    for row in product_event_rows[:10]:
        lead_data = lead_map.get(row["product_id"], {})
        top_products.append(
            {
                "product_id": row["product_id"],
                "product_name": row["product__name"],
                "category_name": row["product__category__name"] or "",
                "product_views": row["product_views"] or 0,
                "cart_adds": row["cart_adds"] or 0,
                "favorite_adds": row["favorite_adds"] or 0,
                "lead_count": lead_data.get("lead_count", 0) or 0,
                "lead_quantity": lead_data.get("lead_quantity", 0) or 0,
            }
        )

    source_labels = dict(Lead.Source.choices)
    status_labels = dict(Lead.Status.choices)

    lead_sources = list(
        leads_qs.values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    for row in lead_sources:
        row["label"] = source_labels.get(row["source"], row["source"])

    lead_statuses = list(
        leads_qs.values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    for row in lead_statuses:
        row["label"] = status_labels.get(row["status"], row["status"])

    hot_leads = (
        Lead.objects.select_related("profile", "score")
        .filter(created_at__gte=since, score__isnull=False)
        .order_by("-score__score", "-created_at")[:10]
    )

    latest_page_metric = PageDailyMetric.objects.order_by("-date").first()
    latest_product_metric = ProductDailyMetric.objects.order_by("-date").first()

    context = {
        **admin.site.each_context(request),
        "title": "Аналитический dashboard",
        "days": days,
        "allowed_days": sorted(allowed_days),
        "since": since,
        "overview": overview,
        "product_to_cart_rate": product_to_cart_rate,
        "cart_to_lead_rate": cart_to_lead_rate,
        "top_pages": top_pages,
        "top_products": top_products,
        "lead_sources": lead_sources,
        "lead_statuses": lead_statuses,
        "hot_leads": hot_leads,
        "latest_page_metric": latest_page_metric,
        "latest_product_metric": latest_product_metric,
    }
    return TemplateResponse(request, "admin/analytics/dashboard.html", context)
