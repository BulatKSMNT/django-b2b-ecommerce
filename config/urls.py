from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.analytics.views import admin_analytics_dashboard

urlpatterns = [
    path("admin/analytics/dashboard/", admin.site.admin_view(admin_analytics_dashboard), name="admin_analytics_dashboard"),
    path("admin/", admin.site.urls),

    path("", include(("apps.pages.urls", "pages"), namespace="pages")),
    path("catalog/", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("accounts/", include("apps.accounts.auth_urls")),
    path("", include(("apps.shop.urls", "shop"), namespace="shop")),
    path("leads/", include(("apps.leads.urls", "leads"), namespace="leads")),
    path("", include(("apps.tracking.urls", "tracking"), namespace="tracking")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
