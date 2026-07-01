"""ReportAgent — generate a customer PDF report, gate the *send* on approval.

Rendering the PDF into the workspace is an internal, safe action. Emailing it
to the customer is external, so it is queued as a SEND_REPORT approval item
rather than sent directly. Zero human effort to produce; one click to send.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import ApprovalItem, MonitoredSite, WaterRiskScore
from .base import BaseAgent

_BANDS = [(80, "Severe", "#b00020"), (60, "High", "#e2711d"), (40, "Elevated", "#e0a800"),
          (20, "Moderate", "#2a9d8f"), (0, "Low", "#2a7d2a")]
_LABELS = {
    "streamflow_deficit": "Streamflow deficit",
    "precip_deficit": "Precipitation deficit",
    "withdrawal_pressure": "Withdrawal pressure",
}


def _band(score: float):
    for threshold, label, color in _BANDS:
        if score >= threshold:
            return label, color
    return "Low", "#2a7d2a"


class ReportAgent(BaseAgent):
    name = "report"

    def run(self, *, site_reference: str, recipient: str = "") -> dict:
        site = MonitoredSite.objects.select_related("watershed").get(reference=site_reference)
        latest = (
            WaterRiskScore.objects.filter(watershed=site.watershed).order_by("-computed_at").first()
            if site.watershed_id
            else None
        )
        if latest is None:
            raise ValueError(f"no_score_for_site:{site_reference}")

        band, color = _band(latest.score)
        narrative = self._narrative(site, latest, band)
        components = [
            {"label": _LABELS.get(k, k), "value": v, "weight": latest.components.get("weights", {}).get(k, "")}
            for k, v in latest.components.items()
            if k in _LABELS
        ]

        html = render_to_string(
            "report.html",
            {
                "site_name": site.name,
                "watershed_name": site.watershed.name if site.watershed_id else "—",
                "site_ref": site.reference,
                "as_of": latest.computed_at.strftime("%Y-%m-%d"),
                "score": round(latest.score, 1),
                "score_color": color,
                "band": band,
                "components": components,
                "narrative": narrative,
            },
        )

        pdf_path = self._render_pdf(html, site.reference)

        # External send is approval-gated.
        approval = self.queue_for_approval(
            content_type="customer_report",
            action_type=ApprovalItem.ActionType.SEND_REPORT,
            payload={"to": recipient, "report_path": pdf_path, "site": site.reference},
            summary=f"Send water-risk report for {site.name} ({band}, {latest.score:.0f})",
        )
        return {"pdf_path": pdf_path, "approval_id": approval.pk}

    def _render_pdf(self, html: str, ref: str) -> str:
        out_dir = Path(settings.NEMO["WORKSPACE_ROOT"]) / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"water_risk_{ref}_{timezone.now():%Y%m%d}.pdf"
        try:
            from weasyprint import HTML

            HTML(string=html).write_pdf(str(pdf_path))
        except Exception as exc:  # noqa: BLE001 - fall back to HTML if WeasyPrint deps missing
            self.log("weasyprint_failed_fallback_html", error=str(exc))
            pdf_path = pdf_path.with_suffix(".html")
            pdf_path.write_text(html, encoding="utf-8")
        return str(pdf_path)

    def _narrative(self, site, score, band) -> str:
        """Optional LLM narrative; falls back to a deterministic sentence."""
        try:
            data = self.think_json(
                system_prompt=(
                    "You write concise, factual water-risk narratives for data-center "
                    "operators. 2-3 sentences. Cite the numbers you are given. No hype. "
                    'Return JSON: {"narrative": "string"}.'
                ),
                user_prompt=(
                    f"Site: {site.name}. Risk score: {score.score} ({band}). "
                    f"Components: {score.components}."
                ),
                temperature=0.3,
            )
            text = str(data.get("narrative", "")).strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001 - never block a report on the LLM
            self.log("narrative_llm_failed", error=str(exc))
        return (
            f"{site.name} currently carries a water-risk score of {score.score:.0f} "
            f"({band}). This reflects recent streamflow, precipitation, and withdrawal "
            f"conditions in its watershed."
        )
