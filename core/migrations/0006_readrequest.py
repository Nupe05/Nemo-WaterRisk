"""ReadRequest: inbound requests for a free independent site read (pilot funnel).

Pure lead capture — no approval gate, no external action on write.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_monitoring"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, default="", max_length=120)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("company", models.CharField(blank=True, default="", max_length=160)),
                ("market", models.CharField(blank=True, default="", max_length=160)),
                ("note", models.TextField(blank=True, default="")),
                ("source", models.CharField(default="report_request", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("delivered", "Report delivered"),
                            ("closed", "Closed"),
                        ],
                        default="new",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
