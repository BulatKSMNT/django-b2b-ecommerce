from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.leads.models import Lead, LeadItem

from .services import schedule_score_lead


@receiver(post_save, sender=Lead)
def rescore_lead_after_save(sender, instance, **kwargs):
    if kwargs.get("raw"):
        return
    fields = kwargs.get("update_fields")
    # Handling changes do not affect the current rule-based scoring formula.
    scoring_fields = {"source", "profile", "profile_id", "visitor", "visitor_id", "email", "comment"}
    if fields is None or scoring_fields.intersection(fields):
        schedule_score_lead(instance.pk)


@receiver(post_save, sender=LeadItem)
def rescore_lead_after_item_save(sender, instance, **kwargs):
    if not kwargs.get("raw"):
        schedule_score_lead(instance.lead_id)


@receiver(post_delete, sender=LeadItem)
def rescore_lead_after_item_delete(sender, instance, **kwargs):
    origin = kwargs.get("origin")
    if isinstance(origin, Lead) or getattr(origin, "model", None) is Lead:
        return
    if instance.lead_id:
        schedule_score_lead(instance.lead_id)
