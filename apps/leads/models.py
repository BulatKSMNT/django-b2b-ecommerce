from decimal import Decimal

from django.conf import settings
from django.db import models


class Lead(models.Model):
    class Source(models.TextChoices):
        CONTACT = "contact", "Обычная форма"
        PRODUCT = "product", "Заявка с товара"
        CART = "cart", "Заявка из корзины"

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        COMPLETED = "completed", "Завершена"
        CANCELED = "canceled", "Отменена"

    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="Профиль",
    )
    visitor = models.ForeignKey(
        "tracking.Visitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="Посетитель",
    )

    source = models.CharField(
        "Источник",
        max_length=20,
        choices=Source.choices,
        default=Source.CONTACT,
        db_index=True,
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )

    fullname = models.CharField("ФИО", max_length=255)
    phone_number = models.CharField("Телефон", max_length=50)
    email = models.EmailField("Email")

    comment = models.TextField("Комментарий клиента", blank=True)

    source_path = models.CharField("Страница отправки", max_length=500, blank=True)
    referer = models.TextField("Referer", blank=True)

    utm_source = models.CharField("UTM source", max_length=255, blank=True, db_index=True)
    utm_medium = models.CharField("UTM medium", max_length=255, blank=True)
    utm_campaign = models.CharField("UTM campaign", max_length=255, blank=True)
    utm_term = models.CharField("UTM term", max_length=255, blank=True)
    utm_content = models.CharField("UTM content", max_length=255, blank=True)

    manager_comment = models.TextField("Комментарий менеджера", blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_leads",
        verbose_name="Обработал",
    )
    processed_at = models.DateTimeField("Дата обработки", null=True, blank=True)

    created_at = models.DateTimeField("Создана", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Заявка #{self.pk} — {self.fullname}"

    @property
    def items_count(self) -> int:
        return self.items.count()

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def total_amount(self) -> Decimal:
        total = Decimal("0.00")
        for item in self.items.all():
            if item.line_total is not None:
                total += item.line_total
        return total


class LeadItem(models.Model):
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заявка",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_items",
        verbose_name="Текущий товар",
    )

    product_name = models.CharField("Название товара", max_length=255)
    category_name = models.CharField("Категория", max_length=255, blank=True)
    product_slug = models.CharField("Slug товара", max_length=255, blank=True)
    product_url = models.CharField("URL товара", max_length=500, blank=True)

    quantity = models.PositiveIntegerField("Количество", default=1)
    product_price = models.DecimalField(
        "Цена на момент заявки",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    line_total = models.DecimalField(
        "Сумма позиции",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    snapshot = models.JSONField("Снимок товара", default=dict, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Позиция заявки"
        verbose_name_plural = "Позиции заявки"
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}"
