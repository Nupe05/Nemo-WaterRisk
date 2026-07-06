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
    # County FIPS for the associated metro, used for U.S. Drought Monitor data.
    county_fips = models.CharField(max_length=5, blank=True, default="")
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
        USDM = "usdm", "U.S. Drought Monitor"
        CENSUS = "census", "U.S. Census"

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
        EMAIL_REPLY = "email_reply", "Email reply to an inbound message"
        SEND_SITING_REPORT = "send_siting_report", "Email site-selection report"
        SEND_ALERT = "send_alert", "Email a monitoring alert"

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


class Lead(models.Model):
    """An inbound signup from the free public Water Risk Index.

    This is the demand signal from the go-to-market plan: if people ask for
    the full methodology, there is a business. Purely inbound data — no
    approval gate needed (the agent isn't taking an external action).
    """

    email = models.EmailField(db_index=True)
    site_ref = models.CharField(max_length=64, blank=True, default="")
    source = models.CharField(max_length=64, default="water_risk_index")
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Lead<{self.email}>"


class InboundEmail(models.Model):
    """An email received via the SendGrid Inbound Parse webhook.

    On receipt we auto-send a safe acknowledgment (hybrid mode) and queue an
    AI-drafted personalized reply as an approval-gated EMAIL_REPLY action.
    """

    from_email = models.EmailField(db_index=True)
    subject = models.CharField(max_length=500, blank=True, default="")
    body = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"InboundEmail<{self.from_email}: {self.subject[:40]}>"


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


# ---------------------------------------------------------------------------
# Site selection ("where to build") — the proactive siting product
# ---------------------------------------------------------------------------
class SitingLocation(models.Model):
    """A candidate county the siting engine scores, grouped into a metro market.

    Seeded from integrations.siting_locations.LOCATIONS. Kept as a table (not
    just a Python list) so scores, ranks, and the public teaser can be queried
    and joined like any other domain data.
    """

    county_fips = models.CharField(max_length=5, unique=True, db_index=True)
    county_name = models.CharField(max_length=128)
    state_fips = models.CharField(max_length=2, db_index=True)
    metro = models.CharField(max_length=128, db_index=True)
    market_status = models.CharField(max_length=16, default="emerging")  # established | emerging
    is_public_teaser = models.BooleanField(
        default=True, help_text="Include this metro in the free public siting teaser."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["metro", "county_name"]

    def __str__(self):
        return f"{self.county_name} ({self.metro})"


class SitingScore(models.Model):
    """A computed data-center suitability score for a candidate county.

    Higher = more suitable (the inverse direction of WaterRiskScore). The three
    legs are the favorability sub-scores that fed the composite.
    """

    location = models.ForeignKey(
        SitingLocation, on_delete=models.CASCADE, related_name="scores"
    )
    suitability = models.FloatField(help_text="0-100 composite; higher = better site.")
    water = models.FloatField(default=0.0)
    power = models.FloatField(default=0.0)
    hazard = models.FloatField(default=0.0)
    grade = models.CharField(max_length=16, blank=True, default="")
    rank = models.PositiveIntegerField(null=True, blank=True, help_text="1 = best county this run.")
    detail = models.JSONField(default=dict, blank=True, help_text="Weights, notes, hazard list, ISO region.")
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-suitability"]
        indexes = [models.Index(fields=["-suitability", "computed_at"], name="core_siting_suitabi_idx")]

    def __str__(self):
        return f"SitingScore<{self.location.county_name}={self.suitability}>"


class SitingChange(models.Model):
    """A flagged material change in a metro's siting suitability.

    The siting analogue of RiskChange: emitted by the SitingAgent when a
    metro's rolled-up suitability moves by more than the configured threshold
    between runs. Consumed by the monitoring/alert path.
    """

    metro = models.CharField(max_length=128, db_index=True)
    previous_score = models.FloatField(null=True, blank=True)
    new_score = models.FloatField()
    magnitude = models.FloatField(help_text="abs(new - previous)")
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"SitingChange<{self.metro}: {self.previous_score}->{self.new_score}>"


# ---------------------------------------------------------------------------
# Monitoring & alerts — the recurring-revenue product
# ---------------------------------------------------------------------------
class MonitorSubscription(models.Model):
    """A customer's standing subscription to be alerted when a target's risk
    changes. Targets are either a water-index site or a siting metro. This is
    the recurring-revenue primitive: one signup, ongoing alerts.

    `last_alerted_*` capture the state we last notified on, so the sweep never
    double-alerts the same condition. Billing lives in a later brick; `tier`
    already models the paid levels so the alert logic can honor them now.
    """

    class TargetType(models.TextChoices):
        SITE = "site", "Water-risk site"
        METRO = "metro", "Siting metro"

    class Tier(models.TextChoices):
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"

    email = models.EmailField(db_index=True)
    target_type = models.CharField(max_length=8, choices=TargetType.choices)
    target_ref = models.CharField(max_length=128, help_text="Site reference or metro name.")
    tier = models.CharField(max_length=8, choices=Tier.choices, default=Tier.BASIC)
    active = models.BooleanField(default=True, db_index=True)
    source = models.CharField(max_length=64, default="monitor_signup")
    last_alerted_score = models.FloatField(null=True, blank=True)
    last_alerted_band = models.CharField(max_length=24, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["email", "target_type", "target_ref"],
                name="uniq_subscription_per_target",
            )
        ]

    def __str__(self):
        return f"Monitor<{self.email}:{self.target_type}:{self.target_ref}>"


class AlertEvent(models.Model):
    """Audit trail of a fired monitoring alert (one per material adverse move).

    Records the transition and links the approval-gated email, so we have a
    full history and never re-alert an already-notified condition.
    """

    subscription = models.ForeignKey(
        MonitorSubscription, on_delete=models.CASCADE, related_name="alerts"
    )
    target_type = models.CharField(max_length=8)
    target_ref = models.CharField(max_length=128)
    from_score = models.FloatField(null=True, blank=True)
    to_score = models.FloatField()
    from_band = models.CharField(max_length=24, blank=True, default="")
    to_band = models.CharField(max_length=24, blank=True, default="")
    approval = models.ForeignKey(
        "ApprovalItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="alert_events"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AlertEvent<{self.target_ref}: {self.from_band}->{self.to_band}>"
