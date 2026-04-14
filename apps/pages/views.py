from django.shortcuts import render
from django.urls import reverse

from apps.catalog.models import Category
from apps.leads.services import get_scoped_lead_form


CONTACT_DATA = {
    "phone": "+79991234567",
    "email": "mail@mail.ru",
    "address": "г. Москва, ул. Примерная, д. 123",
}


def home(request):
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")[:6]

    context = {
        "categories": categories,
        "contact_lead_form": get_scoped_lead_form(request, "contact"),
    }
    return render(request, "pages/home.html", context)


def about(request):
    context = {
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "О компании", "url": None},
        ]
    }
    return render(request, "pages/about.html", context)


def contacts(request):
    context = {
        "contact_data": CONTACT_DATA,
        "contact_lead_form": get_scoped_lead_form(request, "contact"),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Контакты", "url": None},
        ],
    }
    return render(request, "pages/contacts.html", context)


def privacy_policy(request):
    context = {
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Политика конфиденциальности", "url": None},
        ]
    }
    return render(request, "pages/privacy_policy.html", context)


def personal_data(request):
    context = {
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Персональные данные", "url": None},
        ]
    }
    return render(request, "pages/personal_data.html", context)


def public_offer(request):
    context = {
        "breadcrumbs":[
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Публичная оферта", "url": None},
        ]
    }
    return render(request, "pages/public_offer.html", context)


def delivery_payment(request):
    context = {
        "breadcrumbs":[
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Доставка и оплата", "url": None},
        ]
    }
    return render(request, "pages/delivery_payment.html", context)
