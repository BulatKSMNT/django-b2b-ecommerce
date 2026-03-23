from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.accounts.services import ACTIVE_PROFILE_SESSION_KEY, ensure_user_has_default_profile

from .services import merge_session_shop_state_to_profile


@receiver(user_logged_in)
def merge_guest_shop_state_after_login(sender, request, user, **kwargs):
    profile = ensure_user_has_default_profile(user)
    request.session[ACTIVE_PROFILE_SESSION_KEY] = profile.id
    merge_session_shop_state_to_profile(request, profile)
