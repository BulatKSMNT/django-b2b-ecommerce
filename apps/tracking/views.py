from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.shop.services import get_favorite_product_ids

from .services import get_recent_product_views


@require_GET
def history(request):
    product_views = get_recent_product_views(request, limit=50)

    context = {
        "product_views": product_views,
        "favorite_product_ids": get_favorite_product_ids(request),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "История просмотров", "url": None},
        ],
    }
    return render(request, "tracking/history.html", context)
