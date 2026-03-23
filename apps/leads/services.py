from django.db import transaction

from apps.tracking.services import extract_utm_params

from .forms import LeadForm
from .models import Lead, LeadItem

LEAD_FORM_STATE_SESSION_KEY = "leads_form_state"


def get_initial_lead_form_data(request) -> dict:
    if not request.user.is_authenticated:
        return {}

    fullname = request.user.get_full_name().strip() or request.user.username
    email = request.user.email or ""

    return {
        "fullname": fullname,
        "email": email,
    }


def _extract_form_data_for_session(form: LeadForm) -> dict:
    data = {}

    for field_name in form.fields.keys():
        value = form.data.get(field_name)
        if value is not None:
            data[field_name] = value

    return data


def save_lead_form_state(request, scope: str, form: LeadForm) -> None:
    request.session[LEAD_FORM_STATE_SESSION_KEY] = {
        "scope": scope,
        "data": _extract_form_data_for_session(form),
    }
    request.session.modified = True


def get_scoped_lead_form(request, scope: str) -> LeadForm:
    state = request.session.get(LEAD_FORM_STATE_SESSION_KEY)

    if state and state.get("scope") == scope:
        form = LeadForm(data=state.get("data", {}))
        form.is_valid()
        request.session.pop(LEAD_FORM_STATE_SESSION_KEY, None)
        request.session.modified = True
        return form

    return LeadForm(initial=get_initial_lead_form_data(request))


def _get_request_profile(request):
    if request.user.is_authenticated:
        return getattr(request, "profile", None)
    return None


def _get_request_visitor(request):
    return getattr(request, "visitor", None)


def build_product_snapshot(product) -> dict:
    attributes = {
        attribute_value.attribute.name: attribute_value.value
        for attribute_value in product.attribute_values.select_related("attribute").all()
    }

    return {
        "product_id": product.id,
        "product_name": product.name,
        "product_slug": product.slug,
        "category_id": product.category_id,
        "category_name": product.category.name,
        "category_slug": product.category.slug,
        "product_url": product.get_absolute_url(),
        "price": str(product.price) if product.price is not None else None,
        "attributes": attributes,
    }


@transaction.atomic
def create_base_lead(request, form: LeadForm, source: str) -> Lead:
    utm = extract_utm_params(request)

    return Lead.objects.create(
        profile=_get_request_profile(request),
        visitor=_get_request_visitor(request),
        source=source,
        fullname=form.cleaned_data["fullname"],
        phone_number=str(form.cleaned_data["phone_number"]),
        email=form.cleaned_data["email"],
        comment=form.cleaned_data.get("comment", ""),
        source_path=(request.POST.get("next") or request.get_full_path() or "")[:500],
        referer=(request.META.get("HTTP_REFERER", "") or "")[:2000],
        utm_source=utm.get("utm_source", "")[:255],
        utm_medium=utm.get("utm_medium", "")[:255],
        utm_campaign=utm.get("utm_campaign", "")[:255],
        utm_term=utm.get("utm_term", "")[:255],
        utm_content=utm.get("utm_content", "")[:255],
    )


def add_product_to_lead(lead: Lead, product, quantity: int = 1) -> LeadItem:
    quantity = max(1, int(quantity))
    product_price = product.price if product.price is not None else None
    line_total = product_price * quantity if product_price is not None else None

    return LeadItem.objects.create(
        lead=lead,
        product=product,
        product_name=product.name,
        category_name=product.category.name,
        product_slug=product.slug,
        product_url=product.get_absolute_url(),
        quantity=quantity,
        product_price=product_price,
        line_total=line_total,
        snapshot=build_product_snapshot(product),
    )


@transaction.atomic
def create_product_lead(request, form: LeadForm, product, quantity: int = 1) -> Lead:
    lead = create_base_lead(request, form, Lead.Source.PRODUCT)
    add_product_to_lead(lead, product, quantity=quantity)
    return lead


@transaction.atomic
def create_cart_lead_from_cart_data(request, form: LeadForm, cart_data: dict) -> Lead:
    items = cart_data.get("items", [])
    if not items:
        raise ValueError("Нельзя создать заявку из пустой корзины.")

    lead = create_base_lead(request, form, Lead.Source.CART)

    for line in items:
        add_product_to_lead(
            lead=lead,
            product=line["product"],
            quantity=line["quantity"],
        )

    return lead


@transaction.atomic
def create_contact_lead(request, form: LeadForm) -> Lead:
    return create_base_lead(request, form, Lead.Source.CONTACT)
