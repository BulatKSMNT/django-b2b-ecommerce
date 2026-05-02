from decimal import Decimal

from django.db.models import Prefetch, Sum, F

from apps.accounts.services import ensure_user_has_default_profile
from apps.catalog.models import Product, ProductImage

from .models import Cart, CartItem, FavoriteItem

SESSION_CART_KEY = "shop_cart"
SESSION_FAVORITES_KEY = "shop_favorites"


def _get_profile_for_request(request):
    if not request.user.is_authenticated:
        return None

    profile = getattr(request, "profile", None)
    if profile:
        return profile

    return ensure_user_has_default_profile(request.user)


def _get_session_cart(request) -> dict[str, int]:
    return request.session.get(SESSION_CART_KEY, {})


def _save_session_cart(request, cart_data: dict[str, int]) -> None:
    request.session[SESSION_CART_KEY] = cart_data
    request.session.modified = True


def _get_session_favorites(request) -> list[int]:
    return request.session.get(SESSION_FAVORITES_KEY, [])


def _save_session_favorites(request, favorites: list[int]) -> None:
    request.session[SESSION_FAVORITES_KEY] = favorites
    request.session.modified = True


def get_or_create_cart(profile):
    cart, _ = Cart.objects.get_or_create(profile=profile)
    return cart


def add_product_to_cart(request, product: Product, quantity: int = 1) -> None:
    quantity = max(1, int(quantity))
    profile = _get_profile_for_request(request)

    if profile:
        cart = get_or_create_cart(profile)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": quantity},
        )
        if not created:
            item.quantity = F("quantity") + quantity
            item.save(update_fields=["quantity", "updated_at"])
        return

    session_cart = _get_session_cart(request)
    key = str(product.id)
    session_cart[key] = session_cart.get(key, 0) + quantity
    _save_session_cart(request, session_cart)

def set_product_quantity(request, product: Product, quantity: int) -> None:
    quantity = int(quantity)
    profile = _get_profile_for_request(request)

    if profile:
        cart = get_or_create_cart(profile)
        item = CartItem.objects.filter(cart=cart, product=product).first()

        if quantity <= 0:
            if item:
                item.delete()
            return

        if item:
            item.quantity = quantity
            item.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        return

    session_cart = _get_session_cart(request)
    key = str(product.id)

    if quantity <= 0:
        session_cart.pop(key, None)
    else:
        session_cart[key] = quantity

    _save_session_cart(request, session_cart)


def remove_product_from_cart(request, product: Product) -> None:
    set_product_quantity(request, product, 0)


def clear_cart(request) -> None:
    profile = _get_profile_for_request(request)

    if profile:
        cart = Cart.objects.filter(profile=profile).first()
        if cart:
            cart.items.all().delete()
        return

    _save_session_cart(request, {})


def _build_cart_line(product: Product, quantity: int) -> dict:
    quantity = int(quantity)
    line_total = None
    if product.price is not None:
        line_total = product.price * quantity

    return {
        "product": product,
        "quantity": quantity,
        "line_total": line_total,
    }


def get_cart_data(request) -> dict:
    profile = _get_profile_for_request(request)
    product_images_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("sort_order", "id"),
    )

    lines = []
    total_quantity = 0
    subtotal = Decimal("0.00")
    has_unpriced_items = False

    if profile:
        cart = (
            Cart.objects.filter(profile=profile)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CartItem.objects.select_related("product", "product__category")
                    .prefetch_related("product__images")
                    .order_by("created_at", "id"),
                )
            )
            .first()
        )

        if not cart:
            return {
                "items": [],
                "total_quantity": 0,
                "subtotal": Decimal("0.00"),
                "has_unpriced_items": False,
            }

        for item in cart.items.all():
            line = _build_cart_line(item.product, item.quantity)
            lines.append(line)
            total_quantity += item.quantity

            if line["line_total"] is not None:
                subtotal += line["line_total"]
            else:
                has_unpriced_items = True

        return {
            "items": lines,
            "total_quantity": total_quantity,
            "subtotal": subtotal,
            "has_unpriced_items": has_unpriced_items,
        }

    session_cart = _get_session_cart(request)
    if not session_cart:
        return {
            "items": [],
            "total_quantity": 0,
            "subtotal": Decimal("0.00"),
            "has_unpriced_items": False,
        }

    product_ids = [int(product_id) for product_id in session_cart.keys()]
    products = (
        Product.objects.filter(id__in=product_ids, is_active=True)
        .select_related("category")
        .prefetch_related(product_images_prefetch)
    )
    product_map = {product.id: product for product in products}

    for product_id in product_ids:
        product = product_map.get(product_id)
        if not product:
            continue

        quantity = int(session_cart[str(product_id)])
        line = _build_cart_line(product, quantity)
        lines.append(line)
        total_quantity += quantity

        if line["line_total"] is not None:
            subtotal += line["line_total"]
        else:
            has_unpriced_items = True

    return {
        "items": lines,
        "total_quantity": total_quantity,
        "subtotal": subtotal,
        "has_unpriced_items": has_unpriced_items,
    }


