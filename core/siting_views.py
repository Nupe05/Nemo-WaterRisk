"""Public-facing views for the Data-Center Siting Index (the "where to build"
product), plus the shared report-context builder used by both the staff report
view and the approval-gated email handler.

Monetization mirrors the water index: a free public teaser ranks metros and
shows the three headline legs (water / power / hazard); the full county-level
breakdown is the paid deliverable, unlocked by a signup that drops an
approval-gated SEND_SITING_REPORT into the queue.
"""
from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from scoring.siting import grade_for
from .models import ApprovalItem, Lead, ReadRequest, SitingScore

LEG_LABELS = {
    "water": "Water headroom",
    "power": "Power availability",
    "hazard": "Hazard safety",
}


def _latest_scores() -> list[SitingScore]:
    """Most recent SitingScore per location (one row per county)."""
    seen: dict[int, SitingScore] = {}
    for s in SitingScore.objects.select_related("location").order_by("-computed_at"):
        if s.location_id not in seen:
            seen[s.location_id] = s
    return list(seen.values())


def _avg(scores, attr) -> float:
    return round(sum(getattr(s, attr) for s in scores) / len(scores), 1) if scores else 0.0


def _metro_rollup(public_only: bool = True) -> list[dict]:
    """Roll county scores up to a ranked list of metro markets (best first)."""
    buckets: dict[str, list[SitingScore]] = {}
    for s in _latest_scores():
        if public_only and not s.location.is_public_teaser:
            continue
        buckets.setdefault(s.location.metro, []).append(s)

    rollups = []
    for metro, cs in buckets.items():
        cs.sort(key=lambda s: s.suitability, reverse=True)
        comp = _avg(cs, "suitability")
        label, color = grade_for(comp)
        best = cs[0]
        rollups.append({
            "metro": metro,
            "slug": slugify(metro),
            "suitability": comp,
            "grade": label,
            "color": color,
            "water": _avg(cs, "water"),
            "power": _avg(cs, "power"),
            "hazard": _avg(cs, "hazard"),
            "county_count": len(cs),
            "best_county": best.location.county_name,
            "power_region": best.detail.get("power_region"),
            "power_years": best.detail.get("power_years"),
            "counties": cs,
        })
    rollups.sort(key=lambda r: r["suitability"], reverse=True)
    for i, r in enumerate(rollups, start=1):
        r["rank"] = i
    return rollups


def _find_metro(slug: str, public_only: bool = True) -> dict | None:
    for r in _metro_rollup(public_only=public_only):
        if r["slug"] == slug:
            return r
    return None


def current_metro_score(metro_name: str) -> dict | None:
    """Latest rolled-up suitability + grade for a metro (by name or slug), or
    None if unknown/unscored. Used by the monitoring sweep."""
    m = _find_metro(slugify(metro_name), public_only=False)
    if m is None:
        return None
    return {"metro": m["metro"], "score": m["suitability"], "band": m["grade"]}


# --- Public teaser ----------------------------------------------------------
def siting_index(request):
    metros = _metro_rollup(public_only=True)
    context = {
        "metros": metros,
        "leader": metros[0] if metros else None,
        "subscribed": request.GET.get("subscribed") == "1",
    }
    return render(request, "public/siting_index.html", context)


def siting_metro(request, slug):
    metro = _find_metro(slug, public_only=True)
    if metro is None:
        return redirect("/siting/")
    legs = [
        {"key": k, "label": LEG_LABELS[k], "value": metro[k]}
        for k in ("power", "water", "hazard")
    ]
    return render(request, "public/siting_metro.html", {"m": metro, "legs": legs})


@require_POST
def siting_subscribe(request):
    """Signup on the siting index: capture the lead and queue an approval-gated
    report send for the requested metro (the revenue connector)."""
    email = (request.POST.get("email") or "").strip()
    metro = (request.POST.get("metro") or "").strip()
    if "@" in email and "." in email:
        lead = Lead.objects.create(email=email, site_ref=metro, source="siting_index")
        if metro and _find_metro(slugify(metro), public_only=False):
            ApprovalItem.objects.create(
                content_type="siting_report",
                action_type=ApprovalItem.ActionType.SEND_SITING_REPORT,
                state=ApprovalItem.State.PENDING,
                summary=f"Send {metro} siting report to {lead.email}",
                payload={"to": lead.email, "metro": metro, "lead_id": lead.id},
            )
    dest = f"/siting/{slugify(metro)}/" if metro else "/siting/"
    return redirect(f"{dest}?subscribed=1#unlock")


