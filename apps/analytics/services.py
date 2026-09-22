import logging
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.leads.models import Lead

from .models import LeadScore, LeadScoringState
from .predictors import build_lead_features, score_lead_features

logger = logging.getLogger(__name__)
SCORING_STATES = ["missing", "pending", "ready", "error"]


class ScoringUnavailable(Exception):
    """A failed calculation; no internal exception details are sent to the client."""


class ScoringBusy(Exception):
    """Another worker owns the current request, or a newer request replaced it."""


def _to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def scoring_summary(lead):
    try:
        result = lead.score
    except ObjectDoesNotExist:
        result = None
    try:
        state = lead.scoring_state
    except ObjectDoesNotExist:
        state = None
    status = state.status if state else ("ready" if result else "missing")
    if status == "ready" and result is None:
        status = "missing"
    return {
        "state": status, "has_result": result is not None,
        "is_stale": result is not None and status in {"pending", "error"},
        "requested_revision": state.requested_revision if state else None,
        "completed_revision": state.completed_revision if state else None,
        "requested_at": state.requested_at if state else None,
        "started_at": state.started_at if state else None,
        "finished_at": state.finished_at if state else None,
        "error_code": (state.error_code or None) if state else None,
    }


def _queue_locked(lead):
    """Caller owns the lead lock, also used by calculation publication and CRM writes."""
    state, created = LeadScoringState.objects.get_or_create(lead=lead)
    if not created:
        state.requested_revision += 1
    state.status = LeadScoringState.Status.PENDING
    state.requested_at = timezone.now()
    state.started_at = state.finished_at = state.lease_expires_at = state.attempt_token = None
    state.error_code = ""
    state.save()
    return state


@transaction.atomic
def schedule_score_lead(lead_id: int):
    """Persist a request within the source transaction; never calculate in an HTTP callback."""
    lead = Lead.objects.select_for_update().filter(pk=lead_id).first()
    if lead is None:  # A LeadItem deletion may belong to a cascading lead deletion.
        return None
    return _queue_locked(lead)


def pending_scores(now=None):
    now = now or timezone.now()
    return LeadScoringState.objects.filter(status="pending").filter(
        Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now)
    ).order_by("requested_at", "lead_id")


def _begin_calculation(lead_id, force):
    with transaction.atomic():
        lead = Lead.objects.select_for_update().filter(pk=lead_id).first()
        if lead is None:
            return None
        state = _queue_locked(lead) if force else LeadScoringState.objects.filter(lead=lead).first()
        now = timezone.now()
        if state is None or state.status != "pending" or (state.lease_expires_at and state.lease_expires_at > now):
            raise ScoringBusy("Расчёт уже выполняется или запрос больше не ожидает обработки.")
        state.attempt_token = uuid.uuid4()
        state.started_at = now
        state.finished_at = None
        state.lease_expires_at = now + timedelta(seconds=settings.LEAD_SCORING_LEASE_SECONDS)
        state.save(update_fields=["attempt_token", "started_at", "finished_at", "lease_expires_at"])
        return state.requested_revision, state.attempt_token


def _current_attempt(lead_id, revision, token):
    # Always lock Lead before touching state: no lock is held during the calculation.
    lead = Lead.objects.select_for_update().filter(pk=lead_id).first()
    if lead is None:
        raise ScoringBusy("Заявка больше не существует.")
    state = LeadScoringState.objects.get(lead=lead)
    if state.requested_revision != revision or state.attempt_token != token or state.status != "pending":
        raise ScoringBusy("Результат устарел: появился другой запрос расчёта.")
    return state


def process_score_lead(lead_id: int, *, force=False):
    attempt = _begin_calculation(lead_id, force)
    if attempt is None:
        return None
    revision, token = attempt
    try:
        lead = Lead.objects.select_related("profile", "visitor").prefetch_related(
            "items", "items__product", "items__product__category"
        ).get(pk=lead_id)
        features = build_lead_features(lead)
        result = score_lead_features(features)
        defaults = {
            "score": _to_decimal(result["score"]), "priority": result["priority"],
            "model_name": "rule_based_lead_scoring", "model_version": "1.0",
            "features": features, "explanation": {"reasons": result["explanation"]},
        }
        with transaction.atomic():
            state = _current_attempt(lead_id, revision, token)
            score_obj, _ = LeadScore.objects.update_or_create(lead_id=lead_id, defaults=defaults)
            state.status = "ready"
            state.completed_revision = revision
            state.finished_at = timezone.now()
            state.lease_expires_at = None
            state.error_code = ""
            state.save(update_fields=["status", "completed_revision", "finished_at", "lease_expires_at", "error_code"])
        return score_obj
    except ScoringBusy:
        raise
    except Exception as exc:
        logger.exception("Failed to score lead %s", lead_id)
        with transaction.atomic():
            state = _current_attempt(lead_id, revision, token)
            state.status = "error"
            state.error_code = "calculation_failed"
            state.finished_at = timezone.now()
            state.lease_expires_at = None
            state.save(update_fields=["status", "error_code", "finished_at", "lease_expires_at"])
        raise ScoringUnavailable("Не удалось рассчитать оценку. Обработка заявки доступна.") from exc


def score_lead(lead: Lead) -> LeadScore:
    return score_lead_by_id(lead.pk)


def score_lead_by_id(lead_id: int):
    """Explicit synchronous recalculation for the existing API and management callers."""
    return process_score_lead(lead_id, force=True)
