from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class Lead(models.Model):
    class Source(models.TextChoices):
        CONTACT = "contact", "Обычная форма"
        PRODUCT = "product", "Заявка с товара"
        CART = "cart", "Заявка из корзины"

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        ASSIGNED = "assigned", "Назначена"
        IN_PROGRESS = "in_progress", "В работе"
        CONTACTED = "contacted", "Контакт установлен"
        QUALIFIED = "qualified", "Квалифицирована"
        COMPLETED = "completed", "Успешно закрыта"
        CANCELED = "canceled", "Закрыта без успеха"

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="assigned_leads",
    )
    version = models.PositiveIntegerField(default=1)
    next_action = models.TextField(blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_action_revision = models.PositiveIntegerField(default=0)
    next_action_remind_at = models.DateTimeField(null=True, blank=True, db_index=True)

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


class SLAPolicy(models.Model):
    """Append-only versions; the highest version applies to new cycles only."""

    version = models.PositiveIntegerField(unique=True)
    response_minutes = models.PositiveIntegerField(default=240)
    resolution_minutes = models.PositiveIntegerField(default=1440)
    default_priority = models.CharField(
        max_length=20, default="medium",
        choices=[("low", "Низкий"), ("medium", "Средний"), ("high", "Высокий")],
    )
    priority_overrides = models.JSONField(default=dict, blank=True)
    warning_percent = models.PositiveSmallIntegerField(default=80)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version",)
        constraints = [
            models.CheckConstraint(condition=Q(response_minutes__gt=0), name="sla_response_positive"),
            models.CheckConstraint(
                condition=Q(resolution_minutes__gte=models.F("response_minutes")),
                name="sla_resolution_after_response",
            ),
            models.CheckConstraint(condition=Q(warning_percent__gte=1, warning_percent__lte=99), name="sla_warning_percent_range"),
        ]


class LeadHandlingCycle(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="cycles")
    number = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    policy = models.ForeignKey(SLAPolicy, null=True, blank=True, on_delete=models.PROTECT)
    response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_contact_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    response_warning_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolution_warning_at = models.DateTimeField(null=True, blank=True, db_index=True)
    priority = models.CharField(max_length=20, blank=True)
    priority_source = models.CharField(max_length=20, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    result = models.CharField(max_length=20, blank=True)
    result_description = models.TextField(blank=True)
    is_imported = models.BooleanField(default=False)

    class Meta:
        ordering = ("number",)
        constraints = [
            models.UniqueConstraint(fields=("lead", "number"), name="unique_lead_cycle_number"),
            models.UniqueConstraint(fields=("lead",), condition=Q(ended_at__isnull=True), name="one_open_lead_cycle"),
            models.CheckConstraint(condition=Q(ended_at__isnull=True) | Q(ended_at__gte=models.F("started_at")), name="cycle_end_after_start"),
        ]


class LeadComment(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="comments")
    cycle = models.ForeignKey(LeadHandlingCycle, on_delete=models.PROTECT, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")


class LeadInteraction(models.Model):
    class Channel(models.TextChoices):
        PHONE = "phone", "Телефон"
        EMAIL = "email", "Email"
        MESSENGER = "messenger", "Мессенджер"
        MEETING = "meeting", "Встреча"
        OTHER = "other", "Другое"

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Входящий"
        OUTBOUND = "outbound", "Исходящий"

    class Result(models.TextChoices):
        SUCCESS = "success", "Контакт состоялся"
        NO_ANSWER = "no_answer", "Нет ответа"
        FAILED = "failed", "Неудача"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="interactions")
    cycle = models.ForeignKey(LeadHandlingCycle, on_delete=models.PROTECT, related_name="interactions")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    result = models.CharField(max_length=20, choices=Result.choices)
    description = models.TextField()
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("occurred_at", "id")


class LeadEvent(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="history_events")
    cycle = models.ForeignKey(LeadHandlingCycle, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=40)
    data = models.JSONField(default=dict)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Kept on the audit event so action, receipt and history commit together.
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    response = models.JSONField(default=dict)
    reminder_revision = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("lead", "actor", "idempotency_key"), name="unique_lead_action_key"),
            models.UniqueConstraint(fields=("cycle", "kind"), condition=Q(kind__in=[
                "sla_response_warning", "sla_response_overdue", "sla_resolution_warning", "sla_resolution_overdue",
            ]), name="unique_cycle_sla_alert"),
            models.UniqueConstraint(fields=("lead", "kind", "reminder_revision"), condition=Q(kind__in=[
                "next_action_warning", "next_action_overdue",
            ]), name="unique_next_action_alert"),
            models.CheckConstraint(condition=~Q(kind__in=["next_action_warning", "next_action_overdue"]) | Q(reminder_revision__isnull=False), name="next_action_alert_has_revision"),
        ]


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lead_notifications")
    event = models.ForeignKey(LeadEvent, on_delete=models.CASCADE, related_name="notifications")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("recipient", "event"), name="unique_event_recipient")]