def get_cart_total_quantity(request) -> int:
    profile = _get_profile_for_request(request)

    if profile:
        cart = Cart.objects.filter(profile=profile).first()
        if not cart:
            return 0
        return cart.items.aggregate(total=Sum("quantity")).get("total") or 0

    return sum(_get_session_cart(request).values())


def get_favorite_product_ids(request) -> set[int]:
    profile = _get_profile_for_request(request)

    if profile:
        return set(
            FavoriteItem.objects.filter(profile=profile).values_list("product_id", flat=True)
        )

    return set(_get_session_favorites(request))


def get_favorites_count(request) -> int:
    profile = _get_profile_for_request(request)

    if profile:
        return FavoriteItem.objects.filter(profile=profile).count()

    return len(_get_session_favorites(request))


def toggle_favorite(request, product: Product) -> bool:
    """
    Возвращает True, если товар теперь в избранном.
    False — если удалён из избранного.
    """
    profile = _get_profile_for_request(request)

    if profile:
        favorite, created = FavoriteItem.objects.get_or_create(
            profile=profile,
            product=product,
        )
        if created:
            return True

        favorite.delete()
        return False

    favorites = _get_session_favorites(request)
    if product.id in favorites:
        favorites.remove(product.id)
        _save_session_favorites(request, favorites)
        return False

    favorites.append(product.id)
    _save_session_favorites(request, favorites)
    return True


def get_favorite_products(request) -> list[Product]:
    profile = _get_profile_for_request(request)
    product_images_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("sort_order", "id"),
    )

    if profile:
        favorite_items = (
            FavoriteItem.objects.filter(profile=profile)
            .select_related("product", "product__category")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        return [item.product for item in favorite_items if item.product.is_active]

    favorite_ids = _get_session_favorites(request)
    if not favorite_ids:
        return []

    products = (
        Product.objects.filter(id__in=favorite_ids, is_active=True)
        .select_related("category")
        .prefetch_related(product_images_prefetch)
    )
    product_map = {product.id: product for product in products}

    return [product_map[product_id] for product_id in favorite_ids if product_id in product_map]


def merge_session_shop_state_to_profile(request, profile) -> None:
    session_cart = _get_session_cart(request)
    if session_cart:
        for product_id, quantity in session_cart.items():
            product = Product.objects.filter(id=product_id, is_active=True).first()
            if not product:
                continue
            add_product_to_cart_for_profile(profile, product, int(quantity))

        _save_session_cart(request, {})

    session_favorites = _get_session_favorites(request)
    if session_favorites:
        for product_id in session_favorites:
            product = Product.objects.filter(id=product_id, is_active=True).first()
            if not product:
                continue
            FavoriteItem.objects.get_or_create(profile=profile, product=product)

        _save_session_favorites(request, [])


def add_product_to_cart_for_profile(profile, product: Product, quantity: int = 1) -> None:
    quantity = max(1, int(quantity))
    cart = get_or_create_cart(profile)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity},
    )
    if not created:
        item.quantity = F("quantity") + quantity
        item.save(update_fields=["quantity", "updated_at"])