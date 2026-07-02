"""Public-facing views for the free Water Risk Index.

The Index is the lead magnet from the go-to-market plan: publish it, and the
signups tell you whether anyone will pay for the full methodology before you
build a checkout page. Server-rendered HTML for shareability + a small JSON
API for programmatic use.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from scoring.bands import band
from scoring.model import WEIGHTS
from .models import Lead, MonitoredSite, WaterRiskScore

COMPONENT_LABELS = {
    "streamflow_deficit": "Streamflow deficit",
    "precip_deficit": "Precipitation deficit",
    "withdrawal_pressure": "Withdrawal pressure",
}


def healthz(request):
    return JsonResponse({"ok": True})


def _latest_score(site: MonitoredSite):
    if not site.watershed_id:
        return None
    return (
        WaterRiskScore.objects.filter(watershed=site.watershed).order_by("-computed_at").first()
    )


def _row(site: MonitoredSite) -> dict:
    latest = _latest_score(site)
    score = round(latest.score, 1) if latest else None
    label, color = band(score)
    return {
        "reference": site.reference,
        "name": site.name,
        "watershed": site.watershed.name if site.watershed_id else "—",
        "score": score,
        "band": label,
        "color": color,
        "as_of": latest.computed_at if latest else None,
        "components": latest.components if latest else {},
    }


# --- HTML pages -------------------------------------------------------------
def public_index(request):
    rows = [
        _row(s)
        for s in MonitoredSite.objects.filter(is_public_index=True).select_related("watershed")
    ]
    # Highest risk first; unscored sites sink to the bottom.
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    scored = [r for r in rows if r["score"] is not None]
    featured = scored[0] if scored else None
    context = {
        "rows": rows,
        "featured": featured,
        "subscribed": request.GET.get("subscribed") == "1",
    }
    return render(request, "public/index.html", context)


def public_detail(request, site_ref):
    site = get_object_or_404(MonitoredSite, reference=site_ref, is_public_index=True)
    row = _row(site)
    labels = {
        "streamflow_deficit": "Streamflow deficit",
        "precip_deficit": "Precipitation deficit",
        "withdrawal_pressure": "Withdrawal pressure",
    }
    components = [
        {"label": labels.get(k, k), "value": v}
        for k, v in (row["components"] or {}).items()
        if k in labels
    ]
    return render(request, "public/detail.html", {"row": row, "components": components})


@require_POST
def subscribe(request):
    email = (request.POST.get("email") or "").strip()
    if "@" in email and "." in email:
        Lead.objects.create(
            email=email,
            site_ref=(request.POST.get("site_ref") or "").strip(),
            source="water_risk_index",
        )
    return redirect("/?subscribed=1#signup")


# --- Premium report (staff-only, the sellable deliverable) ------------------
def _report_narrative(row: dict) -> str:
    name, band_label, ws = row["name"], row["band"], row["watershed"]
    if row["score"] is None:
        return (
            f"{name} has not yet been scored. A score will appear once hydrological "
            f"data has been ingested for its watershed."
        )
    comps = row["components"] or {}
    lines = [
        f"{name} carries a composite water-supply risk score of {row['score']} out of 100, "
        f"placing it in the {band_label} risk band."
    ]
    sf = comps.get("streamflow_deficit")
    if sf:
        lines.append(
            f"Current streamflow in the {ws} is running roughly {sf:.0f}% below its historical "
            f"median for this time of year, the primary driver of the score."
        )
    pd = comps.get("precip_deficit")
    if pd:
        lines.append(f"Recent precipitation is about {pd:.0f}% below normal for the watershed.")
    lines.append(
        "This assessment reflects the most recent public data and should be revisited as "
        "conditions change."
    )
    return " ".join(lines)


def _report_context(site: MonitoredSite) -> dict:
    row = _row(site)
    comps = [
        {"label": label, "value": row["components"][k], "weight": round(WEIGHTS.get(k, 0) * 100)}
        for k, label in COMPONENT_LABELS.items()
        if k in (row["components"] or {})
    ]
    return {"row": row, "components": comps, "narrative": _report_narrative(row), "today": timezone.now()}


@staff_member_required
def site_report(request, site_ref):
    """Premium one-page water-risk report for a site. Staff-only.

    Renders a print-ready HTML report; `?pdf=1` returns a server-generated PDF
    when WeasyPrint's system libraries are available, otherwise falls back to
    the HTML (which prints cleanly to PDF from the browser).
    """
    site = get_object_or_404(MonitoredSite, reference=site_ref)
    ctx = _report_context(site)

    if request.GET.get("pdf"):
        try:
            from weasyprint import HTML

            html = render_to_string("public/report.html", ctx, request=request)
            pdf = HTML(string=html).write_pdf()
            resp = HttpResponse(pdf, content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="water-risk-{site.reference}.pdf"'
            return resp
        except Exception:  # noqa: BLE001 - fall back to printable HTML
            pass
    return render(request, "public/report.html", ctx)


# --- JSON API ---------------------------------------------------------------
def api_sites(request):
    rows = [
        {
            "reference": r["reference"],
            "name": r["name"],
            "watershed": r["watershed"],
            "risk_score": r["score"],
            "band": r["band"],
            "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        }
        for r in (
            _row(s)
            for s in MonitoredSite.objects.filter(is_public_index=True).select_related("watershed")
        )
    ]
    return JsonResponse({"count": len(rows), "sites": rows})


def api_site_detail(request, site_ref):
    site = get_object_or_404(MonitoredSite, reference=site_ref, is_public_index=True)
    r = _row(site)
    return JsonResponse(
        {
            "reference": r["reference"],
            "name": r["name"],
            "watershed": r["watershed"],
            "risk_score": r["score"],
            "band": r["band"],
            "components": r["components"],
            "as_of": r["as_of"].isoformat() if r["as_of"] else None,
            "methodology": "USGS streamflow deficit + NOAA precip deficit + EPA withdrawal pressure.",
        }
    )
