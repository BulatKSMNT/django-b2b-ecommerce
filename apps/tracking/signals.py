from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.accounts.services import ACTIVE_PROFILE_SESSION_KEY, ensure_user_has_default_profile

from .models import UserEvent
from .services import merge_visitor_tracking_to_profile, record_event


@receiver(user_logged_in)
def attach_tracking_to_logged_user(sender, request, user, **kwargs):
    profile = ensure_user_has_default_profile(user)
    request.session[ACTIVE_PROFILE_SESSION_KEY] = profile.id

    merge_visitor_tracking_to_profile(request, profile)

    try:
        record_event(
            request,
            UserEvent.EventType.LOGIN,
            metadata={"user_id": user.id},
        )
    except Exception:
        pass
