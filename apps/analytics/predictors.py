from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.leads.models import Lead
from apps.tracking.models import PageVisit, UserEvent


FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yandex.ru",
    "ya.ru",
    "mail.ru",
    "bk.ru",
    "list.ru",
    "inbox.ru",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "rambler.ru",
}


def _get_email_domain(email: str) -> str:
    if "@" not in (email or ""):
        return ""
    return email.split("@", 1)[1].strip().lower()


def _get_actor_filter_for_lead(lead: Lead):
    if lead.profile_id:
        return Q(profile_id=lead.profile_id)

    if getattr(lead, "visitor_id", None):
        return Q(visitor_id=lead.visitor_id, profile__isnull=True)

    return None


def _get_lead_filter_for_previous_leads(lead: Lead):
    if lead.profile_id:
        return Q(profile_id=lead.profile_id)

    if getattr(lead, "visitor_id", None):
        return Q(visitor_id=lead.visitor_id, profile__isnull=True)

    return None


def build_lead_features(lead: Lead) -> dict:
    created_at = lead.created_at
    since_24h = created_at - timedelta(hours=24)
    since_7d = created_at - timedelta(days=7)
    since_30d = created_at - timedelta(days=30)
    since_90d = created_at - timedelta(days=90)

    items = list(lead.items.select_related("product", "product__category").all())
    requested_product_ids = [item.product_id for item in items if item.product_id]

    actor_filter = _get_actor_filter_for_lead(lead)
    previous_leads_filter = _get_lead_filter_for_previous_leads(lead)

    page_visits_24h = 0
    page_visits_7d = 0
    product_views_7d = 0
    cart_adds_7d = 0
    favorite_adds_7d = 0
    viewed_requested_products_7d = 0
    previous_leads_90d = 0
    previous_leads_30d = 0

    if actor_filter is not None:
        page_visits_24h = PageVisit.objects.filter(
            actor_filter,
            created_at__gte=since_24h,
            created_at__lte=created_at,
        ).count()

        page_visits_7d = PageVisit.objects.filter(
            actor_filter,
            created_at__gte=since_7d,
            created_at__lte=created_at,
        ).count()

        event_qs_7d = UserEvent.objects.filter(
            actor_filter,
            created_at__gte=since_7d,
            created_at__lte=created_at,
        )

        product_views_7d = event_qs_7d.filter(
            event_type=UserEvent.EventType.PRODUCT_VIEW
        ).count()

        cart_adds_7d = event_qs_7d.filter(
            event_type=UserEvent.EventType.CART_ADD
        ).count()

        favorite_adds_7d = event_qs_7d.filter(
            event_type=UserEvent.EventType.FAVORITE_ADD
        ).count()

        if requested_product_ids:
            viewed_requested_products_7d = event_qs_7d.filter(
                event_type=UserEvent.EventType.PRODUCT_VIEW,
                product_id__in=requested_product_ids,
            ).count()

    if previous_leads_filter is not None:
        previous_leads_90d = Lead.objects.filter(
            previous_leads_filter,
            created_at__gte=since_90d,
            created_at__lt=created_at,
        ).exclude(pk=lead.pk).count()

        previous_leads_30d = Lead.objects.filter(
            previous_leads_filter,
            created_at__gte=since_30d,
            created_at__lt=created_at,
        ).exclude(pk=lead.pk).count()

    comment_length = len((lead.comment or "").strip())
    email_domain = _get_email_domain(lead.email)
    is_business_email = bool(email_domain) and email_domain not in FREE_EMAIL_DOMAINS

    items_count = len(items)
    total_quantity = sum(item.quantity for item in items)
    total_amount = sum((item.line_total or Decimal("0.00")) for item in items)
    has_unpriced_items = any(item.product_price is None for item in items)
    has_items = items_count > 0

    has_utm = any(
        [
            lead.utm_source,
            lead.utm_medium,
            lead.utm_campaign,
            lead.utm_term,
            lead.utm_content,
        ]
    )

    return {
        "source": lead.source,
        "status": lead.status,
        "has_profile": bool(lead.profile_id),
        "has_visitor": bool(getattr(lead, "visitor_id", None)),
        "has_items": has_items,
        "items_count": items_count,
        "total_quantity": total_quantity,
        "total_amount": float(total_amount),
        "has_unpriced_items": has_unpriced_items,
        "comment_length": comment_length,
        "is_business_email": is_business_email,
        "email_domain": email_domain,
        "page_visits_24h": page_visits_24h,
        "page_visits_7d": page_visits_7d,
        "product_views_7d": product_views_7d,
        "cart_adds_7d": cart_adds_7d,
        "favorite_adds_7d": favorite_adds_7d,
        "viewed_requested_products_7d": viewed_requested_products_7d,
        "previous_leads_30d": previous_leads_30d,
        "previous_leads_90d": previous_leads_90d,
        "has_utm": has_utm,
        "requested_product_ids_count": len(requested_product_ids),
    }


