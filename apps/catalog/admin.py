from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from unfold.admin import ModelAdmin, TabularInline
from .models import Category, Product, ProductImage, Attribute, ProductAttributeValue


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "preview", "alt_text", "is_primary", "sort_order")
    readonly_fields = ("preview",)

    @admin.display(description="Превью")
    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html('<img src="{}" width="100" />', obj.image.url)
        return "Нет изображения"


class ProductAttributeValueInline(TabularInline):
    model = ProductAttributeValue
    extra = 1
    autocomplete_fields = ("attribute",)


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("id", "name", "slug", "is_active", "product_count", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("is_active",)
    ordering = ("sort_order", "name")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count("products"))

    @admin.display(description="Товаров")
    def product_count(self, obj):
        return obj._product_count


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("id", "name", "category", "price", "is_active", "main_image_preview", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "description")
    autocomplete_fields = ("category",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ProductImageInline, ProductAttributeValueInline)
    list_editable = ("is_active",)
    ordering = ("category", "sort_order", "name")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category")
            .prefetch_related("images")
        )

    @admin.display(description="Изображение")
    def main_image_preview(self, obj):
        image = obj.get_main_image()
        if image and image.image:
            return format_html('<img src="{}" width="70" />', image.image.url)
        return "Нет изображения"


@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin):
    list_display = ("id", "product", "is_primary", "sort_order", "preview")
    list_filter = ("is_primary", "product__category")
    search_fields = ("product__name", "alt_text")
    autocomplete_fields = ("product",)

    @admin.display(description="Превью")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" />', obj.image.url)
        return "Нет изображения"


@admin.register(Attribute)
class AttributeAdmin(ModelAdmin):
    list_display = ("id", "name", "category", "is_active", "sort_order")
    list_filter = ("is_active", "category")
    search_fields = ("name",)
    autocomplete_fields = ("category",)


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(ModelAdmin):
    list_display = ("id", "product", "attribute", "value")
    list_filter = ("attribute__category", "attribute")
    search_fields = ("product__name", "attribute__name", "value")
    autocomplete_fields = ("product", "attribute")
