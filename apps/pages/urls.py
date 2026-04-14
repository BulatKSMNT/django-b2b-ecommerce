from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contacts/", views.contacts, name="contacts"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("personal-data/", views.personal_data, name="personal_data"),
    path("public-offer/", views.public_offer, name="public_offer"),
    path("delivery-payment/", views.delivery_payment, name="delivery_payment")
]
