from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import Cart, CartItem, FavoriteItem


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product",)
    fields = ("product", "quantity", "line_total", "created_at", "updated_at")
    readonly_fields = ("line_total", "created_at", "updated_at")


@admin.register(Cart)
class CartAdmin(ModelAdmin):
    list_display = ("id", "profile", "user_email", "total_quantity", "subtotal", "updated_at")
    search_fields = (
        "profile__name",
        "profile__user__username",
        "profile__user__email",
    )
    autocomplete_fields = ("profile",)
    inlines = (CartItemInline,)

    @admin.display(description="Email пользователя")
    def user_email(self, obj):
        return obj.profile.user.email

    @admin.display(description="Позиций")
    def total_quantity(self, obj):
        return obj.total_quantity

    @admin.display(description="Сумма")
    def subtotal(self, obj):
        return obj.subtotal


@admin.register(CartItem)
class CartItemAdmin(ModelAdmin):
    list_display = ("id", "cart", "product", "quantity", "line_total", "updated_at")
    search_fields = ("product__name", "cart__profile__name", "cart__profile__user__email")
    autocomplete_fields = ("cart", "product")


@admin.register(FavoriteItem)
class FavoriteItemAdmin(ModelAdmin):
    list_display = ("id", "profile", "product", "created_at")
    search_fields = ("profile__name", "profile__user__email", "product__name")
    autocomplete_fields = ("profile", "product")
