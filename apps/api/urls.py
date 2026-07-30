from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.api.views import CategoryViewSet, ProductViewSet
from apps.leads.api.views import LeadViewSet

app_name = "api"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("leads", LeadViewSet, basename="lead")

urlpatterns = [
    path("", include(router.urls)),
]
