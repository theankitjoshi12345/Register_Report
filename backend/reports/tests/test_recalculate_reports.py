from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from reports.lottery.services import MONEY_FIELDS
from reports.models import DailyReport
from stores.models import Store


class RecalculateReportsCommandTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(pk=1)

    def legacy_report(self, report_date, ending, *, store=None):
        return DailyReport.objects.create(
            store=store or self.store, report_date=report_date, close_type="day",
            **{field: "0.00" for field in MONEY_FIELDS if field != "gas_card_payment_sales"},
            gas_card_payment_sales=None,
            scratch_offs=[{"slot_number": 1, "ending_number": ending, "new_roll_count": 0}],
            calculated_report={"old_snapshot": True},
        )

    def test_dry_run_validates_without_changing_snapshots_or_children(self):
        report = self.legacy_report("2026-09-10", 20)
        stdout = StringIO()
        call_command("recalculate_reports", store=self.store.pk, dry_run=True, stdout=stdout)
        report.refresh_from_db()
        self.assertEqual(report.calculated_report, {"old_snapshot": True})
        self.assertFalse(report.scratch_off_rolls.exists())
        self.assertIn("Validated 1 report(s)", stdout.getvalue())
        self.assertIn("No changes saved", stdout.getvalue())

    def test_recalculation_updates_totals_and_exhaustion_without_inventing_card_payments(self):
        self.legacy_report("2026-09-09", 20)
        report = self.legacy_report("2026-09-10", None)
        original_created_at = report.created_at
        stdout = StringIO()
        call_command("recalculate_reports", store=self.store.pk, stdout=stdout)
        report.refresh_from_db()
        self.assertEqual(report.calculated_report["scratch_off"]["sales"], "80.00")
        self.assertIsNone(report.calculated_report["registers"]["gas_net_difference"])
        self.assertEqual(report.scratch_offs, [{"slot_number": 1, "ending_number": None, "new_roll_count": 0}])
        self.assertEqual(report.created_at, original_created_at)
        self.assertTrue(report.scratch_off_rolls.get().ending_exhausted)
        self.assertIn("Recalculated 2 report(s)", stdout.getvalue())

    def test_conflicting_history_rolls_back_the_whole_store(self):
        earlier = self.legacy_report("2026-09-09", 20)
        later = self.legacy_report("2026-09-10", 5)
        with self.assertRaises(CommandError) as error:
            call_command("recalculate_reports", store=self.store.pk, stdout=StringIO())
        self.assertIn(str(later.pk), str(error.exception))
        earlier.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(earlier.calculated_report, {"old_snapshot": True})
        self.assertEqual(later.calculated_report, {"old_snapshot": True})
        self.assertFalse(earlier.scratch_off_rolls.exists())
        self.assertFalse(later.scratch_off_rolls.exists())

    def test_store_selection_leaves_other_stores_unchanged(self):
        first = self.legacy_report("2026-09-10", 20)
        other_store = Store.objects.create(name="Other store")
        other = self.legacy_report("2026-09-10", 2, store=other_store)
        call_command("recalculate_reports", store=self.store.pk, stdout=StringIO())
        first.refresh_from_db()
        other.refresh_from_db()
        self.assertIn("scratch_off", first.calculated_report)
        self.assertEqual(other.calculated_report, {"old_snapshot": True})

    def test_unknown_store_is_an_actionable_error(self):
        with self.assertRaisesMessage(CommandError, "does not exist"):
            call_command("recalculate_reports", store=999, stdout=StringIO())