def score_lead_features(features: dict) -> dict:
    score = 0
    explanation = []

    def add(points: int, code: str, label: str):
        nonlocal score
        if points <= 0:
            return
        score += points
        explanation.append(
            {
                "code": code,
                "label": label,
                "points": points,
            }
        )

    source = features["source"]

    if source == Lead.Source.CART:
        add(25, "source_cart", "Заявка пришла из корзины")
    elif source == Lead.Source.PRODUCT:
        add(18, "source_product", "Заявка пришла с карточки товара")
    else:
        add(8, "source_contact", "Обычная контактная заявка")

    if features["has_profile"]:
        add(8, "has_profile", "Авторизованный профиль")
    elif features["has_visitor"]:
        add(3, "has_visitor", "Есть идентификатор посетителя")

    items_count = features["items_count"]
    total_quantity = features["total_quantity"]
    total_amount = features["total_amount"]

    if items_count >= 5:
        add(20, "many_items", "В заявке много позиций")
    elif items_count >= 3:
        add(14, "several_items", "В заявке несколько позиций")
    elif items_count >= 1:
        add(7, "single_item", "В заявке есть товар")

    if total_quantity >= 10:
        add(12, "large_quantity", "Большой суммарный объём")
    elif total_quantity >= 5:
        add(8, "medium_quantity", "Средний суммарный объём")
    elif total_quantity >= 2:
        add(4, "small_quantity", "Количество больше одной единицы")

    if total_amount >= 200000:
        add(18, "high_amount", "Высокая сумма заявки")
    elif total_amount >= 100000:
        add(14, "mid_high_amount", "Заметная сумма заявки")
    elif total_amount >= 50000:
        add(10, "medium_amount", "Средняя сумма заявки")
    elif total_amount >= 10000:
        add(6, "low_amount", "Есть оценимая сумма заявки")

    if features["has_unpriced_items"]:
        add(5, "unpriced_items", "Есть товары с ценой по запросу")

    if features["is_business_email"]:
        add(8, "business_email", "Корпоративный email")

    comment_length = features["comment_length"]
    if comment_length >= 150:
        add(10, "long_comment", "Подробный комментарий клиента")
    elif comment_length >= 50:
        add(6, "medium_comment", "Есть содержательный комментарий")
    elif comment_length >= 15:
        add(3, "short_comment", "Есть комментарий")

    page_visits_24h = features["page_visits_24h"]
    page_visits_7d = features["page_visits_7d"]
    product_views_7d = features["product_views_7d"]
    cart_adds_7d = features["cart_adds_7d"]
    favorite_adds_7d = features["favorite_adds_7d"]
    viewed_requested_products_7d = features["viewed_requested_products_7d"]

    if page_visits_24h >= 8:
        add(10, "active_last_24h", "Высокая активность за последние 24 часа")
    elif page_visits_24h >= 3:
        add(5, "some_activity_last_24h", "Есть активность за последние 24 часа")

    if page_visits_7d >= 15:
        add(8, "many_page_visits", "Много просмотров страниц за 7 дней")
    elif page_visits_7d >= 5:
        add(4, "medium_page_visits", "Есть серия посещений за 7 дней")

    if product_views_7d >= 8:
        add(10, "many_product_views", "Много просмотров товаров")
    elif product_views_7d >= 3:
        add(5, "medium_product_views", "Есть интерес к товарам")

    if cart_adds_7d >= 3:
        add(12, "many_cart_adds", "Несколько добавлений в корзину")
    elif cart_adds_7d >= 1:
        add(6, "cart_adds", "Есть добавление в корзину")

    if favorite_adds_7d >= 3:
        add(6, "many_favorite_adds", "Несколько добавлений в избранное")
    elif favorite_adds_7d >= 1:
        add(3, "favorite_adds", "Есть добавление в избранное")

    if viewed_requested_products_7d >= 3:
        add(9, "viewed_requested_products_many", "Просматривал именно те товары, что вошли в заявку")
    elif viewed_requested_products_7d >= 1:
        add(4, "viewed_requested_products", "До заявки смотрел связанные товары")

    previous_leads_90d = features["previous_leads_90d"]
    if previous_leads_90d >= 3:
        add(7, "repeat_leads_many", "Повторные обращения")
    elif previous_leads_90d >= 1:
        add(4, "repeat_leads", "Клиент уже обращался ранее")

    if features["has_utm"]:
        add(2, "has_utm", "Сохранены маркетинговые метки")

    score = max(0, min(score, 100))

    if score >= 70:
        priority = "high"
    elif score >= 40:
        priority = "medium"
    else:
        priority = "low"

    return {
        "score": round(score, 2),
        "priority": priority,
        "explanation": explanation,
    }
