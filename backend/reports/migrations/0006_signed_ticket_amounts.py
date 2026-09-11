from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0005_report_history_and_payment_totals"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="reportlineitem",
            name="report_line_item_nonnegative",
        ),
        migrations.AddConstraint(
            model_name="reportlineitem",
            constraint=models.CheckConstraint(
                condition=models.Q(item_type="ticket") | models.Q(amount__gte=0),
                name="report_line_item_amount_valid",
            ),
        ),
    ]
