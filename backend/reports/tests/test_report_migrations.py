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


class ShiftTerminalCompatibilityMigrationTests(TransactionTestCase):
    migrate_from = [("reports", "0006_signed_ticket_amounts"), ("stores", "0002_loginattemptbucket")]
    migrate_to = [("reports", "0007_cumulative_shift_terminal_readings"), ("stores", "0002_loginattemptbucket")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        store, _ = old_apps.get_model("stores", "Store").objects.get_or_create(
            pk=1, defaults={"name": "Main store"},
        )
        Report = old_apps.get_model("reports", "DailyReport")
        values = {
            "phone_card_actual_sales": "0.00", "bodega_net_difference": "0.00",
            "bodega_lottery_sales": "0.00", "bodega_lottery_payout": "0.00",
            "bodega_phone_card_sales": "0.00", "bodega_gas_sales": "0.00",
            "gas_cash_sales": "0.00", "gas_lottery_sales": "0.00",
            "gas_lottery_payout": "0.00", "gas_phone_card_sales": "0.00",
            "gas_card_payment_sales": "0.00",
        }
        self.shift_ids = [
            Report.objects.create(
                store=store, report_date="2026-09-10", close_type="shift",
                lottery_terminal_sales=sales, lottery_terminal_payout=payout, **values,
            ).pk
            for sales, payout in [("500.00", "100.00"), ("700.00", "150.00"), ("400.00", "70.00")]
        ]
        self.next_date_id = Report.objects.create(
            store=store, report_date="2026-09-11", close_type="shift",
            lottery_terminal_sales="200.00", lottery_terminal_payout="40.00", **values,
        ).pk
        self.legacy_day_id = Report.objects.create(
            store=store, report_date="2026-09-10", close_type="day",
            lottery_terminal_sales="999.00", lottery_terminal_payout="88.00", **values,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_shift_amounts_remain_unchanged_and_are_marked_legacy(self):
        Report = self.apps.get_model("reports", "DailyReport")
        shifts = Report.objects.filter(pk__in=self.shift_ids).order_by("created_at", "id")
        self.assertEqual(
            list(shifts.values_list("lottery_terminal_sales", "lottery_terminal_payout")),
            [
                (Decimal("500.00"), Decimal("100.00")),
                (Decimal("700.00"), Decimal("150.00")),
                (Decimal("400.00"), Decimal("70.00")),
            ],
        )
        self.assertEqual(list(shifts.values_list("terminal_values_cumulative", flat=True)), [False, False, False])
        next_date = Report.objects.get(pk=self.next_date_id)
        self.assertEqual(next_date.lottery_terminal_sales, Decimal("200.00"))
        legacy_day = Report.objects.get(pk=self.legacy_day_id)
        self.assertEqual(legacy_day.lottery_terminal_sales, Decimal("999.00"))

    def test_reverse_removes_marker_without_changing_amounts(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        Report = executor.loader.project_state(self.migrate_from).apps.get_model("reports", "DailyReport")
        shifts = Report.objects.filter(pk__in=self.shift_ids).order_by("created_at", "id")
        self.assertEqual(
            list(shifts.values_list("lottery_terminal_sales", "lottery_terminal_payout")),
            [
                (Decimal("500.00"), Decimal("100.00")),
                (Decimal("700.00"), Decimal("150.00")),
                (Decimal("400.00"), Decimal("70.00")),
            ],
        )