# --- Paid report (staff-only render; also emailed on approval) --------------
def _leg_rows(metro: dict) -> list[dict]:
    weights = {}
    if metro["counties"]:
        weights = metro["counties"][0].detail.get("weights", {})
    return [
        {
            "key": k,
            "label": LEG_LABELS[k],
            "value": metro[k],
            "weight": round(weights.get(k, 0) * 100),
        }
        for k in ("power", "water", "hazard")
    ]


def _siting_narrative(metro: dict) -> str:
    legs = {"power availability": metro["power"], "water headroom": metro["water"],
            "hazard safety": metro["hazard"]}
    strongest = max(legs, key=legs.get)
    weakest = min(legs, key=legs.get)
    lines = [
        f"{metro['metro']} earns a composite data-center suitability score of "
        f"{metro['suitability']} out of 100 ({metro['grade']}), ranking #{metro['rank']} "
        f"among the markets in this index.",
        f"Its strongest leg is {strongest} ({legs[strongest]:.0f}/100); its binding "
        f"constraint is {weakest} ({legs[weakest]:.0f}/100).",
    ]
    if metro.get("power_region"):
        lines.append(
            f"Power sits in the {metro['power_region']} interconnection region, with a "
            f"typical large-load energize time of roughly {metro['power_years']} years."
        )
    lines.append(
        "Scores are relative rankings across candidate markets, built from public USGS/"
        "drought water data, ISO interconnection-queue data, and FEMA National Risk Index "
        "hazard data. Use them to shortlist, then confirm with site-specific utility and "
        "water-rights diligence."
    )
    return " ".join(lines)


def siting_report_context(metro_name: str) -> dict | None:
    """Full report context for a metro, or None if unknown/unscored.

    Shared by the staff report view and the SEND_SITING_REPORT email handler.
    Accepts either the metro display name or its slug.
    """
    metro = _find_metro(slugify(metro_name), public_only=False)
    if metro is None:
        return None
    counties = [
        {
            "name": s.location.county_name,
            "market_status": s.location.market_status,
            "suitability": round(s.suitability, 1),
            "grade": s.grade,
            "grade_color": grade_for(s.suitability)[1],
            "water": round(s.water),
            "power": round(s.power),
            "hazard": round(s.hazard),
            "top_hazards": ", ".join(s.detail.get("top_hazards", []) or ["—"]),
            "nri_rating": s.detail.get("nri_risk_rating") or "—",
            "water_source": s.detail.get("water_source") or "structural",
        }
        for s in metro["counties"]
    ]
    return {
        "m": metro,
        "legs": _leg_rows(metro),
        "counties": counties,
        "narrative": _siting_narrative(metro),
        "today": timezone.now(),
    }


