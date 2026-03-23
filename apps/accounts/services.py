from __future__ import annotations

from django.db import transaction

from .models import Profile

ACTIVE_PROFILE_SESSION_KEY = "accounts_active_profile_id"


def ensure_user_has_default_profile(user) -> Profile:
    """
    Гарантирует, что у пользователя есть хотя бы один профиль
    и один из них помечен как профиль по умолчанию.
    """
    profiles = user.profiles.filter(is_active=True).order_by("id")

    default_profile = profiles.filter(is_default=True).first()
    if default_profile:
        return default_profile

    first_profile = profiles.first()
    if first_profile:
        first_profile.is_default = True
        first_profile.save(update_fields=["is_default"])
        return first_profile

    profile_name = user.get_full_name().strip() or user.username

    return Profile.objects.create(
        user=user,
        name=profile_name,
        profile_type=Profile.ProfileType.PERSONAL,
        is_default=True,
        is_active=True,
    )


def get_available_profiles(user):
    return user.profiles.filter(is_active=True).order_by("-is_default", "id")


def get_default_profile(user) -> Profile | None:
    if not user.is_authenticated:
        return None

    return ensure_user_has_default_profile(user)


def get_active_profile(request) -> Profile | None:
    if not request.user.is_authenticated:
        return None

    profile_id = request.session.get(ACTIVE_PROFILE_SESSION_KEY)
    available_profiles = get_available_profiles(request.user)

    if profile_id:
        profile = available_profiles.filter(id=profile_id).first()
        if profile:
            return profile

    default_profile = ensure_user_has_default_profile(request.user)
    request.session[ACTIVE_PROFILE_SESSION_KEY] = default_profile.id
    return default_profile


def set_active_profile(request, profile: Profile) -> None:
    if profile.user_id != request.user.id:
        raise ValueError("Нельзя установить чужой профиль как активный.")

    if not profile.is_active:
        raise ValueError("Нельзя установить неактивный профиль как активный.")

    request.session[ACTIVE_PROFILE_SESSION_KEY] = profile.id


@transaction.atomic
def make_profile_default(profile: Profile) -> None:
    Profile.objects.filter(user=profile.user, is_default=True).exclude(pk=profile.pk).update(is_default=False)

    if not profile.is_default:
        profile.is_default = True
        profile.save(update_fields=["is_default"])
