from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.tracking.models import UserEvent
from apps.tracking.services import record_event

from .forms import ProfileForm, UserRegistrationForm
from .models import Profile
from .services import get_available_profiles, make_profile_default, set_active_profile


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = UserRegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)

        record_event(
            request,
            UserEvent.EventType.SIGNUP,
            metadata={"user_id": user.id},
        )

        messages.success(request, "Регистрация прошла успешно.")
        return redirect("accounts:dashboard")

    return render(request, "accounts/signup.html", {"form": form})


@login_required
def dashboard(request):
    context = {
        "profile_count": request.user.profiles.filter(is_active=True).count(),
        "breadcrumbs": [
            {"title": "Главная", "url": reverse("pages:home")},
            {"title": "Личный кабинет", "url": None},
        ],
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile_list(request):
    profiles = get_available_profiles(request.user)
    return render(
        request,
        "accounts/profile_list.html",
        {
            "profiles": profiles,
            "breadcrumbs": [
                {"title": "Главная", "url": reverse("pages:home")},
                {"title": "Личный кабинет", "url": reverse("accounts:dashboard")},
                {"title": "Профили", "url": None},
            ],
        },
    )


@login_required
def profile_create(request):
    form = ProfileForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.user = request.user
        profile.is_active = True

        has_profiles = request.user.profiles.filter(is_active=True).exists()
        if not has_profiles:
            profile.is_default = True

        profile.save()
        set_active_profile(request, profile)

        messages.success(request, "Профиль создан.")
        return redirect("accounts:profile_list")

    return render(
        request,
        "accounts/profile_form.html",
        {
            "form": form,
            "page_title": "Создать профиль",
            "submit_text": "Создать",
            "breadcrumbs": [
                {"title": "Главная", "url": reverse("pages:home")},
                {"title": "Личный кабинет", "url": reverse("accounts:dashboard")},
                {"title": "Профили", "url": reverse("accounts:profile_list")},
                {"title": "Создать профиль", "url": None},
            ],
        },
    )


@login_required
def profile_update(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)

    form = ProfileForm(request.POST or None, instance=profile)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль обновлён.")
        return redirect("accounts:profile_list")

    return render(
        request,
        "accounts/profile_form.html",
        {
            "form": form,
            "profile": profile,
            "page_title": "Редактировать профиль",
            "submit_text": "Сохранить",
            "breadcrumbs": [
                {"title": "Главная", "url": reverse("pages:home")},
                {"title": "Личный кабинет", "url": reverse("accounts:dashboard")},
                {"title": "Профили", "url": reverse("accounts:profile_list")},
                {"title": str(profile), "url": None},
            ],
        },
    )


@require_POST
@login_required
def profile_switch(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user, is_active=True)
    set_active_profile(request, profile)
    messages.success(request, f"Активный профиль: {profile.name}")

    next_url = request.POST.get("next") or reverse("accounts:profile_list")
    return redirect(next_url)


@require_POST
@login_required
def profile_make_default(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user, is_active=True)
    make_profile_default(profile)
    messages.success(request, f"Профиль «{profile.name}» назначен основным.")

    next_url = request.POST.get("next") or reverse("accounts:profile_list")
    return redirect(next_url)
