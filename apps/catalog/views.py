from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.leads.services import get_scoped_lead_form
from apps.shop.services import get_favorite_product_ids
from apps.tracking.services import record_product_view

from .models import Category, Product, ProductImage, ProductAttributeValue


def category_list(request):
    search_query = request.GET.get("q", "").strip()

    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")

    if search_query:
        categories = categories.filter(name__icontains=search_query)

    context = {
        "categories": categories,
        "search_query": search_query,
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": None},
        ],
    }
    return render(request, "catalog/category_list.html", context)


def product_list(request, category_slug):
    search_query = request.GET.get("q", "").strip()

    category = get_object_or_404(
        Category.objects.filter(is_active=True),
        slug=category_slug,
    )

    image_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("sort_order", "id"),
    )

    products = (
        Product.objects.filter(category=category, is_active=True)
        .prefetch_related(image_prefetch)
        .order_by("sort_order", "name")
    )

    if search_query:
        products = products.filter(name__icontains=search_query)

    context = {
        "category": category,
        "products": products,
        "search_query": search_query,
        "favorite_product_ids": get_favorite_product_ids(request),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": reverse("catalog:category_list")},
            {"title": category.name, "url": None},
        ],
    }
    return render(request, "catalog/product_list.html", context)


def product_detail(request, category_slug, product_slug):
    category = get_object_or_404(
        Category.objects.filter(is_active=True),
        slug=category_slug,
    )

    image_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("sort_order", "id"),
    )

    attribute_prefetch = Prefetch(
        "attribute_values",
        queryset=ProductAttributeValue.objects.select_related("attribute").order_by(
            "attribute__sort_order",
            "attribute__name",
            "id",
        ),
    )

    product = get_object_or_404(
        Product.objects.filter(category=category, is_active=True)
        .select_related("category")
        .prefetch_related(image_prefetch, attribute_prefetch),
        slug=product_slug,
    )

    related_products = (
        Product.objects.filter(category=category, is_active=True)
        .exclude(pk=product.pk)
        .prefetch_related(image_prefetch)
        .order_by("sort_order", "name")[:4]
    )

    record_product_view(request, product)

    context = {
        "category": category,
        "product": product,
        "related_products": related_products,
        "favorite_product_ids": get_favorite_product_ids(request),
        "product_lead_form": get_scoped_lead_form(request, f"product:{product.id}"),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": reverse("catalog:category_list")},
            {"title": category.name, "url": category.get_absolute_url()},
            {"title": product.name, "url": None},
        ],
    }
    return render(request, "catalog/product_detail.html", context)
