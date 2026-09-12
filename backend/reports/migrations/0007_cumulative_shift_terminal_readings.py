from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reports", "0006_signed_ticket_amounts")]

    operations = [
        migrations.AddField(
            model_name="dailyreport",
            name="terminal_values_cumulative",
            field=models.BooleanField(default=False),
        ),
    ]
