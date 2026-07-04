"""Siting engine: candidate locations + suitability scores.

Also widens ApprovalItem.action_type choices to include SEND_SITING_REPORT so
the siting revenue loop (signup -> approval-gated report send) uses the same
approval queue as the water product.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_inboundemail"),
    ]

    operations = [
        migrations.AlterField(
            model_name="approvalitem",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("write_file", "Write file (workspace-jailed)"),
                    ("send_report", "Email customer report"),
                    ("post_twitter", "Post X/Twitter thread"),
                    ("post_youtube", "Publish YouTube content"),
                    ("post_instagram", "Post Instagram"),
                    ("email_reply", "Email reply to an inbound message"),
                    ("send_siting_report", "Email site-selection report"),
                ],
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="SitingLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("county_fips", models.CharField(db_index=True, max_length=5, unique=True)),
                ("county_name", models.CharField(max_length=128)),
                ("state_fips", models.CharField(db_index=True, max_length=2)),
                ("metro", models.CharField(db_index=True, max_length=128)),
                ("market_status", models.CharField(default="emerging", max_length=16)),
                ("is_public_teaser", models.BooleanField(default=True, help_text="Include this metro in the free public siting teaser.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["metro", "county_name"]},
        ),
        migrations.CreateModel(
            name="SitingScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("suitability", models.FloatField(help_text="0-100 composite; higher = better site.")),
                ("water", models.FloatField(default=0.0)),
                ("power", models.FloatField(default=0.0)),
                ("hazard", models.FloatField(default=0.0)),
                ("grade", models.CharField(blank=True, default="", max_length=16)),
                ("rank", models.PositiveIntegerField(blank=True, help_text="1 = best county this run.", null=True)),
                ("detail", models.JSONField(blank=True, default=dict, help_text="Weights, notes, hazard list, ISO region.")),
                ("computed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scores", to="core.sitinglocation")),
            ],
            options={
                "ordering": ["-suitability"],
                "indexes": [models.Index(fields=["-suitability", "computed_at"], name="core_siting_suitabi_idx")],
            },
        ),
    ]
