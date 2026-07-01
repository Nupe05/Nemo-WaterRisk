"""
Data models for the Nemo Water Risk platform.

Design notes
------------
* Spatial data uses django.contrib.gis (PostGIS). Watersheds carry polygon
  geometry; monitored sites carry point geometry. Spatial joins that would be
  weeks of work in application code become single ORM/SQL calls.
* The ApprovalQueue is the single choke point for every externally-visible
  action (social post, outbound email, customer report send). Nothing leaves
  the system without a row here in state=APPROVED. This ports the strongest
  pattern from the previous codebase, but backs it with the database instead
  of a JSON file so concurrent workers can't clobber each other's writes
  (fixes the read-modify-write race from the prior review).
"""
from django.contrib.gis.db import models as gis
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Spatial / domain data
# ---------------------------------------------------------------------------
class Watershed(models.Model):
    """A hydrologic unit (e.g., USGS HUC-8) we track for water stress."""

    huc_code = models.CharField(max_length=16, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    geometry = gis.MultiPolygonField(srid=4326, null=True, blank=True)
    # Representative USGS gauge site number used for streamflow + baseline.
    # If blank, the pipeline falls back to a broad HUC query.
    usgs_site_no = models.CharField(max_length=15, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.huc_code})"


class MonitoredSite(models.Model):
    """A customer asset (e.g., a data center) whose water risk we monitor."""

    reference = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    location = gis.PointField(srid=4326)
    watershed = models.ForeignKey(
        Watershed, null=True, blank=True, on_delete=models.SET_NULL, related_name="sites"
    )
    customer_id = models.CharField(max_length=64, blank=True, default="")
    is_public_index = models.BooleanField(
        default=False, help_text="Exposed in the free public Water Risk Index."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.reference}]"


class RawDataRecord(models.Model):
    """A normalized measurement pulled from an external source (USGS/NOAA/EPA)."""

    class Source(models.TextChoices):
        USGS = "usgs", "USGS"
        NOAA = "noaa", "NOAA"
        EPA = "epa", "EPA"

    source = models.CharField(max_length=8, choices=Source.choices, db_index=True)
    watershed = models.ForeignKey(
        Watershed, null=True, blank=True, on_delete=models.CASCADE, related_name="records"
    )
    metric = models.CharField(max_length=64, help_text="e.g. streamflow_cfs, drought_index, withdrawal_mgd")
    value = models.FloatField()
    unit = models.CharField(max_length=32, blank=True, default="")
    observed_at = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["source", "metric", "observed_at"])]

    def __str__(self):
        return f"{self.source}:{self.metric}={self.value} @ {self.observed_at:%Y-%m-%d}"


class WaterRiskScore(models.Model):
    """A computed water-risk score (0-100) for a watershed at a point in time."""

    watershed = models.ForeignKey(Watershed, on_delete=models.CASCADE, related_name="scores")
    score = models.FloatField(help_text="0 (low risk) - 100 (severe risk)")
    components = models.JSONField(default=dict, help_text="Sub-scores that fed the total.")
    computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        get_latest_by = "computed_at"
        indexes = [models.Index(fields=["watershed", "computed_at"])]

    def __str__(self):
        return f"{self.watershed.huc_code} score={self.score:.1f}"


class RiskChange(models.Model):
    """A flagged material change in a watershed's risk score.

    Emitted by the ScoringAgent; consumed by the ContentAgent (content angle)
    and the alerting path (customer notification).
    """

    watershed = models.ForeignKey(Watershed, on_delete=models.CASCADE, related_name="changes")
    previous_score = models.FloatField(null=True, blank=True)
    new_score = models.FloatField()
    magnitude = models.FloatField(help_text="abs(new - previous)")
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    content_generated = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.watershed.huc_code} Δ{self.magnitude:.1f}"


# ---------------------------------------------------------------------------
# Agent orchestration state (ORM-backed, replaces the JSON state store)
# ---------------------------------------------------------------------------
class AgentTask(models.Model):
    """A unit of work moving through the planner -> executor -> reviewer stages."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        IN_PROGRESS = "in_progress", "In progress"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(max_length=64, help_text="e.g. build_report, generate_content")
    objective = models.TextField(blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED, db_index=True)
    stage = models.CharField(max_length=32, default="planning")
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=2)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"AgentTask#{self.pk} {self.kind} [{self.status}]"


class ApprovalItem(models.Model):
    """The human-in-the-loop gate. NO external action runs without an
    APPROVED row here. Reviewed in Django admin.
    """

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXECUTED = "executed", "Executed"
        FAILED = "failed", "Failed"

    # Registry of action types the runner knows how to execute. The executor
    # may ONLY propose these, and the runner validates against the same list —
    # one shared vocabulary (fixes the split registry from the prior review).
    class ActionType(models.TextChoices):
        WRITE_FILE = "write_file", "Write file (workspace-jailed)"
        SEND_REPORT = "send_report", "Email customer report"
        POST_TWITTER = "post_twitter", "Post X/Twitter thread"
        POST_YOUTUBE = "post_youtube", "Publish YouTube content"
        POST_INSTAGRAM = "post_instagram", "Post Instagram"

    task = models.ForeignKey(
        AgentTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="approvals"
    )
    content_type = models.CharField(max_length=48, help_text="e.g. social_content, customer_report")
    action_type = models.CharField(max_length=32, choices=ActionType.choices)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING, db_index=True)
    summary = models.CharField(max_length=512, blank=True, default="")
    payload = models.JSONField(default=dict, help_text="Exactly what will be executed on approval.")
    review_notes = models.TextField(blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Approval#{self.pk} {self.action_type} [{self.state}]"


class ContentItem(models.Model):
    """A drafted marketing asset (one trigger -> multi-platform outputs)."""

    trigger_change = models.ForeignKey(
        RiskChange, null=True, blank=True, on_delete=models.SET_NULL, related_name="content"
    )
    youtube_outline = models.TextField(blank=True, default="")
    twitter_thread = models.JSONField(default=list, blank=True)
    instagram_caption = models.TextField(blank=True, default="")
    visual_brief = models.TextField(blank=True, default="")
    visual_path = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ContentItem#{self.pk}"


class MailboxCredential(models.Model):
    """OAuth mailbox tokens. Stored encrypted at rest (see core.crypto).

    The previous system stored refresh tokens in plaintext JSON; here the
    token blob is encrypted before it ever touches the database.
    """

    customer_id = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=32, default="gmail")
    email_address = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=24, default="disconnected")
    encrypted_tokens = models.BinaryField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Mailbox<{self.customer_id}:{self.status}>"
