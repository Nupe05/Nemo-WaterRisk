"""Add the InboundEmail table (SendGrid Inbound Parse records)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_core_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="InboundEmail",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_email", models.EmailField(db_index=True, max_length=254)),
                ("subject", models.CharField(blank=True, default="", max_length=500)),
                ("body", models.TextField(blank=True, default="")),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("acknowledged", models.BooleanField(default=False)),
            ],
            options={"ordering": ["-received_at"]},
        ),
    ]
