import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.leads.models import Lead

from .models import LeadScore
from .predictors import build_lead_features, score_lead_features

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def score_lead(lead: Lead) -> LeadScore:
    features = build_lead_features(lead)
    result = score_lead_features(features)

    score_obj, _ = LeadScore.objects.update_or_create(
        lead=lead,
        defaults={
            "score": _to_decimal(result["score"]),
            "priority": result["priority"],
            "model_name": "rule_based_lead_scoring",
            "model_version": "1.0",
            "features": features,
            "explanation": {"reasons": result["explanation"]},
        },
    )
    return score_obj


def score_lead_by_id(lead_id: int):
    try:
        lead = (
            Lead.objects.select_related("profile", "visitor")
            .prefetch_related("items", "items__product", "items__product__category")
            .get(pk=lead_id)
        )
    except Lead.DoesNotExist:
        return None

    return score_lead(lead)


def schedule_score_lead(lead_id: int) -> None:
    def _runner():
        try:
            score_lead_by_id(lead_id)
        except Exception as e:
            # ИСПРАВЛЕНО: Теперь мы увидим ошибку в логах
            logger.error(f"Failed to score lead {lead_id}: {e}")

    transaction.on_commit(_runner)
