from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="LoginAttemptBucket",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
        ),
    ]
