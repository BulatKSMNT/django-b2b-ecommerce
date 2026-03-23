from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.analytics.models import PageDailyMetric, ProductDailyMetric
from apps.leads.models import LeadItem
from apps.tracking.models import PageVisit, UserEvent


class Command(BaseCommand):
    help = "Пересчитывает дневные агрегаты для аналитики"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Дата в формате YYYY-MM-DD. По умолчанию вчера.",
        )

    def handle(self, *args, **options):
        if options["date"]:
            target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
        else:
            target_date = timezone.localdate() - timedelta(days=1)

        self.stdout.write(self.style.NOTICE(f"Собираем агрегаты за {target_date}"))

        self.build_page_metrics(target_date)
        self.build_product_metrics(target_date)

        self.stdout.write(self.style.SUCCESS("Готово."))

    def build_page_metrics(self, target_date):
        PageDailyMetric.objects.filter(date=target_date).delete()

        rows = (
            PageVisit.objects.filter(created_at__date=target_date)
            .values("path", "route_name")
            .annotate(
                hits=Count("id"),
                unique_visitors=Count("visitor", distinct=True),
                unique_users=Count("user", distinct=True),
                unique_profiles=Count("profile", distinct=True),
                avg_duration=Avg("duration_ms"),
            )
            .order_by()
        )

        objects = [
            PageDailyMetric(
                date=target_date,
                path=row["path"],
                route_name=row["route_name"] or "",
                hits=row["hits"] or 0,
                unique_visitors=row["unique_visitors"] or 0,
                unique_users=row["unique_users"] or 0,
                unique_profiles=row["unique_profiles"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]

        PageDailyMetric.objects.bulk_create(objects, batch_size=1000)

    def build_product_metrics(self, target_date):
        ProductDailyMetric.objects.filter(date=target_date).delete()

        event_rows = (
            UserEvent.objects.filter(created_at__date=target_date, product__isnull=False)
            .values("product_id", "product__name", "product__category__name")
            .annotate(
                product_views=Count("id", filter=Q(event_type=UserEvent.EventType.PRODUCT_VIEW)),
                unique_view_visitors=Count(
                    "visitor",
                    filter=Q(event_type=UserEvent.EventType.PRODUCT_VIEW),
                    distinct=True,
                ),
                unique_view_profiles=Count(
                    "profile",
                    filter=Q(event_type=UserEvent.EventType.PRODUCT_VIEW),
                    distinct=True,
                ),
                cart_adds=Count("id", filter=Q(event_type=UserEvent.EventType.CART_ADD)),
                cart_removes=Count("id", filter=Q(event_type=UserEvent.EventType.CART_REMOVE)),
                favorite_adds=Count("id", filter=Q(event_type=UserEvent.EventType.FAVORITE_ADD)),
                favorite_removes=Count("id", filter=Q(event_type=UserEvent.EventType.FAVORITE_REMOVE)),
            )
            .order_by()
        )

        lead_rows = (
            LeadItem.objects.filter(lead__created_at__date=target_date, product__isnull=False)
            .values("product_id")
            .annotate(
                lead_items=Count("id"),
                lead_quantity=Sum("quantity"),
                lead_count=Count("lead_id", distinct=True),
            )
            .order_by()
        )

        lead_map = {row["product_id"]: row for row in lead_rows}

        objects = []
        for row in event_rows:
            lead_data = lead_map.get(row["product_id"], {})
            objects.append(
                ProductDailyMetric(
                    date=target_date,
                    product_id=row["product_id"],
                    product_name=row["product__name"],
                    category_name=row["product__category__name"] or "",
                    product_views=row["product_views"] or 0,
                    unique_view_visitors=row["unique_view_visitors"] or 0,
                    unique_view_profiles=row["unique_view_profiles"] or 0,
                    cart_adds=row["cart_adds"] or 0,
                    cart_removes=row["cart_removes"] or 0,
                    favorite_adds=row["favorite_adds"] or 0,
                    favorite_removes=row["favorite_removes"] or 0,
                    lead_items=lead_data.get("lead_items", 0) or 0,
                    lead_quantity=lead_data.get("lead_quantity", 0) or 0,
                    lead_count=lead_data.get("lead_count", 0) or 0,
                )
            )

        ProductDailyMetric.objects.bulk_create(objects, batch_size=1000)
