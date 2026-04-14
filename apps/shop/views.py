from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Product
from apps.leads.services import get_scoped_lead_form
from apps.tracking.models import UserEvent
from apps.tracking.services import record_event

from .forms import AddToCartForm, UpdateCartItemForm
from .services import (
    add_product_to_cart,
    clear_cart,
    get_cart_data,
    get_favorite_product_ids,
    get_favorite_products,
    remove_product_from_cart,
    set_product_quantity,
    toggle_favorite,
)


def _get_safe_next_url(request, fallback_url: str) -> str:
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


@require_GET
def cart_detail(request):
    cart_data = get_cart_data(request)
    update_forms = {
        line["product"].id: UpdateCartItemForm(
            initial={
                "quantity": line["quantity"],
                "next": request.get_full_path(),
            }
        )
        for line in cart_data["items"]
    }

    context = {
        "cart_data": cart_data,
        "update_forms": update_forms,
        "favorite_product_ids": get_favorite_product_ids(request),
        "cart_lead_form": get_scoped_lead_form(request, "cart"),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Корзина", "url": None},
        ],
    }
    return render(request, "shop/cart.html", context)


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    form = AddToCartForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Некорректное количество товара.")
        return redirect(_get_safe_next_url(request, product.get_absolute_url()))

    quantity = form.cleaned_data["quantity"]
    add_product_to_cart(request, product, quantity)

    record_event(
        request,
        UserEvent.EventType.CART_ADD,
        product=product,
        metadata={"quantity": quantity},
    )

    messages.success(request, f"Товар «{product.name}» добавлен в корзину.")
    return redirect(_get_safe_next_url(request, product.get_absolute_url()))


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    form = UpdateCartItemForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Некорректное количество товара.")
        return redirect(_get_safe_next_url(request, reverse("shop:cart")))

    quantity = form.cleaned_data["quantity"]
    set_product_quantity(request, product, quantity)

    if quantity <= 0:
        record_event(
            request,
            UserEvent.EventType.CART_REMOVE,
            product=product,
            metadata={"quantity": 0},
        )
        messages.success(request, f"Товар «{product.name}» удалён из корзины.")
    else:
        record_event(
            request,
            UserEvent.EventType.CART_UPDATE,
            product=product,
            metadata={"quantity": quantity},
        )
        messages.success(request, f"Количество товара «{product.name}» обновлено.")

    return redirect(_get_safe_next_url(request, reverse("shop:cart")))


@require_POST
def cart_remove(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    remove_product_from_cart(request, product)

    record_event(
        request,
        UserEvent.EventType.CART_REMOVE,
        product=product,
        metadata={"quantity": 0},
    )

    messages.success(request, f"Товар «{product.name}» удалён из корзины.")
    return redirect(_get_safe_next_url(request, reverse("shop:cart")))


@require_POST
def cart_clear_view(request):
    clear_cart(request)

    record_event(
        request,
        UserEvent.EventType.CART_CLEAR,
        metadata={"path": request.path},
    )

    messages.success(request, "Корзина очищена.")
    return redirect(_get_safe_next_url(request, reverse("shop:cart")))


@require_GET
def favorites_list(request):
    products = get_favorite_products(request)
    favorite_product_ids = {product.id for product in products}

    context = {
        "products": products,
        "favorite_product_ids": favorite_product_ids,
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Избранное", "url": None},
        ],
    }
    return render(request, "shop/favorites.html", context)


@require_POST
def favorite_toggle(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    is_now_favorite = toggle_favorite(request, product)

    record_event(
        request,
        UserEvent.EventType.FAVORITE_ADD if is_now_favorite else UserEvent.EventType.FAVORITE_REMOVE,
        product=product,
    )

    if is_now_favorite:
        messages.success(request, f"Товар «{product.name}» добавлен в избранное.")
    else:
        messages.success(request, f"Товар «{product.name}» удалён из избранного.")

    return redirect(_get_safe_next_url(request, product.get_absolute_url()))
