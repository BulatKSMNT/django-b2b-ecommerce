from django.shortcuts import render

from apps.catalog.models import Category
from apps.leads.services import get_scoped_lead_form


def home(request):
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")[:6]

    context = {
        "categories": categories,
        "contact_lead_form": get_scoped_lead_form(request, "contact"),
    }
    return render(request, "pages/home.html", context)
