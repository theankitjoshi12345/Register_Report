from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reports", "0007_cumulative_shift_terminal_readings")]

    operations = [
        migrations.AddField(
            model_name="dailyreport",
            name="bodega_ai_tickets",
            field=models.JSONField(default=list),
        ),
        migrations.AlterField(
            model_name="reportlineitem",
            name="item_type",
            field=models.CharField(
                choices=[
                    ("ticket", "Ticket"),
                    ("bodega_ai_ticket", "Bodega AI ticket"),
                    ("vendor_payout", "Vendor payout"),
                    ("safe_drop", "Safe drop"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="reportlineitem",
            constraint=models.CheckConstraint(
                condition=~models.Q(item_type="bodega_ai_ticket") | models.Q(amount__gt=0),
                name="bodega_ticket_amount_positive",
            ),
        ),
    ]
