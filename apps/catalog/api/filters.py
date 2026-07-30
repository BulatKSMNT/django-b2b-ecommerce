import django_filters

from apps.catalog.models import Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")
    category_slug = django_filters.CharFilter(field_name="category__slug")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    has_price = django_filters.BooleanFilter(method="filter_has_price")

    class Meta:
        model = Product
        fields = [
            "category",
            "category_slug",
            "min_price",
            "max_price",
            "has_price",
        ]

    def filter_has_price(self, queryset, name, value):
        if value is None:
            return queryset

        return queryset.filter(price__isnull=not value)
