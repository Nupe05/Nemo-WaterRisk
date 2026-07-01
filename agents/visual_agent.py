"""VisualAgent — render real-data charts for content (no generative imagery).

Uses Matplotlib against our own scores, which is more credible for a data
company than AI-generated images. Writes PNGs into the workspace jail.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings

from core.models import ContentItem, WaterRiskScore
from .base import BaseAgent


class VisualAgent(BaseAgent):
    name = "visual"

    def run(self, *, content_item_id: int, size: str = "instagram") -> dict:
        item = ContentItem.objects.select_related("trigger_change__watershed").get(pk=content_item_id)
        dims = {"instagram": (1080, 1080), "youtube": (1280, 720)}.get(size, (1080, 1080))

        path = self._render_score_history(item, dims)
        item.visual_path = path
        item.save(update_fields=["visual_path"])
        return {"content_item": item.pk, "visual_path": path}

    def _render_score_history(self, item: ContentItem, dims: tuple[int, int]) -> str:
        out_dir = Path(settings.NEMO["WORKSPACE_ROOT"]) / "visuals"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"content_{item.pk}.png"

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            change = item.trigger_change
            scores = (
                list(
                    WaterRiskScore.objects.filter(watershed=change.watershed)
                    .order_by("computed_at")
                    .values_list("computed_at", "score")
                )
                if change and change.watershed_id
                else []
            )

            fig_w, fig_h = dims[0] / 100, dims[1] / 100
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=100)
            if scores:
                xs = [s[0] for s in scores]
                ys = [s[1] for s in scores]
                ax.plot(xs, ys, linewidth=3, color="#0b3d5c")
                ax.fill_between(xs, ys, color="#0b3d5c", alpha=0.1)
                ax.set_title(change.watershed.name + " — Water Risk Score", fontsize=16)
            else:
                ax.text(0.5, 0.5, "No score history yet", ha="center", va="center")
                ax.axis("off")
            ax.set_ylim(0, 100)
            fig.tight_layout()
            fig.savefig(str(out_path))
            plt.close(fig)
        except Exception as exc:  # noqa: BLE001 - never block on rendering
            self.log("visual_render_failed", error=str(exc))
            out_path = out_path.with_suffix(".txt")
            out_path.write_text(f"visual render failed: {exc}", encoding="utf-8")

        return str(out_path)
