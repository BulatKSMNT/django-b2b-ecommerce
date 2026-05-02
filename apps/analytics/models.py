from django.db import models


class PageDailyMetric(models.Model):
    date = models.DateField("Дата", db_index=True)
    path = models.CharField("Путь", max_length=500)
    route_name = models.CharField("Имя маршрута", max_length=255, blank=True)

    hits = models.PositiveIntegerField("Хиты", default=0)
    unique_visitors = models.PositiveIntegerField("Уникальные посетители", default=0)
    unique_users = models.PositiveIntegerField("Уникальные пользователи", default=0)
    unique_profiles = models.PositiveIntegerField("Уникальные профили", default=0)
    avg_duration_ms = models.PositiveIntegerField("Средняя длительность, мс", default=0)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Дневная метрика страницы"
        verbose_name_plural = "Дневные метрики страниц"
        constraints =[
            models.UniqueConstraint(
                fields=("date", "path", "route_name"),
                name="unique_page_daily_metric",
            )
        ]
        ordering = ("-date", "-hits")

    def __str__(self):
        return f"{self.date} - {self.path}"


class ProductDailyMetric(models.Model):
    date = models.DateField("Дата", db_index=True)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL, # ИСПРАВЛЕНО: Сохраняем аналитику при удалении товара
        null=True,
        blank=True,
        related_name="daily_metrics",
        verbose_name="Товар",
    )
    product_name = models.CharField("Название товара", max_length=255)
    category_name = models.CharField("Категория", max_length=255, blank=True)

    product_views = models.PositiveIntegerField("Просмотры товара", default=0)
    unique_view_visitors = models.PositiveIntegerField("Уникальные посетители просмотров", default=0)
    unique_view_profiles = models.PositiveIntegerField("Уникальные профили просмотров", default=0)

    cart_adds = models.PositiveIntegerField("Добавления в корзину", default=0)
    cart_removes = models.PositiveIntegerField("Удаления из корзины", default=0)

    favorite_adds = models.PositiveIntegerField("Добавления в избранное", default=0)
    favorite_removes = models.PositiveIntegerField("Удаления из избранного", default=0)

    lead_items = models.PositiveIntegerField("Позиции в заявках", default=0)
    lead_quantity = models.PositiveIntegerField("Количество в заявках", default=0)
    lead_count = models.PositiveIntegerField("Уникальных заявок", default=0)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Дневная метрика товара"
        verbose_name_plural = "Дневные метрики товаров"
        constraints =[
            models.UniqueConstraint(
                fields=("date", "product"),
                name="unique_product_daily_metric",
            )
        ]
        ordering = ("-date", "-product_views")

    def __str__(self):
        return f"{self.date} - {self.product_name}"


class LeadScore(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"

    lead = models.OneToOneField(
        "leads.Lead",
        on_delete=models.CASCADE,
        related_name="score",
        verbose_name="Заявка",
    )
    score = models.DecimalField("Скор", max_digits=6, decimal_places=2, default=0)
    priority = models.CharField("Приоритет", max_length=20, choices=Priority.choices, default=Priority.LOW)
    model_name = models.CharField("Модель", max_length=255, blank=True)
    model_version = models.CharField("Версия модели", max_length=50, blank=True)
    features = models.JSONField("Признаки", default=dict, blank=True)
    explanation = models.JSONField("Объяснение", default=dict, blank=True)
    predicted_at = models.DateTimeField("Рассчитано", auto_now=True)

    class Meta:
        verbose_name = "Скоринг заявки"
        verbose_name_plural = "Скоринги заявок"
        ordering = ("-predicted_at",)

    def __str__(self):
        return f"Lead #{self.lead_id}: {self.score}"
