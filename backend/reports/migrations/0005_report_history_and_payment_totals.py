from copy import deepcopy
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def preserve_legacy_payment_inputs(apps, schema_editor):
    """The old card field was phone cards; independent payments were not captured."""
    Report = apps.get_model("reports", "DailyReport")
    for report in Report.objects.using(schema_editor.connection.alias).iterator():
        calculated = deepcopy(report.calculated_report)
        inputs = calculated.setdefault("inputs", {})
        inputs.pop("gas_card_sales", None)
        inputs["gas_phone_card_sales"] = format(report.gas_phone_card_sales, ".2f")
        inputs["gas_card_payment_sales"] = None
        calculated.setdefault("registers", {})["gas_net_difference"] = None
        expected = report.phone_card_actual_sales
        actual = report.bodega_phone_card_sales + report.gas_phone_card_sales
        difference = actual - expected
        calculated.setdefault("comparisons", {})["phone_card_sales"] = {
            "expected": format(expected, ".2f"), "actual": format(actual, ".2f"),
            "difference": format(difference, ".2f"),
            "status": "match" if difference == Decimal("0.00") else "mismatch",
        }
        Report.objects.using(schema_editor.connection.alias).filter(pk=report.pk).update(calculated_report=calculated)



def backfill_normalized_entries(apps, schema_editor):
    Report = apps.get_model("reports", "DailyReport")
    Roll = apps.get_model("reports", "ScratchOffRoll")
    Item = apps.get_model("reports", "ReportLineItem")
    alias = schema_editor.connection.alias
    for report in Report.objects.using(alias).iterator():
        for reading in report.scratch_offs:
            ending = reading.get("ending_number")
            ending = int(ending) if ending is not None and str(ending).strip() else None
            count = reading.get("new_roll_count", 1 if reading.get("new_roll") else 0)
            Roll.objects.using(alias).get_or_create(
                report_id=report.pk, slot_number=reading["slot_number"],
                defaults={"ending_number": ending, "new_roll_counter": count + 1},
            )
        for item_type, key in (("ticket", "tickets"), ("vendor_payout", "vendor_payouts"), ("safe_drop", "safe_drops")):
            if not Item.objects.using(alias).filter(report_id=report.pk, item_type=item_type).exists():
                Item.objects.using(alias).bulk_create([
                    Item(report_id=report.pk, item_type=item_type, amount=item["amount"],
                         description=item.get("description", ""), position=index)
                    for index, item in enumerate(getattr(report, key))
                ])

def restore_legacy_payment_inputs(apps, schema_editor):
    Report = apps.get_model("reports", "DailyReport")
    for report in Report.objects.using(schema_editor.connection.alias).iterator():
        calculated = deepcopy(report.calculated_report)
        inputs = calculated.setdefault("inputs", {})
        inputs["gas_card_sales"] = inputs.pop("gas_phone_card_sales", format(report.gas_phone_card_sales, ".2f"))
        inputs.pop("gas_card_payment_sales", None)
        gas_net = (report.gas_cash_sales - report.bodega_gas_sales - report.gas_phone_card_sales
                   - sum((Decimal(item["amount"]) for key in ("tickets", "vendor_payouts", "safe_drops")
                          for item in getattr(report, key)), Decimal("0.00")))
        calculated.setdefault("registers", {})["gas_net_difference"] = format(gas_net, ".2f")
        Report.objects.using(schema_editor.connection.alias).filter(pk=report.pk).update(calculated_report=calculated)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0004_reportlineitem_scratchoffroll"),
        ("stores", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(model_name="dailyreport", old_name="gas_card_sales", new_name="gas_phone_card_sales"),
        migrations.AddField(model_name="dailyreport", name="gas_card_payment_sales", field=models.DecimalField(decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="dailyreport", name="store", field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to="stores.store")),
        migrations.AddField(model_name="scratchoffroll", name="ending_exhausted", field=models.BooleanField(default=False)),
        migrations.AlterModelOptions(name="dailyreport", options={"ordering": ["-report_date", "-created_at", "-id"]}),
        migrations.AddConstraint(model_name="dailyreport", constraint=models.UniqueConstraint(condition=models.Q(close_type="day"), fields=("store", "report_date"), name="unique_store_day_close")),
        migrations.RunPython(preserve_legacy_payment_inputs, restore_legacy_payment_inputs),
        migrations.RunPython(backfill_normalized_entries, migrations.RunPython.noop),
    ]
