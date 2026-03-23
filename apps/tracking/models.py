import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Visitor(models.Model):
    uuid = models.UUIDField("UUID", default=uuid.uuid4, unique=True, editable=False)
    session_key = models.CharField("Ключ сессии", max_length=64, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors",
        verbose_name="Пользователь",
    )

    first_ip_hash = models.CharField("Первый IP hash", max_length=64, blank=True, db_index=True)
    last_ip_hash = models.CharField("Последний IP hash", max_length=64, blank=True, db_index=True)

    first_user_agent = models.TextField("Первый User-Agent", blank=True)
    last_user_agent = models.TextField("Последний User-Agent", blank=True)

    first_seen_at = models.DateTimeField("Первый визит", auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField("Последняя активность", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Посетитель"
        verbose_name_plural = "Посетители"
        ordering = ("-last_seen_at",)

    def __str__(self) -> str:
        return f"Visitor {self.uuid}"


class PageVisit(models.Model):
    visitor = models.ForeignKey(
        "tracking.Visitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_visits",
        verbose_name="Посетитель",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_visits",
        verbose_name="Пользователь",
    )
    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_visits",
        verbose_name="Профиль",
    )

    method = models.CharField("Метод", max_length=10, default="GET")
    path = models.CharField("Путь", max_length=500, db_index=True)
    full_path = models.CharField("Полный путь", max_length=1000, blank=True)
    route_name = models.CharField("Имя маршрута", max_length=255, blank=True, db_index=True)
    query_string = models.TextField("Query string", blank=True)

    referer = models.TextField("Referer", blank=True)
    user_agent = models.TextField("User-Agent", blank=True)
    ip_hash = models.CharField("IP hash", max_length=64, blank=True, db_index=True)

    status_code = models.PositiveSmallIntegerField("HTTP статус", default=200, db_index=True)
    duration_ms = models.PositiveIntegerField("Длительность, мс", null=True, blank=True)

    utm_source = models.CharField("UTM source", max_length=255, blank=True, db_index=True)
    utm_medium = models.CharField("UTM medium", max_length=255, blank=True)
    utm_campaign = models.CharField("UTM campaign", max_length=255, blank=True)
    utm_term = models.CharField("UTM term", max_length=255, blank=True)
    utm_content = models.CharField("UTM content", max_length=255, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Посещение страницы"
        verbose_name_plural = "Посещения страниц"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("created_at", "path")),
            models.Index(fields=("created_at", "route_name")),
            models.Index(fields=("visitor", "created_at")),
            models.Index(fields=("profile", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.path} [{self.status_code}]"


class ProductView(models.Model):
    visitor = models.ForeignKey(
        "tracking.Visitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_views",
        verbose_name="Посетитель",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_views",
        verbose_name="Пользователь",
    )
    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_views",
        verbose_name="Профиль",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="product_views",
        verbose_name="Товар",
    )

    first_viewed_at = models.DateTimeField("Первый просмотр", auto_now_add=True)
    last_viewed_at = models.DateTimeField("Последний просмотр", auto_now=True, db_index=True)
    view_count = models.PositiveIntegerField("Количество просмотров", default=1)
    last_path = models.CharField("Последний путь", max_length=500, blank=True)

    class Meta:
        verbose_name = "История просмотра товара"
        verbose_name_plural = "История просмотров товаров"
        ordering = ("-last_viewed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "product"),
                condition=Q(profile__isnull=False),
                name="unique_product_view_per_profile",
            ),
            models.UniqueConstraint(
                fields=("visitor", "product"),
                condition=Q(profile__isnull=True) & Q(visitor__isnull=False),
                name="unique_guest_product_view_per_visitor",
            ),
        ]
        indexes = [
            models.Index(fields=("profile", "last_viewed_at")),
            models.Index(fields=("visitor", "last_viewed_at")),
            models.Index(fields=("product", "last_viewed_at")),
        ]

    def __str__(self) -> str:
        return f"{self.product} ({self.view_count})"


class UserEvent(models.Model):
    class EventType(models.TextChoices):
        PRODUCT_VIEW = "product_view", "Просмотр товара"

        CART_ADD = "cart_add", "Добавление в корзину"
        CART_UPDATE = "cart_update", "Изменение корзины"
        CART_REMOVE = "cart_remove", "Удаление из корзины"
        CART_CLEAR = "cart_clear", "Очистка корзины"

        FAVORITE_ADD = "favorite_add", "Добавление в избранное"
        FAVORITE_REMOVE = "favorite_remove", "Удаление из избранного"

        LEAD_CONTACT_CREATED = "lead_contact_created", "Создание обычной заявки"
        LEAD_PRODUCT_CREATED = "lead_product_created", "Создание заявки с товара"
        LEAD_CART_CREATED = "lead_cart_created", "Создание заявки из корзины"

        LOGIN = "login", "Вход"
        SIGNUP = "signup", "Регистрация"

    visitor = models.ForeignKey(
        "tracking.Visitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="Посетитель",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="Пользователь",
    )
    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="Профиль",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="Товар",
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="Заявка",
    )

    event_type = models.CharField("Тип события", max_length=50, choices=EventType.choices, db_index=True)
    path = models.CharField("Путь", max_length=500, blank=True)
    metadata = models.JSONField("Метаданные", default=dict, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Событие пользователя"
        verbose_name_plural = "События пользователей"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("created_at", "event_type")),
            models.Index(fields=("product", "created_at")),
            models.Index(fields=("profile", "created_at")),
            models.Index(fields=("visitor", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
