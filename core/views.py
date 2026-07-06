"""Public-facing views for the free Water Risk Index.

The Index is the lead magnet from the go-to-market plan: publish it, and the
signups tell you whether anyone will pay for the full methodology before you
build a checkout page. Server-rendered HTML for shareability + a small JSON
API for programmatic use.
"""
import os
import re

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.utils.text import slugify

from scoring.bands import band
from scoring.model import WEIGHTS
from .models import (
    ApprovalItem,
    InboundEmail,
    Lead,
    MonitoredSite,
    MonitorSubscription,
    WaterRiskScore,
)

COMPONENT_LABELS = {
    "streamflow_deficit": "Streamflow deficit",
    "drought_index": "Drought severity (USDM)",
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
    components = [
        {"label": COMPONENT_LABELS.get(k, k), "value": v}
        for k, v in (row["components"] or {}).items()
        if k in COMPONENT_LABELS
    ]
    return render(request, "public/detail.html", {"row": row, "components": components})


@require_POST
def subscribe(request):
    email = (request.POST.get("email") or "").strip()
    site_ref = (request.POST.get("site_ref") or "").strip()
    if "@" in email and "." in email:
        lead = Lead.objects.create(email=email, site_ref=site_ref, source="water_risk_index")
        _queue_report_request(lead, site_ref)
    return redirect("/?subscribed=1#signup")


def _queue_report_request(lead: Lead, site_ref: str) -> None:
    """If the lead asked about a specific metro, queue an approval-gated report send.

    This is the revenue connector: a signup on a metro's page becomes an
    actionable item in the approval queue. The report is (re)generated and
    emailed only when you approve it — nothing leaves automatically.
    """
    if not site_ref:
        return
    site = MonitoredSite.objects.filter(reference=site_ref).first()
    if not site:
        return
    ApprovalItem.objects.create(
        content_type="customer_report",
        action_type=ApprovalItem.ActionType.SEND_REPORT,
        state=ApprovalItem.State.PENDING,
        summary=f"Send {site.name} water-risk report to {lead.email}",
        payload={"to": lead.email, "site": site.reference, "lead_id": lead.id},
    )


# --- Monitoring subscription (recurring-revenue signup) ---------------------
@require_POST
def monitor_subscribe(request):
    """Subscribe an email to alerts for a water site or a siting metro.

    Works from both product surfaces via hidden fields:
      target_type = 'site' | 'metro',  target_ref = site reference | metro name.
    Idempotent per (email, target, type) thanks to the DB unique constraint.
    """
    email = (request.POST.get("email") or "").strip()
    target_type = (request.POST.get("target_type") or "").strip()
    target_ref = (request.POST.get("target_ref") or "").strip()
    tier = (request.POST.get("tier") or "basic").strip()

    valid_types = {t for t, _ in MonitorSubscription.TargetType.choices}
    valid_tiers = {t for t, _ in MonitorSubscription.Tier.choices}
    if "@" in email and "." in email and target_type in valid_types and target_ref:
        MonitorSubscription.objects.get_or_create(
            email=email,
            target_type=target_type,
            target_ref=target_ref,
            defaults={
                "tier": tier if tier in valid_tiers else "basic",
                "source": "monitor_signup",
            },
        )
        Lead.objects.get_or_create(
            email=email, source="monitor_signup", defaults={"site_ref": target_ref}
        )

    if target_type == "metro":
        dest = f"/siting/{slugify(target_ref)}/"
    else:
        dest = f"/site/{target_ref}/"
    return redirect(f"{dest}?monitoring=1")


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
            f"median for this time of year, a primary driver of the score."
        )
    di = comps.get("drought_index")
    if di:
        lines.append(
            f"The U.S. Drought Monitor shows elevated drought conditions across the metro "
            f"(severity index {di:.0f} of 100)."
        )
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


# --- Inbound email (SendGrid Inbound Parse webhook) -------------------------
_REPLY_SYSTEM = (
    "You draft concise, professional email replies for Nemo Water Risk, an independent "
    "water-supply risk intelligence service for U.S. data-center metros. Be helpful and "
    "factual, point the sender to the public index at https://www.nemowaterrisk.com where "
    "relevant, and NEVER invent specific risk numbers. Keep it under 150 words. "
    'Return ONLY JSON: {"reply": "<plain-text email reply>"}.'
)


def _extract_email(raw: str) -> str:
    match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", raw or "")
    return match.group(0).lower() if match else ""


def _send_acknowledgment(to: str, subject: str) -> None:
    from django.conf import settings
    from django.core.mail import EmailMessage

    text = (
        "Thanks for reaching out to Nemo Water Risk. We've received your message and will "
        "follow up shortly.\n\nIn the meantime, our live water-risk index for the major U.S. "
        "data-center metros is at https://www.nemowaterrisk.com.\n\n— Nemo Water Risk"
    )
    try:
        EmailMessage(
            subject=(f"Re: {subject}" if subject else "Thanks for reaching out")[:255],
            body=text,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to],
        ).send(fail_silently=True)
    except Exception:  # noqa: BLE001 - acknowledgment is best-effort
        pass


def _queue_ai_reply(sender: str, subject: str, body: str) -> None:
    from agents.llm_client import LLMError, call_llm_json

    try:
        data = call_llm_json(
            _REPLY_SYSTEM,
            f"Inbound email from {sender}\nSubject: {subject}\n\n{body}",
            temperature=0.4,
        )
        reply = str(data.get("reply", "")).strip()
    except LLMError:
        reply = ""  # skip the AI reply; the acknowledgment already went out
    if not reply:
        return
    ApprovalItem.objects.create(
        content_type="email_reply",
        action_type=ApprovalItem.ActionType.EMAIL_REPLY,
        state=ApprovalItem.State.PENDING,
        summary=f"Reply to {sender}: {(subject or body)[:60]}",
        payload={
            "to": sender,
            "subject": f"Re: {subject}" if subject else "Re: your message",
            "body": reply,
        },
    )


@csrf_exempt
@require_POST
def inbound_email(request):
    """Webhook for SendGrid Inbound Parse.

    Hybrid autonomy: auto-sends a safe acknowledgment immediately, and queues an
    AI-drafted personalized reply for approval. Protected by a shared secret in
    the URL (?token=), set as INBOUND_EMAIL_TOKEN.
    """
    token = (os.getenv("INBOUND_EMAIL_TOKEN") or "").strip()
    if token and request.GET.get("token") != token:
        return HttpResponse(status=403)

    sender = _extract_email(request.POST.get("from") or "")
    subject = (request.POST.get("subject") or "").strip()
    body = (request.POST.get("text") or request.POST.get("email") or "").strip()
    if not sender:
        return HttpResponse(status=200)  # nothing actionable; ack SendGrid anyway

    InboundEmail.objects.create(from_email=sender, subject=subject[:500], body=body, acknowledged=True)
    Lead.objects.get_or_create(email=sender, defaults={"source": "inbound_email"})

    _send_acknowledgment(sender, subject)   # instant, safe
    _queue_ai_reply(sender, subject, body)  # approval-gated, AI-drafted

    return HttpResponse(status=200)


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
            "methodology": "USGS streamflow deficit + U.S. Drought Monitor severity + population-weighted withdrawal pressure (U.S. Census).",
        }
    )
