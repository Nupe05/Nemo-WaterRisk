"""Public-facing views.

The free Water Risk Index is the lead magnet from the go-to-market plan:
publish it, and inbound interest tells you whether anyone will pay for the
full methodology before you build a checkout page.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import MonitoredSite, WaterRiskScore


def healthz(request):
    return JsonResponse({"ok": True})


def water_risk_index(request):
    """List of publicly-indexed sites with their latest risk score."""
    sites = MonitoredSite.objects.filter(is_public_index=True).select_related("watershed")
    out = []
    for site in sites:
        latest = (
            WaterRiskScore.objects.filter(watershed=site.watershed).order_by("-computed_at").first()
            if site.watershed_id
            else None
        )
        out.append(
            {
                "reference": site.reference,
                "name": site.name,
                "watershed": site.watershed.name if site.watershed_id else None,
                "risk_score": round(latest.score, 1) if latest else None,
                "as_of": latest.computed_at.isoformat() if latest else None,
            }
        )
    return JsonResponse({"count": len(out), "sites": out})


def water_risk_index_detail(request, site_ref):
    site = get_object_or_404(MonitoredSite, reference=site_ref, is_public_index=True)
    latest = (
        WaterRiskScore.objects.filter(watershed=site.watershed).order_by("-computed_at").first()
        if site.watershed_id
        else None
    )
    return JsonResponse(
        {
            "reference": site.reference,
            "name": site.name,
            "watershed": site.watershed.name if site.watershed_id else None,
            "risk_score": round(latest.score, 1) if latest else None,
            "components": latest.components if latest else {},
            "as_of": latest.computed_at.isoformat() if latest else None,
            "methodology": "USGS withdrawal + NOAA drought + EPA stress, weighted. See docs/ARCHITECTURE.md.",
        }
    )
