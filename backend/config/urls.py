"""Project routes."""

from django.contrib import admin
from django.urls import path

from .views import health
from reports.views import lottery_catalog, report_detail, reports
from stores.views import session, sign_in, sign_out

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/session/", session, name="session"),
    path("api/auth/login/", sign_in, name="login"),
    path("api/auth/logout/", sign_out, name="logout"),
    path("api/lottery/catalog/", lottery_catalog, name="lottery-catalog"),
    path("api/reports/", reports, name="reports"),
    path("api/reports/<int:report_id>/", report_detail, name="report-detail"),
]
