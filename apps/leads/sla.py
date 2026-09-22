"""SLA calculations and presentation. Existing cycles never consult current settings."""
from copy import deepcopy
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.analytics.models import LeadScore


def validate_deadlines(response_minutes, resolution_minutes):
    if (type(response_minutes) is not int or type(resolution_minutes) is not int
            or not 1 <= response_minutes <= resolution_minutes <= 525600):
        raise ValidationError("Сроки задаются в минутах: 1 <= ответ <= закрытие <= 525600.")


def validate_policy(default_priority, priority_overrides, warning_percent):
    if default_priority not in LeadScore.Priority.values:
        raise ValidationError({"default_priority": "Неизвестный приоритет."})
    if type(warning_percent) is not int or not 1 <= warning_percent <= 99:
        raise ValidationError({"warning_percent": "Укажите процент от 1 до 99."})
    if not isinstance(priority_overrides, dict) or set(priority_overrides) - set(LeadScore.Priority.values):
        raise ValidationError({"priority_overrides": "Ожидается объект с ключами low, medium или high."})
    for priority, rule in priority_overrides.items():
        if not isinstance(rule, dict) or set(rule) != {"response_minutes", "resolution_minutes"}:
            raise ValidationError({"priority_overrides": f"Для {priority} нужны response_minutes и resolution_minutes."})
        validate_deadlines(rule["response_minutes"], rule["resolution_minutes"])


def cycle_sla_fields(lead, policy, started_at):
    score = LeadScore.objects.filter(lead=lead).values("priority", "score", "predicted_at").first()
    has_score = score is not None and score["priority"] in LeadScore.Priority.values
    priority = score["priority"] if has_score else policy.default_priority
    source = "score" if has_score else "default"
    effective = policy.priority_overrides.get(priority, {
        "response_minutes": policy.response_minutes, "resolution_minutes": policy.resolution_minutes,
    })
    response_period = timedelta(minutes=effective["response_minutes"])
    resolution_period = timedelta(minutes=effective["resolution_minutes"])
    snapshot = {
        "policy_id": policy.pk, "version": policy.version,
        "response_minutes": policy.response_minutes, "resolution_minutes": policy.resolution_minutes,
        "default_priority": policy.default_priority, "priority_overrides": deepcopy(policy.priority_overrides),
        "warning_percent": policy.warning_percent, "response_basis": "outbound_attempt",
        "applied_priority": priority, "priority_source": source,
        "effective_response_minutes": effective["response_minutes"],
        "effective_resolution_minutes": effective["resolution_minutes"],
        "score": {"value": str(score["score"]), "priority": priority,
                  "predicted_at": score["predicted_at"].isoformat()} if has_score else None,
    }
    return {
        "priority": priority, "priority_source": source, "policy_snapshot": snapshot,
        "response_due_at": started_at + response_period,
        "resolution_due_at": started_at + resolution_period,
        "response_warning_at": started_at + response_period * policy.warning_percent / 100,
        "resolution_warning_at": started_at + resolution_period * policy.warning_percent / 100,
    }


def next_action_reminder_at(due_at, now):
    minutes = settings.CRM_NEXT_ACTION_REMINDER_MINUTES
    if type(minutes) is not int or minutes < 0:
        raise ValidationError("CRM_NEXT_ACTION_REMINDER_MINUTES должен быть неотрицательным целым числом.")
    return max(now, due_at - timedelta(minutes=minutes)) if minutes else None


def deadline_state(due_at, warning_at, fulfilled_at, closed_at, now):
    if due_at is None:
        return "not_configured"
    if fulfilled_at is not None:
        return "met" if fulfilled_at <= due_at else "breached"
    if closed_at is not None:
        return "breached" if closed_at > due_at else "closed"
    if now >= due_at:
        return "overdue"
    if warning_at is not None and now >= warning_at:
        return "warning"
    return "pending"


def latest_cycle(lead):
    cycles = getattr(lead, "_prefetched_objects_cache", {}).get("cycles")
    if cycles is not None:
        return max(cycles, key=lambda cycle: cycle.number, default=None)
    return lead.cycles.order_by("-number").first()


def sla_summary(lead, now=None):
    now = now or timezone.now()
    cycle = latest_cycle(lead)
    if cycle is None:
        return None
    return {
        "cycle_id": cycle.pk, "priority": cycle.priority or None,
        "priority_source": cycle.priority_source or None,
        "policy_version": cycle.policy_snapshot.get("version"),
        "response": {
            "due_at": cycle.response_due_at, "warning_at": cycle.response_warning_at,
            "fulfilled_at": cycle.first_response_at,
            "state": deadline_state(cycle.response_due_at, cycle.response_warning_at, cycle.first_response_at, cycle.ended_at, now),
        },
        "resolution": {
            "due_at": cycle.resolution_due_at, "warning_at": cycle.resolution_warning_at,
            "fulfilled_at": cycle.ended_at,
            "state": deadline_state(cycle.resolution_due_at, cycle.resolution_warning_at, cycle.ended_at, cycle.ended_at, now),
        },
    }


def next_action_summary(lead, now=None):
    now = now or timezone.now()
    state = deadline_state(lead.next_action_at, lead.next_action_remind_at, None, None, now)
    if lead.status in {"completed", "canceled"} and lead.next_action_at:
        state = "closed"
    return {
        "revision": lead.next_action_revision, "due_at": lead.next_action_at,
        "warning_at": lead.next_action_remind_at,
        "state": "not_scheduled" if state == "not_configured" else state,
    }


def overdue_cycles_filter(now):
    return Q(response_due_at__lte=now, first_response_at__isnull=True) | Q(resolution_due_at__lte=now)


def warning_cycles_filter(now):
    return Q(response_warning_at__lte=now, response_due_at__gt=now, first_response_at__isnull=True) | Q(
        resolution_warning_at__lte=now, resolution_due_at__gt=now,
    )
