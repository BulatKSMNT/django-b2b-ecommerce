import hashlib
import uuid
from time import perf_counter

from django.conf import settings
from django.db import transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from .models import PageVisit, ProductView, UserEvent, Visitor

TRACKING_UTM_SESSION_KEY = "tracking_utm_params"


def get_tracking_cookie_name() -> str:
    return getattr(settings, "TRACKING_VISITOR_COOKIE_NAME", "visitor_id")


def get_tracking_cookie_age() -> int:
    return getattr(settings, "TRACKING_VISITOR_COOKIE_AGE", 60 * 60 * 24 * 365)


def get_excluded_path_prefixes() -> list[str]:
    return getattr(
        settings,
        "TRACKING_EXCLUDED_PATH_PREFIXES",
        ["/admin/", "/static/", "/media/", "/favicon.ico", "/robots.txt"],
    )


def get_client_ip(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def get_ip_hash(request) -> str:
    raw_ip = get_client_ip(request)
    if not raw_ip:
        return ""

    salt = settings.SECRET_KEY
    return hashlib.sha256(f"{salt}:{raw_ip}".encode("utf-8")).hexdigest()


def get_user_agent(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:1000]


def ensure_session_key(request) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def parse_visitor_uuid(value: str | None):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def extract_utm_params(request, *, fallback_to_session: bool = True) -> dict:
    current = {
        "utm_source": request.GET.get("utm_source", "").strip(),
        "utm_medium": request.GET.get("utm_medium", "").strip(),
        "utm_campaign": request.GET.get("utm_campaign", "").strip(),
        "utm_term": request.GET.get("utm_term", "").strip(),
        "utm_content": request.GET.get("utm_content", "").strip(),
    }

    if any(current.values()):
        request.session[TRACKING_UTM_SESSION_KEY] = current
        request.session.modified = True
        return current

    if fallback_to_session:
        return request.session.get(
            TRACKING_UTM_SESSION_KEY,
            {
                "utm_source": "",
                "utm_medium": "",
                "utm_campaign": "",
                "utm_term": "",
                "utm_content": "",
            },
        )

    return current


def ensure_visitor(request) -> Visitor:
    raw_cookie_value = request.COOKIES.get(get_tracking_cookie_name())
    visitor_uuid = parse_visitor_uuid(raw_cookie_value)

    visitor = None
    if visitor_uuid:
        visitor = Visitor.objects.filter(uuid=visitor_uuid).first()

    session_key = ensure_session_key(request)
    ip_hash = get_ip_hash(request)
    user_agent = get_user_agent(request)
    user = request.user if request.user.is_authenticated else None

    now = timezone.now()
    needs_cookie_set = False

    if visitor is None:
        visitor = Visitor.objects.create(
            session_key=session_key,
            user=user,
            first_ip_hash=ip_hash,
            last_ip_hash=ip_hash,
            first_user_agent=user_agent,
            last_user_agent=user_agent,
            last_seen_at=now,
        )
        needs_cookie_set = True
    else:
        update_fields = []

        if session_key and visitor.session_key != session_key:
            visitor.session_key = session_key
            update_fields.append("session_key")

        if user and visitor.user_id != user.id:
            visitor.user = user
            update_fields.append("user")

        if ip_hash and visitor.last_ip_hash != ip_hash:
            visitor.last_ip_hash = ip_hash
            update_fields.append("last_ip_hash")

        if user_agent and visitor.last_user_agent != user_agent:
            visitor.last_user_agent = user_agent
            update_fields.append("last_user_agent")

        if (now - visitor.last_seen_at).total_seconds() >= 60:
            visitor.last_seen_at = now
            update_fields.append("last_seen_at")

        if update_fields:
            visitor.save(update_fields=update_fields)

        if str(visitor.uuid) != str(raw_cookie_value):
            needs_cookie_set = True

    request.visitor = visitor
    request._tracking_set_visitor_cookie = needs_cookie_set
    return visitor


def should_track_page_visit(request, response=None, *, explicit_status_code: int | None = None) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False

    path = request.path or "/"

    for prefix in get_excluded_path_prefixes():
        if prefix and path.startswith(prefix):
            return False

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return False

    status_code = explicit_status_code if explicit_status_code is not None else getattr(response, "status_code", None)

    if response is not None:
        content_type = response.get("Content-Type", "")
        if status_code and status_code < 400 and "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return False

    return True


def get_route_name(request) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match:
        return ""
    return resolver_match.view_name or ""


def record_page_visit(request, response=None, duration_ms: int | None = None, *, explicit_status_code: int | None = None):
    if not should_track_page_visit(request, response, explicit_status_code=explicit_status_code):
        return None

    visitor = getattr(request, "visitor", None)
    user = request.user if request.user.is_authenticated else None
    profile = getattr(request, "profile", None) if request.user.is_authenticated else None
    utm = extract_utm_params(request)

    status_code = explicit_status_code if explicit_status_code is not None else getattr(response, "status_code", 200)

    return PageVisit.objects.create(
        visitor=visitor,
        user=user,
        profile=profile,
        method=request.method,
        path=(request.path or "")[:500],
        full_path=(request.get_full_path() or "")[:1000],
        route_name=get_route_name(request)[:255],
        query_string=(request.META.get("QUERY_STRING", "") or "")[:2000],
        referer=(request.META.get("HTTP_REFERER", "") or "")[:2000],
        user_agent=get_user_agent(request),
        ip_hash=get_ip_hash(request),
        status_code=status_code,
        duration_ms=duration_ms,
        utm_source=utm.get("utm_source", "")[:255],
        utm_medium=utm.get("utm_medium", "")[:255],
        utm_campaign=utm.get("utm_campaign", "")[:255],
        utm_term=utm.get("utm_term", "")[:255],
        utm_content=utm.get("utm_content", "")[:255],
    )


def record_event(request, event_type: str, *, product=None, lead=None, metadata: dict | None = None):
    visitor = getattr(request, "visitor", None)
    user = request.user if request.user.is_authenticated else None
    profile = getattr(request, "profile", None) if request.user.is_authenticated else None

    return UserEvent.objects.create(
        visitor=visitor,
        user=user,
        profile=profile,
        product=product,
        lead=lead,
        event_type=event_type,
        path=(request.path or "")[:500],
        metadata=metadata or {},
    )


@transaction.atomic
def record_product_view(request, product):
    visitor = getattr(request, "visitor", None)
    user = request.user if request.user.is_authenticated else None
    profile = getattr(request, "profile", None) if request.user.is_authenticated else None
    path = (request.get_full_path() or "")[:500]

    if profile:
        product_view, created = ProductView.objects.get_or_create(
            profile=profile,
            product=product,
            defaults={
                "visitor": visitor,
                "user": user,
                "view_count": 1,
                "last_path": path,
            },
        )
        if not created:
            ProductView.objects.filter(pk=product_view.pk).update(
                view_count=F("view_count") + 1,
                last_path=path,
                visitor=visitor,
                user=user,
                last_viewed_at=timezone.now(),
            )
    else:
        if not visitor:
            return None

        product_view, created = ProductView.objects.get_or_create(
            visitor=visitor,
            profile=None,
            product=product,
            defaults={
                "user": user,
                "view_count": 1,
                "last_path": path,
            },
        )
        if not created:
            ProductView.objects.filter(pk=product_view.pk).update(
                view_count=F("view_count") + 1,
                last_path=path,
                user=user,
                last_viewed_at=timezone.now(),
            )

    record_event(
        request,
        UserEvent.EventType.PRODUCT_VIEW,
        product=product,
        metadata={
            "product_id": product.id,
            "category_id": product.category_id,
            "path": path,
        },
    )

    return True


@transaction.atomic
def merge_visitor_tracking_to_profile(request, profile) -> None:
    visitor = getattr(request, "visitor", None)
    if not visitor:
        return

    user = profile.user

    PageVisit.objects.filter(visitor=visitor, profile__isnull=True).update(
        user=user,
        profile=profile,
    )

    UserEvent.objects.filter(visitor=visitor, profile__isnull=True).update(
        user=user,
        profile=profile,
    )

    guest_views = (
        ProductView.objects.filter(visitor=visitor, profile__isnull=True)
        .select_related("product")
        .order_by("id")
    )

    for guest_view in guest_views:
        target = ProductView.objects.filter(profile=profile, product=guest_view.product).first()

        if target:
            target.view_count += guest_view.view_count
            target.first_viewed_at = min(target.first_viewed_at, guest_view.first_viewed_at)
            target.last_viewed_at = max(target.last_viewed_at, guest_view.last_viewed_at)
            target.last_path = guest_view.last_path or target.last_path
            target.visitor = visitor
            target.user = user
            target.save(
                update_fields=[
                    "view_count",
                    "first_viewed_at",
                    "last_viewed_at",
                    "last_path",
                    "visitor",
                    "user",
                ]
            )
            guest_view.delete()
        else:
            guest_view.profile = profile
            guest_view.user = user
            guest_view.save(update_fields=["profile", "user"])

    if visitor.user_id != user.id:
        visitor.user = user
        visitor.save(update_fields=["user"])


def get_recent_product_views(request, limit: int = 50):
    from apps.catalog.models import ProductImage

    profile = getattr(request, "profile", None) if request.user.is_authenticated else None
    visitor = getattr(request, "visitor", None)

    image_prefetch = Prefetch(
        "product__images",
        queryset=ProductImage.objects.order_by("sort_order", "id"),
    )

    if profile:
        queryset = (
            ProductView.objects.filter(profile=profile)
            .select_related("product", "product__category")
            .prefetch_related(image_prefetch)
            .order_by("-last_viewed_at")
        )
        return queryset[:limit]

    if visitor:
        queryset = (
            ProductView.objects.filter(visitor=visitor, profile__isnull=True)
            .select_related("product", "product__category")
            .prefetch_related(image_prefetch)
            .order_by("-last_viewed_at")
        )
        return queryset[:limit]

    return ProductView.objects.none()
