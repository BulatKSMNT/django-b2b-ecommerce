import logging
from time import perf_counter

from django.conf import settings

from .services import ensure_visitor, get_tracking_cookie_age, get_tracking_cookie_name, record_page_visit

logger = logging.getLogger(__name__)


class VisitorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ensure_visitor(request)
        response = self.get_response(request)

        if getattr(request, "_tracking_set_visitor_cookie", False) and getattr(request, "visitor", None):
            response.set_cookie(
                key=get_tracking_cookie_name(),
                value=str(request.visitor.uuid),
                max_age=get_tracking_cookie_age(),
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
        return response


class PageVisitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = perf_counter()

        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = int((perf_counter() - started_at) * 1000)
            try:
                record_page_visit(request, None, duration_ms, explicit_status_code=500)
            except Exception as e:
                logger.error(f"Failed to record page visit (500): {e}")
            raise

        duration_ms = int((perf_counter() - started_at) * 1000)
        try:
            record_page_visit(request, response, duration_ms)
        except Exception as e:
            logger.error(f"Failed to record page visit: {e}")

        return response
