from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Free public "Water Risk Index" lookup — the lead-magnet from the plan.
    path("index/", views.water_risk_index, name="water-risk-index"),
    path("index/<str:site_ref>/", views.water_risk_index_detail, name="water-risk-index-detail"),
    path("healthz/", views.healthz, name="healthz"),
]