@staff_member_required
def siting_report(request, slug):
    ctx = siting_report_context(slug)
    if ctx is None:
        return redirect("/siting/")
    if request.GET.get("pdf"):
        try:
            from weasyprint import HTML

            html = render_to_string("public/siting_report.html", ctx, request=request)
            pdf = HTML(string=html).write_pdf()
            resp = HttpResponse(pdf, content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="siting-{slug}.pdf"'
            return resp
        except Exception:  # noqa: BLE001 - fall back to printable HTML
            pass
    return render(request, "public/siting_report.html", ctx)


# --- The State of Data-Center Water Risk (public, citable, self-updating) ----
def state_of_context() -> dict:
    """Live context for the public 'State of Data-Center Water Risk' report.

    Everything is derived from the latest SitingScore rollups, so the page and
    its findings update automatically each time score_siting runs. Findings that
    name a rank or a market are computed, not hard-coded, so they stay true as
    the numbers move.
    """
    metros = _metro_rollup(public_only=False)
    if not metros:
        return {"has_data": False, "today": timezone.now()}

    n = len(metros)
    least_water = sorted(metros, key=lambda m: m["water"])[:5]
    most_water = sorted(metros, key=lambda m: m["water"], reverse=True)[:5]
    # Pre-zipped rows for the side-by-side water table (templates can't index).
    water_pairs = [{"most": mo, "least": le} for mo, le in zip(most_water, least_water)]
    # The flagship market (largest existing cluster) — Northern Virginia.
    flagship = next((m for m in metros if "Virginia" in m["metro"]), None)
    # Data freshness.
    latest = SitingScore.objects.order_by("-computed_at").first()
    return {
        "has_data": True,
        "metros": metros,
        "count": n,
        "leader": metros[0],
        "least_water": least_water,
        "most_water": most_water,
        "water_pairs": water_pairs,
        "flagship": flagship,
        "as_of": latest.computed_at if latest else None,
        "today": timezone.now(),
    }


def state_of_report(request):
    """Public, permanent home of the report. Citable URL; self-updating.

    `?pdf=1` returns a server-generated PDF when WeasyPrint is available, else
    the print-clean HTML (which prints cleanly to PDF from the browser)."""
    ctx = state_of_context()
    if request.GET.get("pdf") and ctx.get("has_data"):
        try:
            from weasyprint import HTML

            html = render_to_string("public/report_index.html", ctx, request=request)
            pdf = HTML(string=html).write_pdf()
            resp = HttpResponse(pdf, content_type="application/pdf")
            resp["Content-Disposition"] = 'attachment; filename="state-of-data-center-water-risk.pdf"'
            return resp
        except Exception:  # noqa: BLE001 - fall back to printable HTML
            import logging

            logging.getLogger("nemo.web").exception("weasyprint_pdf_failed")
    return render(request, "public/report_index.html", ctx)


def _valid_email(addr: str) -> bool:
    return "@" in addr and "." in addr.split("@")[-1]


def _notify(subject: str, body: str) -> None:
    """Best-effort internal heads-up to the founder. No-op unless LEAD_NOTIFY_EMAIL
    is set. Never raises — capture must succeed even if mail is down."""
    import os

    to = (os.getenv("LEAD_NOTIFY_EMAIL") or "").strip()
    if not to:
        return
    try:
        from django.conf import settings
        from django.core.mail import EmailMessage

        EmailMessage(
            subject=subject[:200],
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to],
        ).send(fail_silently=True)
    except Exception:  # noqa: BLE001 - notification is best-effort
        pass


@require_POST
def newsletter_subscribe(request):
    """Capture an email for the Water Risk Monitor (the owned audience list).

    Pure inbound signal — stored as a Lead with source='newsletter'. Idempotent
    per email+source. Returns to the report page with a success flag."""
    email = (request.POST.get("email") or "").strip()
    if _valid_email(email):
        _, created = Lead.objects.get_or_create(email=email, source="newsletter")
        if created:
            _notify("New Water Risk Monitor subscriber", f"{email} subscribed to the Monitor.")
    return redirect("/report/?subscribed=1#subscribe")


@require_POST
def request_read(request):
    """Capture a free-pilot site-read request (the sales funnel).

    Stores a ReadRequest and drops a best-effort internal notification. No
    approval gate: nothing is sent to anyone but the founder, and only if
    LEAD_NOTIFY_EMAIL is configured."""
    email = (request.POST.get("email") or "").strip()
    if _valid_email(email):
        rr = ReadRequest.objects.create(
            name=(request.POST.get("name") or "").strip()[:120],
            email=email,
            company=(request.POST.get("company") or "").strip()[:160],
            market=(request.POST.get("market") or "").strip()[:160],
            note=(request.POST.get("note") or "").strip()[:2000],
            source="report_request",
        )
        _notify(
            "New free-read request",
            f"{rr.name or '(no name)'} <{rr.email}>\n"
            f"Company: {rr.company or '—'}\nMarket/site: {rr.market or '—'}\n"
            f"Note: {rr.note or '—'}",
        )
    return redirect("/report/?requested=1#request")


def report_data(request):
    """Machine-readable ranking behind the report — for citation & reproducibility."""
    ctx = state_of_context()
    if not ctx.get("has_data"):
        return JsonResponse({"markets": [], "as_of": None})
    markets = [
        {
            "rank": m["rank"],
            "market": m["metro"],
            "suitability": m["suitability"],
            "grade": m["grade"],
            "water_headroom": m["water"],
            "power_availability": m["power"],
            "hazard_safety": m["hazard"],
        }
        for m in ctx["metros"]
    ]
    return JsonResponse({
        "report": "The State of Data-Center Water Risk",
        "publisher": "Nemo Water Risk",
        "as_of": ctx["as_of"].isoformat() if ctx["as_of"] else None,
        "scale": "0-100, higher is more favorable for siting",
        "weights": {"power": 0.40, "water": 0.35, "hazard": 0.25},
        "market_count": ctx["count"],
        "markets": markets,
    })
