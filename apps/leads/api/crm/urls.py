from django.urls import include, path, re_path
from rest_framework.routers import SimpleRouter

from .base import CRMNotFoundView
from .views import (
    CRMAssignableView, CRMDashboardView, CRMDictionariesView, CRMLeadViewSet,
    CRMMeView, CRMNotificationViewSet, CRMQueueView, CRMSLAPolicyViewSet, CRMTeamView,
)

app_name = "crm"
router = SimpleRouter()
router.register("leads", CRMLeadViewSet, basename="lead")
router.register("notifications", CRMNotificationViewSet, basename="notification")
router.register("sla-policies", CRMSLAPolicyViewSet, basename="sla-policy")

urlpatterns = [
    path("me/", CRMMeView.as_view(), name="me"),
    path("dashboard/", CRMDashboardView.as_view(), name="dashboard"),
    path("queue/", CRMQueueView.as_view(), name="queue"),
    path("team/", CRMTeamView.as_view(), name="team"),
    path("employees/assignable/", CRMAssignableView.as_view(), name="assignable"),
    path("dictionaries/", CRMDictionariesView.as_view(), name="dictionaries"),
    path("", include(router.urls)),
    re_path(r"^.*$", CRMNotFoundView.as_view()),
]
