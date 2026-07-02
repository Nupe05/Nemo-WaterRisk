from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Free public "Water Risk Index" — the lead magnet from the plan.
    path("", views.public_index, name="public-index"),
    path("site/<str:site_ref>/", views.public_detail, name="public-detail"),
    path("report/<str:site_ref>/", views.site_report, name="site-report"),
    path("subscribe/", views.subscribe, name="subscribe"),
    # JSON API for programmatic access.
    path("api/sites/", views.api_sites, name="api-sites"),
    path("api/sites/<str:site_ref>/", views.api_site_detail, name="api-site-detail"),
    path("healthz/", views.healthz, name="healthz"),
]
