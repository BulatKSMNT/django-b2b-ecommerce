from rest_framework import serializers

from apps.catalog.models import (
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
)


def build_absolute_file_url(request, file_field) -> str | None:
    if not file_field:
        return None

    try:
        url = file_field.url
    except ValueError:
        return None

    if request is None:
        return url

    return request.build_absolute_uri(url)


class CategoryShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
        ]


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image_url",
            "products_count",
            "sort_order",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj: Category) -> str | None:
        request = self.context.get("request")
        return build_absolute_file_url(request, obj.image)

    def get_products_count(self, obj: Category) -> int:
        annotated_value = getattr(obj, "products_count", None)

        if annotated_value is not None:
            return annotated_value

        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image_url",
            "alt_text",
            "is_primary",
            "sort_order",
        ]

    def get_image_url(self, obj: ProductImage) -> str | None:
        request = self.context.get("request")
        return build_absolute_file_url(request, obj.image)


class ProductAttributeValueSerializer(serializers.ModelSerializer):
    attribute_id = serializers.IntegerField(read_only=True)
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = [
            "attribute_id",
            "attribute_name",
            "value",
        ]


class ProductListSerializer(serializers.ModelSerializer):
    category = CategoryShortSerializer(read_only=True)
    main_image = serializers.SerializerMethodField()
    html_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "price",
            "main_image",
            "html_url",
            "sort_order",
        ]

    def get_main_image(self, obj: Product) -> dict | None:
        image = obj.get_main_image()

        if image is None:
            return None

        request = self.context.get("request")
        image_url = build_absolute_file_url(request, image.image)

        return {
            "id": image.id,
            "image_url": image_url,
            "alt_text": image.alt_text,
            "is_primary": image.is_primary,
        }

    def get_html_url(self, obj: Product) -> str | None:
        request = self.context.get("request")
        url = obj.get_absolute_url()

        if request is None:
            return url

        return request.build_absolute_uri(url)


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributeValueSerializer(
        source="attribute_values",
        many=True,
        read_only=True,
    )

    class Meta(ProductListSerializer.Meta):
        fields = [
            *ProductListSerializer.Meta.fields,
            "description",
            "images",
            "attributes",
            "created_at",
            "updated_at",
        ]
