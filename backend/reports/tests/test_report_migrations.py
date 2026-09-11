"""Protect existing closes when the old card field is clarified."""

from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReportDataMigrationTests(TransactionTestCase):
    migrate_from = [("reports", "0004_reportlineitem_scratchoffroll"), ("stores", "0001_initial")]
    migrate_to = [("reports", "0005_report_history_and_payment_totals"), ("stores", "0001_initial")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        old_apps.get_model("stores", "Store").objects.get_or_create(pk=1, defaults={"name": "Main store"})
        old_report = old_apps.get_model("reports", "DailyReport")
        old_roll = old_apps.get_model("reports", "ScratchOffRoll")
        self.report_id = old_report.objects.create(
            report_date="2026-09-10", close_type="day", close_label="Original close",
            lottery_terminal_sales="0.00", lottery_terminal_payout="0.00", phone_card_actual_sales="35.00",
            bodega_net_difference="-1.25", bodega_lottery_sales="0.00", bodega_lottery_payout="0.00",
            bodega_phone_card_sales="10.00", bodega_gas_sales="0.00", gas_cash_sales="100.00",
            gas_lottery_sales="0.00", gas_lottery_payout="0.00", gas_card_sales="25.00",
            tickets=[{"amount": "23.00", "description": "Original ticket"}],
            vendor_payouts=[{"amount": "2.00", "description": "Original vendor"}],
            safe_drops=[{"amount": "3.00", "description": "Original drop"}],
            scratch_offs=[
                {"slot_number": 1, "ending_number": None, "new_roll_count": 2},
                {"slot_number": 4, "ending_number": "015", "new_roll_count": 0},
            ],
            calculated_report={"inputs": {"gas_card_sales": "25.00"}, "registers": {"gas_net_difference": "47.00"}},
        ).pk
        old_roll.objects.create(report_id=self.report_id, slot_number=4, last_night_number=10, ending_number=15)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        # Leave the database at the latest schema for the remainder of the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_legacy_phone_card_money_and_missing_independent_payment_are_preserved(self):
        report = self.apps.get_model("reports", "DailyReport").objects.get(pk=self.report_id)
        self.assertEqual(report.store_id, 1)
        self.assertEqual(report.gas_phone_card_sales, Decimal("25.00"))
        self.assertIsNone(report.gas_card_payment_sales)
        self.assertEqual(report.close_label, "Original close")
        self.assertEqual(report.bodega_net_difference, Decimal("-1.25"))
        inputs = report.calculated_report["inputs"]
        self.assertNotIn("gas_card_sales", inputs)
        self.assertEqual(inputs["gas_phone_card_sales"], "25.00")
        self.assertIsNone(inputs["gas_card_payment_sales"])
        self.assertIsNone(report.calculated_report["registers"]["gas_net_difference"])
        self.assertEqual(report.calculated_report["comparisons"]["phone_card_sales"], {
            "expected": "35.00", "actual": "35.00", "difference": "0.00", "status": "match",
        })

    def test_missing_normalized_children_are_backfilled_without_losing_blank_roll_counts(self):
        report = self.apps.get_model("reports", "DailyReport").objects.get(pk=self.report_id)
        rolls = report.scratch_off_rolls.order_by("slot_number")
        self.assertEqual(rolls.count(), 2)
        self.assertIsNone(rolls[0].ending_number)
        self.assertEqual(rolls[0].new_roll_counter, 3)
        self.assertEqual(rolls[1].last_night_number, 10)
        self.assertEqual(rolls[1].ending_number, 15)
        self.assertEqual(list(report.line_items.order_by("item_type").values_list("item_type", "amount", "description")), [
            ("safe_drop", Decimal("3.00"), "Original drop"),
            ("ticket", Decimal("23.00"), "Original ticket"),
            ("vendor_payout", Decimal("2.00"), "Original vendor"),
        ])

    def test_reversing_and_reapplying_migration_retains_original_phone_card_value(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        report = old_apps.get_model("reports", "DailyReport").objects.get(pk=self.report_id)
        self.assertEqual(report.gas_card_sales, Decimal("25.00"))
        self.assertEqual(report.calculated_report["inputs"]["gas_card_sales"], "25.00")
        self.assertEqual(report.calculated_report["registers"]["gas_net_difference"], "47.00")
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        report = executor.loader.project_state(self.migrate_to).apps.get_model("reports", "DailyReport").objects.get(pk=self.report_id)
        self.assertEqual(report.gas_phone_card_sales, Decimal("25.00"))
        self.assertIsNone(report.gas_card_payment_sales)
        self.assertEqual(report.scratch_off_rolls.count(), 2)
