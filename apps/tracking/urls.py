from django.urls import path

from . import views

app_name = "tracking"

urlpatterns = [
    path("history/", views.history, name="history"),
]
