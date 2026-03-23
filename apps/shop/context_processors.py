from .services import get_cart_total_quantity, get_favorites_count


def shop_counters(request):
    return {
        "shop_cart_total_quantity": get_cart_total_quantity(request),
        "shop_favorites_count": get_favorites_count(request),
    }
