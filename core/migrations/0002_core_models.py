"""Full schema for the core app.

Committed so that `migrate` applies the schema deterministically (the release
phase no longer relies on `makemigrations`, which silently skipped field
additions because it reused migration names). Going forward, each schema
change ships with its own committed migration.
"""
import django.contrib.gis.db.models.fields
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    # Marked initial so `migrate --fake-initial` recognizes the already-existing
    # tables on the deployed database (which predate committed migrations) and
    # records this as applied without recreating them. A fresh database builds
    # the schema normally.
    initial = True

    dependencies = [
        ("core", "0001_enable_postgis"),
    ]

    operations = [
        migrations.CreateModel(
            name="Watershed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("huc_code", models.CharField(db_index=True, max_length=16, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("geometry", django.contrib.gis.db.models.fields.MultiPolygonField(blank=True, null=True, srid=4326)),
                ("usgs_site_no", models.CharField(blank=True, default="", max_length=15)),
                ("county_fips", models.CharField(blank=True, default="", max_length=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="AgentTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=64)),
                ("objective", models.TextField(blank=True, default="")),
                ("status", models.CharField(db_index=True, default="queued", max_length=24)),
                ("stage", models.CharField(default="planning", max_length=32)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=2)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("site_ref", models.CharField(blank=True, default="", max_length=64)),
                ("source", models.CharField(default="water_risk_index", max_length=64)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="MailboxCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_id", models.CharField(max_length=64, unique=True)),
                ("provider", models.CharField(default="gmail", max_length=32)),
                ("email_address", models.EmailField(blank=True, default="", max_length=254)),
                ("status", models.CharField(default="disconnected", max_length=24)),
                ("encrypted_tokens", models.BinaryField(blank=True, null=True)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="MonitoredSite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(db_index=True, max_length=64, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ("customer_id", models.CharField(blank=True, default="", max_length=64)),
                ("is_public_index", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("watershed", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sites", to="core.watershed")),
            ],
        ),
        migrations.CreateModel(
            name="RawDataRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(db_index=True, max_length=8)),
                ("metric", models.CharField(max_length=64)),
                ("value", models.FloatField()),
                ("unit", models.CharField(blank=True, default="", max_length=32)),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("raw", models.JSONField(blank=True, default=dict)),
                ("watershed", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="records", to="core.watershed")),
            ],
        ),
        migrations.CreateModel(
            name="WaterRiskScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score", models.FloatField()),
                ("components", models.JSONField(default=dict)),
                ("computed_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("watershed", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scores", to="core.watershed")),
            ],
            options={"get_latest_by": "computed_at"},
        ),
        migrations.CreateModel(
            name="RiskChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_score", models.FloatField(blank=True, null=True)),
                ("new_score", models.FloatField()),
                ("magnitude", models.FloatField()),
                ("detected_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("content_generated", models.BooleanField(default=False)),
                ("watershed", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="changes", to="core.watershed")),
            ],
        ),
        migrations.CreateModel(
            name="ContentItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("youtube_outline", models.TextField(blank=True, default="")),
                ("twitter_thread", models.JSONField(blank=True, default=list)),
                ("instagram_caption", models.TextField(blank=True, default="")),
                ("visual_brief", models.TextField(blank=True, default="")),
                ("visual_path", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("trigger_change", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="content", to="core.riskchange")),
            ],
        ),
        migrations.CreateModel(
            name="ApprovalItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content_type", models.CharField(max_length=48)),
                ("action_type", models.CharField(max_length=32)),
                ("state", models.CharField(db_index=True, default="pending", max_length=16)),
                ("summary", models.CharField(blank=True, default="", max_length=512)),
                ("payload", models.JSONField(default=dict)),
                ("review_notes", models.TextField(blank=True, default="")),
                ("result", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("executed_at", models.DateTimeField(blank=True, null=True)),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approvals", to="core.agenttask")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="rawdatarecord",
            index=models.Index(fields=["source", "metric", "observed_at"], name="core_rawdat_source_ec83b0_idx"),
        ),
        migrations.AddIndex(
            model_name="waterriskscore",
            index=models.Index(fields=["watershed", "computed_at"], name="core_waters_watersh_a1b2c3_idx"),
        ),
    ]
