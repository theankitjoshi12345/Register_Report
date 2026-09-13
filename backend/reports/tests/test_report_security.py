from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase

from reports.lottery.services import MAX_LINE_ITEMS
from reports.models import DailyReport
from reports.views import recalculate_store_history
from stores.models import Store, StoreMembership

from .test_report_history import reading, report_payload


class ReportSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store = Store.objects.get(pk=1)
        cls.other_store = Store.objects.create(name="Another store")
        cls.user = get_user_model().objects.create_user(username="report-security-user")
        StoreMembership.objects.create(store=cls.store, user=cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def post_report(self, **changes):
        return self.client.post(
            "/api/reports/", report_payload(**changes), content_type="application/json",
        )

    def test_oversized_line_item_arrays_are_rejected_without_writing(self):
        for field in ("bodega_ai_tickets", "tickets", "vendor_payouts", "safe_drops"):
            with self.subTest(field=field):
                response = self.post_report(**{field: [{"amount": "1.00"}] * (MAX_LINE_ITEMS + 1)})
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json()["errors"])
                self.assertFalse(DailyReport.objects.exists())

    def test_line_item_limit_accepts_boundary_and_preserves_signed_tickets(self):
        response = self.post_report(tickets=[{"amount": "-1.00"}] * MAX_LINE_ITEMS)
        self.assertEqual(response.status_code, 201, response.content)
        report = DailyReport.objects.get(pk=response.json()["id"])
        self.assertEqual(report.line_items.count(), MAX_LINE_ITEMS)
        self.assertEqual(report.calculated_report["registers"]["gas_net_difference"], f"{MAX_LINE_ITEMS}.00")

        bodega = self.post_report(
            report_date="2026-09-11",
            bodega_ai_tickets=[{"amount": "1.00"}] * MAX_LINE_ITEMS,
        )
        self.assertEqual(bodega.status_code, 201, bodega.content)
        self.assertEqual(
            bodega.json()["calculated"]["registers"]["bodega_ai_register_balance"],
            f"{MAX_LINE_ITEMS}.00",
        )

    def test_database_unsafe_text_is_rejected_as_a_field_error(self):
        for value in ("before\x00after", "\ud800", "\udfff"):
            for field in ("close_label", "bodega_ai_tickets", "tickets", "vendor_payouts", "safe_drops"):
                with self.subTest(value=repr(value), field=field):
                    changes = {field: value if field == "close_label" else [{"amount": "1.00", "description": value}]}
                    response = self.post_report(**changes)
                    self.assertEqual(response.status_code, 400, response.content)
                    error_field = field if field == "close_label" else f"{field}.0.description"
                    self.assertIn(error_field, response.json()["errors"])
                    self.assertFalse(DailyReport.objects.exists())

    def test_valid_unicode_labels_and_descriptions_are_preserved(self):
        response = self.post_report(close_label="Cierre de José 🧾", tickets=[{
            "amount": "-5.00", "description": "Pago de José 🧾",
        }])
        self.assertEqual(response.status_code, 201, response.content)
        report = DailyReport.objects.get(pk=response.json()["id"])
        self.assertEqual(report.close_label, "Cierre de José 🧾")
        self.assertEqual(report.line_items.get().description, "Pago de José 🧾")

    def test_failed_patch_preserves_saved_report_and_calculations(self):
        created = self.post_report(scratch_offs=[reading(6, slot=8)], tickets=[{"amount": "2.00"}])
        self.assertEqual(created.status_code, 201, created.content)
        report = DailyReport.objects.get(pk=created.json()["id"])
        original = deepcopy(report.calculated_report)
        for changes in (
            {"tickets": [{"amount": "9.00"}] * (MAX_LINE_ITEMS + 1)},
            {"close_label": "\x00"},
        ):
            with self.subTest(changes=list(changes)):
                response = self.client.patch(
                    f"/api/reports/{report.pk}/", changes, content_type="application/json",
                )
                self.assertEqual(response.status_code, 400, response.content)
                report.refresh_from_db()
                self.assertEqual(report.calculated_report, original)
                self.assertEqual(report.close_label, "")
                self.assertEqual(str(report.line_items.get().amount), "2.00")

    def test_legacy_large_collections_can_be_recalculated_and_partially_edited(self):
        created = self.post_report()
        self.assertEqual(created.status_code, 201, created.content)
        report = DailyReport.objects.get(pk=created.json()["id"])
        # Simulate a report accepted before external collection limits existed.
        report.tickets = [{"amount": "1.00", "description": ""}] * (MAX_LINE_ITEMS + 1)
        report.save(update_fields=["tickets"])
        self.assertEqual(recalculate_store_history(self.store), 1)
        url = f"/api/reports/{report.pk}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.patch(url, {"close_label": "Corrected"}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        report.refresh_from_db()
        self.assertEqual(report.close_label, "Corrected")
        self.assertEqual(len(report.tickets), MAX_LINE_ITEMS + 1)
        self.assertEqual(report.line_items.count(), MAX_LINE_ITEMS + 1)

    def test_client_cannot_overwrite_store_or_calculated_history(self):
        response = self.post_report(
            store_id=self.other_store.pk, calculated_report={"tampered": True},
            scratch_offs=[{
                **reading(6, slot=8), "previous_number": 5, "previous_exhausted": True,
                "initial_roll_active": True, "ticket_price": "999.00",
            }],
        )
        self.assertEqual(response.status_code, 201, response.content)
        report = DailyReport.objects.get(pk=response.json()["id"])
        self.assertEqual(report.store_id, self.store.pk)
        slot = report.calculated_report["scratch_off"]["slots"]["8"]
        self.assertEqual(slot["starting_number"], 0)
        self.assertEqual(slot["ticket_price"], "3.00")
        self.assertEqual(slot["sales"], "18.00")
        self.assertNotIn("tampered", report.calculated_report)
