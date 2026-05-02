from django.core.cache import cache
from .services import get_cart_total_quantity, get_favorites_count


def shop_counters(request):
    if not request.user.is_authenticated:
        return {
            "shop_cart_total_quantity": get_cart_total_quantity(request),
            "shop_favorites_count": get_favorites_count(request),
        }

    profile = getattr(request, "profile", None)
    if not profile:
        return {"shop_cart_total_quantity": 0, "shop_favorites_count": 0}

    cache_key = f"shop_counters_{profile.id}"
    data = cache.get(cache_key)

    if data is None:
        data = {
            "shop_cart_total_quantity": get_cart_total_quantity(request),
            "shop_favorites_count": get_favorites_count(request),
        }
        cache.set(cache_key, data, timeout=60)

    return data
