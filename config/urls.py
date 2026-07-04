from django.contrib import admin
from django.urls import path

from core import siting_views, views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Free public "Water Risk Index" — the lead magnet from the plan.
    path("", views.public_index, name="public-index"),
    path("site/<str:site_ref>/", views.public_detail, name="public-detail"),
    path("report/<str:site_ref>/", views.site_report, name="site-report"),
    path("subscribe/", views.subscribe, name="subscribe"),
    # Data-Center Siting Index — the proactive "where to build" product.
    path("siting/", siting_views.siting_index, name="siting-index"),
    path("siting/subscribe/", siting_views.siting_subscribe, name="siting-subscribe"),
    path("siting/<slug:slug>/", siting_views.siting_metro, name="siting-metro"),
    path("siting/report/<slug:slug>/", siting_views.siting_report, name="siting-report"),
    # SendGrid Inbound Parse webhook (append ?token=... — see docs/INBOUND_EMAIL.md).
    path("inbound/email/", views.inbound_email, name="inbound-email"),
    # JSON API for programmatic access.
    path("api/sites/", views.api_sites, name="api-sites"),
    path("api/sites/<str:site_ref>/", views.api_site_detail, name="api-site-detail"),
    path("healthz/", views.healthz, name="healthz"),
]
