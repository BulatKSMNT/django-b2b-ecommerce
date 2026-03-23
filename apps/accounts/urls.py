from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("profiles/", views.profile_list, name="profile_list"),
    path("profiles/create/", views.profile_create, name="profile_create"),
    path("profiles/<int:pk>/edit/", views.profile_update, name="profile_update"),
    path("profiles/<int:pk>/switch/", views.profile_switch, name="profile_switch"),
    path("profiles/<int:pk>/make-default/", views.profile_make_default, name="profile_make_default"),
]
