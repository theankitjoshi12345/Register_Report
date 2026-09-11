from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase
from django.utils import timezone

from reports.lottery.catalog import SCRATCH_OFF_SLOTS
from reports.lottery.services import MONEY_FIELDS, calculate_daily_report, calculate_scratch_off_sales
from reports.models import DailyReport
from stores.models import Store, StoreMembership


def report_payload(report_date="2026-09-10", close_type="day", **overrides):
    return {
        "report_date": report_date, "close_type": close_type, "close_label": "",
        **dict.fromkeys(MONEY_FIELDS, "0.00"),
        "scratch_offs": [], "tickets": [], "vendor_payouts": [], "safe_drops": [],
        **overrides,
    }


def reading(ending, count=0, slot=1):
    return {"slot_number": slot, "ending_number": ending, "new_roll_count": count}


class ReportInputTests(SimpleTestCase):
    def test_phone_cards_and_independent_payments_have_separate_effects(self):
        calculated = calculate_daily_report(report_payload(
            phone_card_actual_sales="35", bodega_phone_card_sales="10", gas_phone_card_sales="25",
            gas_card_payment_sales="80", gas_cash_sales="100", bodega_net_difference="-1.25",
        ))
        self.assertEqual(calculated["comparisons"]["phone_card_sales"]["status"], "match")
        self.assertEqual(calculated["registers"]["gas_net_difference"], Decimal("20.00"))
        self.assertEqual(calculated["registers"]["bodega_net_difference"], Decimal("-1.25"))

    def test_every_money_field_enforces_precision_type_and_database_size(self):
        for field in MONEY_FIELDS:
            for invalid in (None, "", " ", True, [], {}, "NaN", "Infinity", "1.001", "10000000000", "1e999999", "1e999999999", "-1e999999999"):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValidationError):
                    calculate_daily_report(report_payload(**{field: invalid}))
            if field != "bodega_net_difference":
                with self.subTest(field=field), self.assertRaises(ValidationError):
                    calculate_daily_report(report_payload(**{field: "-0.01"}))
        self.assertEqual(calculate_daily_report(report_payload(gas_cash_sales="9999999999.99"))["inputs"]["gas_cash_sales"], Decimal("9999999999.99"))

    def test_multiple_initial_new_rolls_count_completed_rolls(self):
        result = calculate_scratch_off_sales([reading(2, 3)])
        self.assertEqual(result["slots"][1]["tickets_sold"], 53)
        self.assertEqual(calculate_scratch_off_sales([reading(None, 2)])["slots"][1]["tickets_sold"], 50)

    def test_last_sold_convention_conserves_every_catalog_roll(self):
        for slot in SCRATCH_OFF_SLOTS:
            with self.subTest(slot=slot.slot_number):
                middle = slot.max_ticket_number // 2
                first = calculate_scratch_off_sales([reading(middle, slot=slot.slot_number)])
                finished = calculate_scratch_off_sales([{
                    **reading(None, slot=slot.slot_number), "previous_number": middle,
                }])
                sold = first["slots"][slot.slot_number]["tickets_sold"] + finished["slots"][slot.slot_number]["tickets_sold"]
                self.assertEqual(sold, slot.max_ticket_number + 1)
                replacement = calculate_scratch_off_sales([{
                    **reading(2, count=2, slot=slot.slot_number), "previous_number": middle,
                }])
                total_with_replacements = first["slots"][slot.slot_number]["tickets_sold"] + replacement["slots"][slot.slot_number]["tickets_sold"]
                self.assertEqual(total_with_replacements, 2 * (slot.max_ticket_number + 1) + 3)
                day = calculate_scratch_off_sales([{
                    **reading(2, count=2, slot=slot.slot_number), "initial_roll_active": True,
                }])
                self.assertEqual(day["slots"][slot.slot_number]["tickets_sold"], total_with_replacements)
                last_ticket = calculate_scratch_off_sales([{
                    **reading(None, slot=slot.slot_number), "previous_number": slot.max_ticket_number,
                }])["slots"][slot.slot_number]
                self.assertEqual(last_ticket["tickets_sold"], 0)
                self.assertTrue(last_ticket["ending_exhausted"])

    def test_nested_field_errors_match_frontend_paths(self):
        with self.assertRaises(ValidationError) as error:
            calculate_daily_report(report_payload(tickets=[{"amount": "bad"}]))
        self.assertIn("tickets.0.amount", error.exception.message_dict)
        with self.assertRaises(ValidationError) as error:
            calculate_daily_report(report_payload(scratch_offs=[reading(25)]))
        self.assertIn("scratch_offs.0.ending_number", error.exception.message_dict)


class ReportHistoryTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(pk=1)
        self.user = get_user_model().objects.create_user(username="history-user")
        StoreMembership.objects.create(store=self.store, user=self.user)
        self.client.force_login(self.user)

    def create(self, report_date="2026-09-10", close_type="day", readings=None, **overrides):
        payload = report_payload(report_date, close_type, **overrides)
        if readings is not None:
            payload["scratch_offs"] = readings
        response = self.client.post("/api/reports/", payload, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def patch(self, report, payload):
        return self.client.patch(f"/api/reports/{report['id']}/", payload, content_type="application/json")

    def fetch(self, report):
        response = self.client.get(f"/api/reports/{report['id']}/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def sales(self, report):
        return self.fetch(report)["calculated"]["scratch_off"]["sales"]

    def test_shifts_chain_but_day_close_uses_previous_date(self):
        self.create("2026-09-09", readings=[reading(10)])
        first = self.create(close_type="shift", readings=[reading(12)])
        second = self.create(close_type="shift", readings=[reading(15)])
        day = self.create(readings=[reading(16)])
        tomorrow = self.create("2026-09-11", close_type="shift", readings=[reading(18)])
        self.assertEqual([self.sales(report) for report in (first, second, day, tomorrow)], ["40.00", "60.00", "120.00", "40.00"])

    def test_day_created_before_shifts_still_provides_following_date_baseline(self):
        self.create("2026-09-09", readings=[reading(10)])
        day = self.create(readings=[reading(16)])
        self.create(close_type="shift", readings=[reading(12)])
        tomorrow = self.create("2026-09-11", readings=[reading(18)])
        self.assertEqual(self.sales(day), "120.00")
        self.assertEqual(self.sales(tomorrow), "40.00")

    def test_tied_shift_creation_times_use_id_order(self):
        self.create("2026-09-09", readings=[reading(10)])
        first = self.create(close_type="shift", readings=[reading(12)])
        second = self.create(close_type="shift", readings=[reading(15)])
        DailyReport.objects.filter(pk__in=[first["id"], second["id"]]).update(created_at=timezone.now())
        response = self.patch(first, {"close_label": "Morning"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.sales(second), "60.00")

    def test_omitted_slots_carry_across_reports_and_dates(self):
        self.create("2026-09-08", readings=[reading(5), reading(10, slot=4)])
        self.create("2026-09-09", readings=[reading(12, slot=4)])
        close = self.create(readings=[reading(8)])
        self.assertEqual(self.sales(close), "60.00")

    def test_exhausted_slots_are_saved_and_never_counted_twice(self):
        self.create("2026-09-08", readings=[reading(20)])
        exhausted = self.create("2026-09-09", readings=[reading(None)])
        repeated = self.create(readings=[reading(None)])
        self.assertEqual(self.sales(exhausted), "80.00")
        self.assertEqual(self.sales(repeated), "0.00")
        roll = DailyReport.objects.get(pk=exhausted["id"]).scratch_off_rolls.get()
        self.assertIsNone(roll.ending_number)
        self.assertTrue(roll.ending_exhausted)
        bad = self.client.post("/api/reports/", report_payload("2026-09-11", scratch_offs=[reading(2)]), content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        resumed = self.create("2026-09-11", readings=[reading(2, 1)])
        self.assertEqual(self.sales(resumed), "60.00")

    def test_initial_blank_does_not_invent_inventory_or_exhaust_a_roll(self):
        initial = self.create("2026-09-09", readings=[reading(None)])
        self.assertEqual(self.sales(initial), "0.00")
        self.assertFalse(DailyReport.objects.get(pk=initial["id"]).scratch_off_rolls.get().ending_exhausted)
        first_counter = self.create(readings=[reading(2)])
        self.assertEqual(self.sales(first_counter), "60.00")

    def test_first_day_exhausted_shift_can_be_closed_for_the_whole_day(self):
        self.create(close_type="shift", readings=[reading(20)])
        self.create(close_type="shift", readings=[reading(None)])
        day = self.create(readings=[reading(None)])
        self.assertEqual(self.sales(day), "500.00")
        tomorrow = self.create("2026-09-11", readings=[reading(None)])
        self.assertEqual(self.sales(tomorrow), "0.00")

    def test_first_day_shift_sales_equal_day_sales_when_roll_is_exhausted(self):
        first = self.create(close_type="shift", readings=[reading(20)])
        second = self.create(close_type="shift", readings=[reading(None)])
        day = self.create(readings=[reading(None)])
        self.assertEqual(self.sales(first), "420.00")
        self.assertEqual(self.sales(second), "80.00")
        self.assertEqual(Decimal(self.sales(first)) + Decimal(self.sales(second)), Decimal(self.sales(day)))

    def test_first_day_shift_sales_equal_day_sales_with_replacement_rolls(self):
        first = self.create(close_type="shift", readings=[reading(20)])
        second = self.create(close_type="shift", readings=[reading(2, 2)])
        day = self.create(readings=[reading(2, 2)])
        self.assertEqual(Decimal(self.sales(first)) + Decimal(self.sales(second)), Decimal(self.sales(day)))
        self.assertEqual(self.sales(day), "1060.00")

    def test_every_catalog_slots_shift_sales_match_full_day_sales(self):
        self.create("2026-09-09", readings=[reading(5, slot=slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        first = self.create(close_type="shift", readings=[reading(10, slot=slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        second = self.create(close_type="shift", readings=[reading(2, 1, slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        day = self.create(readings=[reading(2, 1, slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        for slot in SCRATCH_OFF_SLOTS:
            with self.subTest(slot=slot.slot_number):
                first_sales = Decimal(first["calculated"]["scratch_off"]["slots"][str(slot.slot_number)]["sales"])
                second_sales = Decimal(second["calculated"]["scratch_off"]["slots"][str(slot.slot_number)]["sales"])
                day_sales = Decimal(day["calculated"]["scratch_off"]["slots"][str(slot.slot_number)]["sales"])
                self.assertEqual(first_sales + second_sales, day_sales)

    def test_day_new_roll_count_is_cumulative_across_shifts(self):
        self.create("2026-09-09", readings=[reading(20)])
        self.create(close_type="shift", readings=[reading(2, 1)])
        self.create(close_type="shift", readings=[reading(1, 1)])
        invalid = self.client.post("/api/reports/", report_payload(scratch_offs=[reading(3, 1)]), content_type="application/json")
        self.assertEqual(invalid.status_code, 400)
        day = self.create(readings=[reading(1, 2)])
        self.assertEqual(self.sales(day), "620.00")

    def test_backdated_create_recalculates_later_reports(self):
        self.create("2026-09-08", readings=[reading(5)])
        later = self.create(readings=[reading(15)])
        self.assertEqual(self.sales(later), "200.00")
        self.create("2026-09-09", readings=[reading(10)])
        self.assertEqual(self.sales(later), "100.00")
        self.assertEqual(DailyReport.objects.get(pk=later["id"]).scratch_off_rolls.get().last_night_number, 10)

    def test_partial_patch_preserves_inputs_and_recalculates_later_reports(self):
        prior = self.create("2026-09-09", readings=[reading(5)], tickets=[{"amount": "2", "description": "Keep"}], gas_cash_sales="10")
        later = self.create(readings=[reading(15)])
        response = self.patch(prior, {"scratch_offs": [reading(10)], "close_label": "Corrected"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.sales(later), "100.00")
        self.assertEqual(response.json()["calculated"]["inputs"]["gas_cash_sales"], "10.00")
        self.assertEqual(response.json()["calculated"]["normalized_line_items"][0]["description"], "Keep")

    def test_incompatible_edit_rolls_back_all_inputs_and_normalized_rows(self):
        prior = self.create("2026-09-09", readings=[reading(5)], tickets=[{"amount": "2", "description": "Original"}])
        later = self.create(readings=[reading(10)])
        before_prior, before_later = self.fetch(prior), self.fetch(later)
        response = self.patch(prior, {"scratch_offs": [reading(15)], "tickets": [{"amount": "9"}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(later["id"]), str(response.json()))
        self.assertEqual(self.fetch(prior), before_prior)
        self.assertEqual(self.fetch(later), before_later)

    def test_incompatible_backdated_create_leaves_no_report(self):
        later = self.create(readings=[reading(10)])
        response = self.client.post("/api/reports/", report_payload("2026-09-09", scratch_offs=[reading(15)]), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DailyReport.objects.count(), 1)
        self.assertEqual(self.sales(later), "220.00")

    def test_moving_a_report_to_another_date_replays_old_and_new_positions(self):
        first = self.create("2026-09-08", readings=[reading(5)])
        second = self.create("2026-09-10", readings=[reading(15)])
        response = self.patch(first, {"report_date": "2026-09-11", "scratch_offs": [reading(18)]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.sales(second), "320.00")
        self.assertEqual(self.sales(first), "60.00")

    def test_legacy_missing_payment_remains_unknown_during_history_replay(self):
        prior = self.create("2026-09-09", readings=[reading(5)])
        later = self.create(readings=[reading(10)])
        DailyReport.objects.filter(pk=later["id"]).update(gas_card_payment_sales=None)
        response = self.patch(prior, {"scratch_offs": [reading(6)]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(self.fetch(later)["calculated"]["registers"]["gas_net_difference"])
        self.assertIsNone(self.fetch(later)["calculated"]["inputs"]["gas_card_payment_sales"])

    def test_database_prevents_duplicate_day_closes(self):
        day = self.create()
        report = DailyReport.objects.get(pk=day["id"])
        report.pk = None
        with self.assertRaises(IntegrityError), transaction.atomic():
            report.save()

    def test_invalid_json_and_payload_shapes_return_400(self):
        for body in ("{", "[]", "null", "42", '"text"', '{"gas_cash_sales": NaN}', b"\xff", "[" * 1100 + "0" + "]" * 1100):
            with self.subTest(body=body):
                response = self.client.post("/api/reports/", body, content_type="application/json")
                self.assertEqual(response.status_code, 400, response.content)
        for field, invalids in (
            ("report_date", [None, [], {}, True, "20260910", "2026-02-30"]),
            ("close_type", [None, [], {}, True, "night"]),
            ("close_label", [None, [], {}, "x" * 81]),
            ("scratch_offs", [None, {}, "bad", [None], [{"slot_number": []}], [reading(2), reading(3)]]),
            ("tickets", [None, {}, "bad", [1], [{"amount": "1", "description": {}}], [{"amount": "1", "description": "x" * 256}]]),
        ):
            for invalid in invalids:
                with self.subTest(field=field, invalid=invalid):
                    response = self.client.post("/api/reports/", report_payload(**{field: invalid}), content_type="application/json")
                    self.assertEqual(response.status_code, 400, response.content)
        for invalid in (-1, 32767, True, 1.5, "2", [], {}):
            with self.subTest(new_roll_count=invalid):
                response = self.client.post("/api/reports/", report_payload(scratch_offs=[reading(2, invalid)]), content_type="application/json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(DailyReport.objects.count(), 0)
