"""Monitoring & alerts: subscriptions, alert events, and siting change events.

Also widens ApprovalItem.action_type choices to include SEND_ALERT so
monitoring alerts flow through the same approval queue as everything else.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_siting"),
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
                    ("send_alert", "Email a monitoring alert"),
                ],
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="SitingChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metro", models.CharField(db_index=True, max_length=128)),
                ("previous_score", models.FloatField(blank=True, null=True)),
                ("new_score", models.FloatField()),
                ("magnitude", models.FloatField(help_text="abs(new - previous)")),
                ("detected_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-detected_at"]},
        ),
        migrations.CreateModel(
            name="MonitorSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("target_type", models.CharField(choices=[("site", "Water-risk site"), ("metro", "Siting metro")], max_length=8)),
                ("target_ref", models.CharField(help_text="Site reference or metro name.", max_length=128)),
                ("tier", models.CharField(choices=[("basic", "Basic"), ("pro", "Pro")], default="basic", max_length=8)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("source", models.CharField(default="monitor_signup", max_length=64)),
                ("last_alerted_score", models.FloatField(blank=True, null=True)),
                ("last_alerted_band", models.CharField(blank=True, default="", max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="monitorsubscription",
            constraint=models.UniqueConstraint(
                fields=["email", "target_type", "target_ref"], name="uniq_subscription_per_target"
            ),
        ),
        migrations.CreateModel(
            name="AlertEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(max_length=8)),
                ("target_ref", models.CharField(max_length=128)),
                ("from_score", models.FloatField(blank=True, null=True)),
                ("to_score", models.FloatField()),
                ("from_band", models.CharField(blank=True, default="", max_length=24)),
                ("to_band", models.CharField(blank=True, default="", max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("approval", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alert_events", to="core.approvalitem")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="core.monitorsubscription")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
