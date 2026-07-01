"""Enable the PostGIS extension before any geometry columns are created."""
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        CreateExtension("postgis"),
    ]
