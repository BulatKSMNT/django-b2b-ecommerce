from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from apps.tracking.models import UserEvent
from apps.tracking.services import record_event

from apps.catalog.models import Product
from apps.shop.services import get_cart_data

from .forms import LeadForm
from .services import (
    create_cart_lead_from_cart_data,
    create_contact_lead,
    create_product_lead,
    save_lead_form_state,
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


def _get_positive_quantity(raw_value, default=1) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(1, value)


@require_POST
def create_product_lead_view(request, product_id):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=product_id,
        is_active=True,
    )
    form = LeadForm(request.POST)
    next_url = _get_safe_next_url(request, product.get_absolute_url())

    if not form.is_valid():
        save_lead_form_state(request, f"product:{product.id}", form)
        messages.error(request, "Проверьте корректность заполнения формы.")
        return redirect(next_url)

    quantity = _get_positive_quantity(request.POST.get("quantity"), default=1)
    lead = create_product_lead(request, form, product, quantity=quantity)

    record_event(
        request,
        UserEvent.EventType.LEAD_PRODUCT_CREATED,
        product=product,
        lead=lead,
        metadata={"quantity": quantity},
    )

    messages.success(request, "Заявка по товару успешно отправлена.")
    return redirect(next_url)


@require_POST
def create_cart_lead_view(request):
    form = LeadForm(request.POST)
    next_url = _get_safe_next_url(request, reverse("shop:cart"))

    if not form.is_valid():
        save_lead_form_state(request, "cart", form)
        messages.error(request, "Проверьте корректность заполнения формы.")
        return redirect(next_url)

    cart_data = get_cart_data(request)
    if not cart_data["items"]:
        messages.error(request, "Нельзя отправить заявку из пустой корзины.")
        return redirect(next_url)

    lead = create_cart_lead_from_cart_data(request, form, cart_data)

    record_event(
        request,
        UserEvent.EventType.LEAD_CART_CREATED,
        lead=lead,
        metadata={"items_count": len(cart_data["items"])},
    )

    messages.success(request, "Заявка по корзине успешно отправлена.")
    return redirect(next_url)


@require_POST
def create_contact_lead_view(request):
    form = LeadForm(request.POST)
    next_url = _get_safe_next_url(request, reverse("pages:home"))

    if not form.is_valid():
        save_lead_form_state(request, "contact", form)
        messages.error(request, "Проверьте корректность заполнения формы.")
        return redirect(next_url)

    lead = create_contact_lead(request, form)

    record_event(
        request,
        UserEvent.EventType.LEAD_CONTACT_CREATED,
        lead=lead,
    )

    messages.success(request, "Ваша заявка успешно отправлена.")
    return redirect(next_url)
