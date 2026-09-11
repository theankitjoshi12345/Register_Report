import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_main_store(apps, schema_editor):
    apps.get_model("stores", "Store").objects.using(schema_editor.connection.alias).create(name="Main store")


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Store",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="StoreMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="stores.store")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="store_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("store", "user"), name="unique_store_member")]},
        ),
        migrations.RunPython(create_main_store, migrations.RunPython.noop),
    ]

