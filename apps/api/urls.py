from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.api.views import CategoryViewSet, ProductViewSet
from apps.leads.api.views import LeadViewSet
from apps.leads.api.management_views import EmployeeViewSet, NotificationViewSet, SLAPolicyViewSet

app_name = "api"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("leads", LeadViewSet, basename="lead")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("sla-policies", SLAPolicyViewSet, basename="sla-policy")

urlpatterns = [
    path("crm/", include("apps.leads.api.crm.urls")),
    path("", include(router.urls)),
]
