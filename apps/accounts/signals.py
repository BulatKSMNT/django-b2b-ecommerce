from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .services import ensure_user_has_default_profile


@receiver(post_save, sender=User)
def create_default_profile(sender, instance, created, **kwargs):
    if created:
        ensure_user_has_default_profile(instance)
