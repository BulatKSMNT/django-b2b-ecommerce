from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("cart/clear/", views.cart_clear_view, name="cart_clear"),

    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/toggle/<int:product_id>/", views.favorite_toggle, name="favorite_toggle"),
]
