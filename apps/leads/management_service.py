"""Transactional lead operations shared by HTTP, admin and management commands."""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.access import require_employee, require_supervisor
from apps.accounts.models import EmployeeProfile
from .access import require_lead_access
from .models import (
    Lead, LeadComment, LeadEvent, LeadHandlingCycle, LeadInteraction, Notification, SLAPolicy,
)
from .sla import cycle_sla_fields, next_action_reminder_at, validate_deadlines, validate_policy


class LeadConflict(Exception):
    """A stale version, reused key, or competing claim (HTTP 409)."""


CLOSED_STATUSES = {Lead.Status.COMPLETED, Lead.Status.CANCELED}
TRANSITIONS = {
    Lead.Status.ASSIGNED: Lead.Status.IN_PROGRESS,
    Lead.Status.IN_PROGRESS: Lead.Status.CONTACTED,
    Lead.Status.CONTACTED: Lead.Status.QUALIFIED,
}


def _text(value, field, limit=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError({field: f"Непустой текст, не более {limit} символов."})
    return value.strip()


def _date(value, field):
    from datetime import datetime
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValidationError({field: "Нужны дата и время с часовым поясом."})
    return value


def _cycle(lead):
    cycle = lead.cycles.filter(ended_at__isnull=True).first()
    if cycle is None:
        raise ValidationError("У заявки нет открытого цикла обработки.")
    return cycle


def allowed_status_transitions(lead, cycle):
    """Shared by mutation validation and the CRM card's available actions."""
    if lead.status in CLOSED_STATUSES or cycle is None:
        return []
    transitions = [Lead.Status.CANCELED]
    target = TRANSITIONS.get(lead.status)
    if lead.assignee_id and target:
        if target != Lead.Status.CONTACTED or cycle.interactions.filter(result="success").exists():
            transitions.insert(0, target)
    if lead.status == Lead.Status.QUALIFIED:
        transitions.insert(0, Lead.Status.COMPLETED)
    return transitions


def _start_cycle(lead, now):
    policy = SLAPolicy.objects.order_by("-version").first()
    if policy is None:
        raise ValidationError("Не настроена SLA-политика. Примените миграции.")
    number = (lead.cycles.aggregate(number=Max("number"))["number"] or 0) + 1
    return LeadHandlingCycle.objects.create(
        lead=lead, number=number, started_at=now, policy=policy,
        **cycle_sla_fields(lead, policy, now),
    )


def initialize_lead(lead, actor=None):
    """Called inside the creation transaction; no notifications for public submissions."""
    cycle = _start_cycle(lead, lead.created_at)
    LeadEvent.objects.create(
        lead=lead, cycle=cycle, actor=actor, kind="created", version=lead.version,
        data={"source": lead.source},
    )
    return lead


def _assignee(user_id):
    # Employee updates acquire this same row lock before changing availability.
    employee = EmployeeProfile.objects.select_for_update().filter(
        user_id=user_id, is_active=True, is_available=True, user__is_active=True
    ).first()
    if employee is None:
        raise ValidationError({"assignee_id": "Сотрудник не доступен для назначения."})
    return employee.user_id


def _notify(event, user_ids):
    recipients = EmployeeProfile.objects.filter(
        user_id__in={pk for pk in user_ids if pk}, is_active=True, user__is_active=True
    ).values_list("user_id", flat=True)
    Notification.objects.bulk_create([
        Notification(recipient_id=pk, event=event) for pk in recipients
        if pk != event.actor_id
    ])


def _mutate(lead, actor, operation, data, now):
    old_assignee = lead.assignee_id
    details = {"from_status": lead.status, "from_assignee_id": old_assignee}
    resource_id = None
    if operation in {"claim", "assign"}:
        if lead.status in CLOSED_STATUSES:
            raise ValidationError("Закрытую заявку сначала нужно открыть повторно.")
        if operation == "claim":
            if lead.assignee_id is not None or lead.status != Lead.Status.NEW:
                raise LeadConflict("Заявка уже назначена или не находится в новой очереди.")
            target = actor.pk
        else:
            require_supervisor(actor)
            target = data["assignee_id"]
        lead.assignee_id = _assignee(target)
        if old_assignee == lead.assignee_id:
            raise ValidationError("Этот сотрудник уже отвечает за заявку.")
        if lead.status == Lead.Status.NEW:
            lead.status = Lead.Status.ASSIGNED
        cycle = _cycle(lead)
    elif operation == "reopen":
        if lead.status not in CLOSED_STATUSES:
            raise ValidationError("Повторно открыть можно только закрытую заявку.")
        details["reason"] = _text(data.get("reason"), "reason")
        # Preserve ownership even if unavailable; a supervisor can reassign the open cycle.
        cycle = _start_cycle(lead, now)
        lead.status = Lead.Status.ASSIGNED if lead.assignee_id else Lead.Status.NEW
        lead.processed_by = None
        lead.processed_at = None
        lead.next_action = ""
        lead.next_action_at = None
        lead.next_action_remind_at = None
    else:
        if lead.status in CLOSED_STATUSES:
            raise ValidationError("Заявка закрыта; сначала откройте новый цикл.")
        cycle = _cycle(lead)
        if operation == "change_status":
            target = data["status"]
            if target in CLOSED_STATUSES or target not in allowed_status_transitions(lead, cycle):
                raise ValidationError({"status": "Недопустимый переход статуса."})
            lead.status = target
        elif operation == "close":
            target = data["status"]
            if target not in CLOSED_STATUSES:
                raise ValidationError({"status": "Ожидается completed или canceled."})
            if target not in allowed_status_transitions(lead, cycle):
                raise ValidationError({"status": "Успешное закрытие доступно после квалификации."})
            result = _text(data.get("result"), "result")
            cycle.result = target
            cycle.result_description = result
            cycle.ended_at = now
            cycle.save(update_fields=["result", "result_description", "ended_at"])
            lead.status = target
            lead.processed_by = actor
            lead.processed_at = now
            lead.next_action = ""
            lead.next_action_at = None
            lead.next_action_remind_at = None
            details["result"] = result
        elif operation == "add_comment":
            obj = LeadComment.objects.create(
                lead=lead, cycle=cycle, author=actor, text=_text(data.get("text"), "text")
            )
            resource_id = obj.pk
        elif operation == "register_interaction":
            for field, choices in (("channel", LeadInteraction.Channel), ("direction", LeadInteraction.Direction), ("result", LeadInteraction.Result)):
                if data.get(field) not in choices.values:
                    raise ValidationError({field: "Недопустимое значение."})
            occurred_at = _date(data.get("occurred_at") or now, "occurred_at")
            if occurred_at > now or occurred_at < cycle.started_at:
                raise ValidationError({"occurred_at": "Контакт должен быть в пределах текущего цикла и не в будущем."})
            obj = LeadInteraction.objects.create(
                lead=lead, cycle=cycle, author=actor, channel=data["channel"],
                direction=data["direction"], result=data["result"],
                description=_text(data.get("description"), "description"), occurred_at=occurred_at,
            )
            resource_id = obj.pk
            if obj.direction == "outbound" and (cycle.first_response_at is None or occurred_at < cycle.first_response_at):
                cycle.first_response_at = occurred_at
                cycle.save(update_fields=["first_response_at"])
            if obj.result == "success" and (cycle.first_contact_at is None or occurred_at < cycle.first_contact_at):
                cycle.first_contact_at = occurred_at
                cycle.save(update_fields=["first_contact_at"])
        elif operation == "set_next_action":
            lead.next_action = _text(data.get("next_action"), "next_action")
            lead.next_action_at = _date(data.get("next_action_at"), "next_action_at")
            if lead.next_action_at <= now:
                raise ValidationError({"next_action_at": "Укажите время в будущем."})
            lead.next_action_revision += 1
            lead.next_action_remind_at = next_action_reminder_at(lead.next_action_at, now)
            details.update(
                next_action=lead.next_action, next_action_at=lead.next_action_at.isoformat(),
                revision=lead.next_action_revision,
                remind_at=lead.next_action_remind_at.isoformat() if lead.next_action_remind_at else None,
            )
        else:
            raise ValidationError("Неизвестная операция.")
    details.update(to_status=lead.status, to_assignee_id=lead.assignee_id)
    if resource_id:
        details["resource_id"] = resource_id
    return cycle, details, resource_id, old_assignee


@transaction.atomic
def execute_operation(*, lead_id, actor, operation, expected_version=None, idempotency_key, **data):
    require_employee(actor)
    key = _text(idempotency_key, "idempotency_key", 128)
    lead = Lead.objects.select_for_update().get(pk=lead_id)
    # Authorization is checked on the locked current state, including on retries.
    if operation == "assign":
        require_supervisor(actor)
    elif operation == "claim":
        pass  # The limited queue deliberately permits claiming an unassigned NEW lead.
    else:
        require_lead_access(actor, lead)
    fingerprint = hashlib.sha256(json.dumps(
        {"operation": operation, "expected_version": expected_version, "data": data},
        cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    previous = LeadEvent.objects.filter(lead=lead, actor=actor, idempotency_key=key).first()
    if previous:
        if previous.request_hash != fingerprint:
            raise LeadConflict("Ключ идемпотентности уже использован для другого запроса.")
        # A claim receipt must not bypass loss of access after reassignment.
        require_lead_access(actor, lead)
        return previous.response
    if expected_version is None and operation != "claim":
        raise ValidationError({"expected_version": "Обязательное поле."})
    if expected_version is not None:
        if type(expected_version) is not int or expected_version < 1:
            raise ValidationError({"expected_version": "Ожидается положительное целое число."})
        if lead.version != expected_version:
            raise LeadConflict(f"Заявка изменена. Текущая версия: {lead.version}.")
    cycle, details, resource_id, old_assignee = _mutate(lead, actor, operation, data, timezone.now())
    lead.version += 1
    lead.save(update_fields=[
        "assignee", "status", "version", "next_action", "next_action_at",
        "next_action_revision", "next_action_remind_at",
        "processed_by", "processed_at", "updated_at",
    ])
    event = LeadEvent.objects.create(
        lead=lead, cycle=cycle, actor=actor, kind=operation, data=details,
        version=lead.version, idempotency_key=key, request_hash=fingerprint,
    )
    response = {
        "lead_id": lead.pk, "version": lead.version, "status": lead.status,
        "assignee_id": lead.assignee_id, "cycle_id": cycle.pk,
        "event_id": event.pk, "resource_id": resource_id,
    }
    event.response = response
    event.save(update_fields=["response"])
    _notify(event, [lead.assignee_id, old_assignee])
    return response


def claim_lead(**kwargs):
    return execute_operation(operation="claim", **kwargs)


def assign_lead(**kwargs):
    return execute_operation(operation="assign", **kwargs)


def change_status(**kwargs):
    return execute_operation(operation="change_status", **kwargs)


def add_comment(**kwargs):
    return execute_operation(operation="add_comment", **kwargs)


def register_interaction(**kwargs):
    return execute_operation(operation="register_interaction", **kwargs)


def set_next_action(**kwargs):
    return execute_operation(operation="set_next_action", **kwargs)


def close_lead(**kwargs):
    return execute_operation(operation="close", **kwargs)


def reopen_lead(**kwargs):
    return execute_operation(operation="reopen", **kwargs)


@transaction.atomic
def create_sla_policy(*, actor, response_minutes, resolution_minutes, default_priority=None,
                      priority_overrides=None, warning_percent=None):
    require_supervisor(actor)
    # Every writer locks the permanent first policy, even as new versions are appended.
    SLAPolicy.objects.select_for_update().get(version=1)
    previous = SLAPolicy.objects.order_by("-version").first()
    default_priority = previous.default_priority if default_priority is None else default_priority
    warning_percent = previous.warning_percent if warning_percent is None else warning_percent
    priority_overrides = {} if priority_overrides is None else priority_overrides
    validate_deadlines(response_minutes, resolution_minutes)
    validate_policy(default_priority, priority_overrides, warning_percent)
    version = previous.version + 1
    return SLAPolicy.objects.create(
        version=version, response_minutes=response_minutes,
        resolution_minutes=resolution_minutes, created_by=actor,
        default_priority=default_priority, priority_overrides=priority_overrides, warning_percent=warning_percent,
    )


@transaction.atomic
def check_lead_sla(lead_id, now=None):
    """One warning/overdue event per SLA deadline or scheduled-action revision."""
    now = now or timezone.now()
    lead = Lead.objects.select_for_update().get(pk=lead_id)
    if lead.status in CLOSED_STATUSES:
        return 0
    cycle = _cycle(lead)
    pending = []
    for name, due_at, warning_at, fulfilled in (
        ("sla_response", cycle.response_due_at, cycle.response_warning_at, cycle.first_response_at is not None),
        ("sla_resolution", cycle.resolution_due_at, cycle.resolution_warning_at, False),
        ("next_action", lead.next_action_at, lead.next_action_remind_at, False),
    ):
        if due_at is None or fulfilled:
            continue
        if now >= due_at:
            pending.append((name + "_overdue", due_at, warning_at))
        elif warning_at is not None and now >= warning_at:
            # Don't backfill a warning after the deadline if cron missed its window.
            pending.append((name + "_warning", due_at, warning_at))
    count = 0
    for kind, due_at, warning_at in pending:
        is_next_action = kind.startswith("next_action_")
        lookup = {"lead": lead, "kind": kind, "reminder_revision": lead.next_action_revision} if is_next_action else {"cycle": cycle, "kind": kind}
        event, created = LeadEvent.objects.get_or_create(
            **lookup,
            defaults={
                "lead": lead, "cycle": cycle, "version": lead.version,
                "data": {"checked_at": now.isoformat(), "due_at": due_at.isoformat(),
                         "warning_at": warning_at.isoformat() if warning_at else None,
                         **({"revision": lead.next_action_revision} if is_next_action else {})},
            },
        )
        if created:
            recipients = [lead.assignee_id]
            if not is_next_action:
                recipients += list(EmployeeProfile.objects.exclude(role="manager").values_list("user_id", flat=True))
            elif lead.assignee_id is None:
                recipients += list(EmployeeProfile.objects.exclude(role="manager").values_list("user_id", flat=True))
            _notify(event, recipients)
            count += 1
    return count


@transaction.atomic
def mark_notification_read(*, actor, notification_id):
    require_employee(actor)
    notification = Notification.objects.select_related("event").get(
        pk=notification_id, recipient=actor,
    )
    # Share the lead lock with reassignment before checking current access.
    lead = Lead.objects.select_for_update().get(pk=notification.event.lead_id)
    require_lead_access(actor, lead)
    Notification.objects.filter(pk=notification.pk, read_at__isnull=True).update(read_at=timezone.now())
    notification.refresh_from_db()
    return notification
