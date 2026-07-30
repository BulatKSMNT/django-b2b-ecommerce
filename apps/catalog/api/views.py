from django.db.models import Count, Prefetch, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, viewsets
from rest_framework.permissions import AllowAny

from apps.catalog.api.filters import ProductFilter
from apps.catalog.api.serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)
from apps.catalog.models import (
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
)


@extend_schema_view(
    list=extend_schema(summary="List active product categories"),
    retrieve=extend_schema(summary="Retrieve product category by slug"),
)
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "name",
        "description",
    ]

    ordering_fields = [
        "name",
        "sort_order",
        "created_at",
    ]

    ordering = [
        "sort_order",
        "name",
    ]

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                products_count=Count(
                    "products",
                    filter=Q(products__is_active=True),
                )
            )
            .order_by("sort_order", "name")
        )


@extend_schema_view(
    list=extend_schema(summary="List active products"),
    retrieve=extend_schema(summary="Retrieve product details by id"),
)
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_class = ProductFilter

    search_fields = [
        "name",
        "description",
        "category__name",
    ]

    ordering_fields = [
        "name",
        "price",
        "sort_order",
        "created_at",
    ]

    ordering = [
        "sort_order",
        "name",
    ]

    def get_queryset(self):
        image_prefetch = Prefetch(
            "images",
            queryset=ProductImage.objects.order_by("sort_order", "id"),
        )

        queryset = (
            Product.objects.filter(
                is_active=True,
                category__is_active=True,
            )
            .select_related("category")
            .prefetch_related(image_prefetch)
            .order_by("sort_order", "name")
        )

        if getattr(self, "action", None) == "retrieve":
            attribute_prefetch = Prefetch(
                "attribute_values",
                queryset=ProductAttributeValue.objects.select_related("attribute").order_by(
                    "attribute__sort_order",
                    "attribute__name",
                    "id",
                ),
            )
            queryset = queryset.prefetch_related(attribute_prefetch)

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer

        return ProductListSerializer
