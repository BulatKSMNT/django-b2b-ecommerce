from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.leads.models import Lead, LeadItem

from .services import schedule_score_lead


@receiver(post_save, sender=Lead)
def rescore_lead_after_save(sender, instance, **kwargs):
    schedule_score_lead(instance.pk)


@receiver(post_save, sender=LeadItem)
def rescore_lead_after_item_save(sender, instance, **kwargs):
    schedule_score_lead(instance.lead_id)


@receiver(post_delete, sender=LeadItem)
def rescore_lead_after_item_delete(sender, instance, **kwargs):
    if instance.lead_id:
        schedule_score_lead(instance.lead_id)
