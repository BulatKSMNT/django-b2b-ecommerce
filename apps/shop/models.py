from django.db import models

# Create your models here.
from decimal import Decimal

from django.db import models
from django.db.models import Sum


class Cart(models.Model):
    profile = models.OneToOneField(
        "accounts.Profile",
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name="Профиль",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"Корзина профиля {self.profile_id}"

    @property
    def total_quantity(self) -> int:
        return self.items.aggregate(total=Sum("quantity")).get("total") or 0

    @property
    def subtotal(self) -> Decimal:
        total = Decimal("0.00")
        for item in self.items.select_related("product").all():
            if item.product.price is not None:
                total += item.product.price * item.quantity
        return total


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Корзина",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="Товар",
    )
    quantity = models.PositiveIntegerField("Количество", default=1)
    created_at = models.DateTimeField("Добавлен", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Позиция корзины"
        verbose_name_plural = "Позиции корзины"
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "product"),
                name="unique_product_per_cart",
            ),
        ]
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        if self.product.price is None:
            return None
        return self.product.price * self.quantity


class FavoriteItem(models.Model):
    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.CASCADE,
        related_name="favorite_items",
        verbose_name="Профиль",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="favorite_items",
        verbose_name="Товар",
    )
    created_at = models.DateTimeField("Добавлен", auto_now_add=True)

    class Meta:
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "product"),
                name="unique_product_per_profile_favorites",
            ),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.profile} → {self.product}"
