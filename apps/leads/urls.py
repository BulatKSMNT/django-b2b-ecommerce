from django.urls import path

from . import views

app_name = "leads"

urlpatterns = [
    path("contact/", views.create_contact_lead_view, name="create_contact"),
    path("product/<int:product_id>/", views.create_product_lead_view, name="create_product"),
    path("cart/", views.create_cart_lead_view, name="create_cart"),
]
