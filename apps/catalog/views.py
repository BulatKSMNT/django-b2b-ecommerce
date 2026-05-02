from django.core.paginator import Paginator
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

    #Добавлена пагинация (по 12 категорий на страницу)
    paginator = Paginator(categories, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "categories": page_obj, # Передаем объект пагинации как categories
        "page_obj": page_obj,   # Передаем для шаблона пагинации
        "search_query": search_query,
        "breadcrumbs":[
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": None},
        ],
    }
    return render(request, "catalog/category_list.html", context)



def product_list(request, category_slug):
    search_query = request.GET.get("q", "").strip()

    # ИСПРАВЛЕНО: Убрали .filter(is_active=True), чтобы страница открывалась по ссылке
    category = get_object_or_404(Category, slug=category_slug)

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

    paginator = Paginator(products, 16)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "category": category,
        "products": page_obj,
        "page_obj": page_obj,
        "search_query": search_query,
        "favorite_product_ids": get_favorite_product_ids(request),
        "breadcrumbs":[
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": reverse("catalog:category_list")},
            {"title": category.name, "url": None},
        ],
    }
    return render(request, "catalog/product_list.html", context)



def product_detail(request, category_slug, product_slug):
    category = get_object_or_404(Category, slug=category_slug)

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

    # ИСПРАВЛЕНО: Убрали is_active=True для самого товара
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related(image_prefetch, attribute_prefetch),
        category=category,
        slug=product_slug,
    )

    # А вот в похожих товарах оставляем is_active=True (мертвые товары в рекомендациях не нужны)
    related_products = (
        Product.objects.filter(category=category, is_active=True)
        .exclude(pk=product.pk)
        .prefetch_related(image_prefetch)
        .order_by("sort_order", "name")
    )

    record_product_view(request, product)

    context = {
        "category": category,
        "product": product,
        "related_products": related_products,
        "favorite_product_ids": get_favorite_product_ids(request),
        "product_lead_form": get_scoped_lead_form(request, f"product:{product.id}"),
        "breadcrumbs":[
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Каталог", "url": reverse("catalog:category_list")},
            {"хъ": category.name, "url": category.get_absolute_url()},
            {"title": product.name, "url": None},
        ],
    }
    return render(request, "catalog/product_detail.html", context)

