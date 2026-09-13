from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase
from django.utils import timezone

from reports.lottery.catalog import SCRATCH_OFF_SLOTS
from reports.lottery.services import MONEY_FIELDS, calculate_daily_report, calculate_scratch_off_sales
from reports.models import DailyReport
from stores.models import Store, StoreMembership


def report_payload(report_date="2026-09-10", close_type="shift", **overrides):
    return {
        "report_date": report_date, "close_type": close_type, "close_label": "",
        **dict.fromkeys(MONEY_FIELDS, "0.00"),
        "scratch_offs": [], "bodega_ai_tickets": [], "tickets": [], "vendor_payouts": [], "safe_drops": [],
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
        self.assertEqual(result["slots"][1]["tickets_sold"], 52)
        self.assertEqual(calculate_scratch_off_sales([reading(None, 2)])["slots"][1]["tickets_sold"], 50)

    def test_ticket_amounts_are_signed_but_other_line_items_remain_nonnegative(self):
        calculated = calculate_daily_report(report_payload(
            gas_cash_sales="100.00",
            tickets=[{"amount": "+20.00"}, {"amount": "-8.00"}],
        ))
        self.assertEqual(calculated["registers"]["gas_net_difference"], Decimal("88.00"))
        self.assertEqual([item["amount"] for item in calculated["inputs"]["tickets"]], [
            Decimal("20.00"), Decimal("-8.00"),
        ])
        for field in ("bodega_ai_tickets", "vendor_payouts", "safe_drops"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                calculate_daily_report(report_payload(**{field: [{"amount": "-1.00"}]}))
        with self.assertRaises(ValidationError) as error:
            calculate_daily_report(report_payload(bodega_ai_tickets=[{"amount": "0.00"}]))
        self.assertIn("bodega_ai_tickets.0.amount", error.exception.message_dict)

    def test_bodega_ai_tickets_adjust_the_balance_without_changing_raw_net_difference(self):
        for raw, expected in (("-50.00", "-30.00"), ("5.00", "25.00")):
            with self.subTest(raw=raw):
                calculated = calculate_daily_report(report_payload(
                    bodega_net_difference=raw,
                    bodega_ai_tickets=[{"amount": "10.00"}, {"amount": "10.00", "description": "Second"}],
                ))
                self.assertEqual(calculated["inputs"]["bodega_net_difference"], Decimal(raw))
                self.assertEqual(calculated["registers"]["bodega_net_difference"], Decimal(raw))
                self.assertEqual(calculated["registers"]["bodega_ai_ticket_total"], Decimal("20.00"))
                self.assertEqual(calculated["registers"]["bodega_ai_register_balance"], Decimal(expected))
        empty = calculate_daily_report(report_payload(bodega_net_difference="-7.25"))
        self.assertEqual(empty["registers"]["bodega_ai_ticket_total"], Decimal("0.00"))
        self.assertEqual(empty["registers"]["bodega_ai_register_balance"], Decimal("-7.25"))

    def test_zero_baseline_conserves_every_catalog_counter_range(self):
        for slot in SCRATCH_OFF_SLOTS:
            with self.subTest(slot=slot.slot_number):
                middle = slot.max_ticket_number // 2
                first = calculate_scratch_off_sales([reading(middle, slot=slot.slot_number)])
                finished = calculate_scratch_off_sales([{
                    **reading(None, slot=slot.slot_number), "previous_number": middle,
                }])
                sold = first["slots"][slot.slot_number]["tickets_sold"] + finished["slots"][slot.slot_number]["tickets_sold"]
                self.assertEqual(sold, slot.max_ticket_number)
                replacement = calculate_scratch_off_sales([{
                    **reading(2, count=2, slot=slot.slot_number), "previous_number": middle,
                }])
                total_with_replacements = first["slots"][slot.slot_number]["tickets_sold"] + replacement["slots"][slot.slot_number]["tickets_sold"]
                self.assertEqual(total_with_replacements, 2 * slot.max_ticket_number + 4)
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

    def create(self, report_date="2026-09-10", close_type="shift", readings=None, **overrides):
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

    def test_shifts_chain_within_and_across_business_dates(self):
        self.create("2026-09-09", readings=[reading(10)])
        first = self.create(readings=[reading(12)])
        second = self.create(readings=[reading(15)])
        tomorrow = self.create("2026-09-11", readings=[reading(18)])
        self.assertEqual(
            [self.sales(report) for report in (first, second, tomorrow)],
            ["40.00", "60.00", "60.00"],
        )

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
        self.assertEqual(self.sales(resumed), "40.00")

    def test_initial_blank_does_not_invent_inventory_or_exhaust_a_roll(self):
        initial = self.create("2026-09-09", readings=[reading(None)])
        self.assertEqual(self.sales(initial), "0.00")
        self.assertFalse(DailyReport.objects.get(pk=initial["id"]).scratch_off_rolls.get().ending_exhausted)
        first_counter = self.create(readings=[reading(2)])
        self.assertEqual(self.sales(first_counter), "40.00")

    def test_daily_summary_sums_scratch_sales_and_carries_final_state(self):
        first = self.create(readings=[reading(20)])
        second = self.create(readings=[reading(None)])
        history = self.client.get("/api/reports/").json()
        summary = history["daily_summaries"][0]
        self.assertEqual(self.sales(first), "400.00")
        self.assertEqual(self.sales(second), "80.00")
        self.assertEqual(summary["scratch_off"]["sales"], "480.00")
        self.assertTrue(summary["scratch_off"]["final_state"]["1"]["ending_exhausted"])
        self.assertEqual(summary["scratch_off"]["slots"]["1"], {
            "tickets_sold": 24,
            "ticket_price": "20.00",
            "sales": "480.00",
            "new_roll_count": 0,
            "starting_number": 0,
            "ending_number": None,
            "ending_exhausted": True,
        })
        tomorrow = self.create("2026-09-11", readings=[reading(None)])
        self.assertEqual(self.sales(tomorrow), "0.00")

    def test_daily_summary_sums_every_catalog_slot_and_new_roll(self):
        self.create("2026-09-09", readings=[reading(5, slot=slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        first = self.create(readings=[reading(10, slot=slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        second = self.create(readings=[reading(2, 1, slot.slot_number) for slot in SCRATCH_OFF_SLOTS])
        summary = self.client.get("/api/reports/").json()["daily_summaries"][0]
        expected = Decimal(first["calculated"]["scratch_off"]["sales"]) + Decimal(
            second["calculated"]["scratch_off"]["sales"],
        )
        self.assertEqual(Decimal(summary["scratch_off"]["sales"]), expected)
        self.assertEqual(summary["scratch_off"]["total_new_rolls"], 20)
        self.assertEqual(summary["scratch_off"]["new_rolls_by_slot"], {
            str(slot.slot_number): 1 for slot in SCRATCH_OFF_SLOTS
        })

    def test_shift_and_daily_lottery_sales_include_scratch_offs_and_terminal_sales(self):
        self.create("2026-09-09", readings=[reading(5)])
        first = self.create(
            readings=[reading(10)], lottery_terminal_sales="100",
            bodega_lottery_sales="100", gas_lottery_sales="100",
        )
        second = self.create(
            readings=[reading(15)], lottery_terminal_sales="250",
            bodega_lottery_sales="125", gas_lottery_sales="125",
        )

        self.assertEqual(first["calculated"]["scratch_off"]["sales"], "100.00")
        self.assertEqual(first["calculated"]["comparisons"]["lottery_sales"], {
            "expected": "200.00", "actual": "200.00", "difference": "0.00", "status": "match",
        })
        self.assertEqual(second["calculated"]["terminal"]["shift_sales"], "150.00")
        self.assertEqual(second["calculated"]["scratch_off"]["sales"], "100.00")
        self.assertEqual(second["calculated"]["comparisons"]["lottery_sales"]["expected"], "250.00")

        summary = self.client.get("/api/reports/").json()["daily_summaries"][0]
        self.assertEqual(summary["terminal"]["final_cumulative_sales"], "250.00")
        self.assertEqual(summary["scratch_off"]["sales"], "200.00")
        self.assertEqual(summary["comparisons"]["lottery_sales"], {
            "expected": "450.00", "actual": "450.00", "difference": "0.00", "status": "match",
        })

    def test_cumulative_terminal_readings_are_derived_per_shift_and_summarized(self):
        first = self.create(
            lottery_terminal_sales="500", lottery_terminal_payout="100",
            bodega_lottery_sales="300", gas_lottery_sales="200",
            bodega_lottery_payout="60", gas_lottery_payout="40",
            phone_card_actual_sales="10", bodega_phone_card_sales="4", gas_phone_card_sales="6",
            bodega_net_difference="-50", bodega_ai_tickets=[{"amount": "10", "description": "First Bodega ticket"}],
            tickets=[{"amount": "5", "description": "First ticket"}],
        )
        second = self.create(
            lottery_terminal_sales="1200", lottery_terminal_payout="250",
            bodega_lottery_sales="400", gas_lottery_sales="300",
            bodega_lottery_payout="90", gas_lottery_payout="60",
            phone_card_actual_sales="20", bodega_phone_card_sales="8", gas_phone_card_sales="12",
            bodega_net_difference="5", bodega_ai_tickets=[{"amount": "10"}],
            safe_drops=[{"amount": "25"}], vendor_payouts=[{"amount": "7"}],
        )
        third = self.create(
            lottery_terminal_sales="1600", lottery_terminal_payout="320",
            bodega_lottery_sales="250", gas_lottery_sales="150",
            bodega_lottery_payout="40", gas_lottery_payout="30",
        )
        self.assertEqual(first["calculated"]["terminal"]["shift_sales"], "500.00")
        self.assertTrue(DailyReport.objects.get(pk=first["id"]).terminal_values_cumulative)
        self.assertEqual(second["calculated"]["terminal"]["previous_cumulative_sales"], "500.00")
        self.assertEqual(second["calculated"]["terminal"]["shift_sales"], "700.00")
        self.assertEqual(second["calculated"]["terminal"]["shift_payout"], "150.00")
        self.assertEqual(second["calculated"]["comparisons"]["lottery_sales"]["status"], "match")
        self.assertEqual(third["calculated"]["terminal"]["shift_sales"], "400.00")
        self.assertEqual(third["calculated"]["terminal"]["shift_payout"], "70.00")
        summary = self.client.get("/api/reports/").json()["daily_summaries"][0]
        self.assertEqual(summary["shift_count"], 3)
        self.assertEqual(summary["terminal"]["final_cumulative_sales"], "1600.00")
        self.assertEqual(summary["registers"]["lottery_sales"], "1600.00")
        self.assertEqual(summary["comparisons"]["lottery_sales"]["status"], "match")
        self.assertEqual(summary["comparisons"]["lottery_payout"]["status"], "match")
        self.assertEqual(summary["comparisons"]["phone_card_sales"]["status"], "match")
        self.assertEqual(summary["line_items"]["tickets"]["total"], "5.00")
        self.assertEqual(summary["line_items"]["bodega_ai_tickets"]["total"], "20.00")
        self.assertEqual(summary["registers"]["bodega_net_difference"], "-45.00")
        self.assertEqual(summary["registers"]["bodega_ai_ticket_total"], "20.00")
        self.assertEqual(summary["registers"]["bodega_ai_register_balance"], "-25.00")
        self.assertEqual(summary["line_items"]["safe_drops"]["total"], "25.00")
        self.assertEqual(summary["line_items"]["vendor_payouts"]["total"], "7.00")

    def test_legacy_per_shift_terminal_values_are_translated_without_rewriting_them(self):
        first = self.create(lottery_terminal_sales="500", lottery_terminal_payout="100")
        second = self.create(lottery_terminal_sales="1200", lottery_terminal_payout="250")
        DailyReport.objects.filter(pk=first["id"]).update(terminal_values_cumulative=False)
        DailyReport.objects.filter(pk=second["id"]).update(
            terminal_values_cumulative=False,
            lottery_terminal_sales="700",
            lottery_terminal_payout="150",
        )
        from reports.views import recalculate_store_history
        recalculate_store_history(self.store)
        translated = self.fetch(second)["calculated"]["terminal"]
        self.assertEqual(translated["cumulative_sales"], "1200.00")
        self.assertEqual(translated["shift_sales"], "700.00")
        stored = DailyReport.objects.get(pk=second["id"])
        self.assertEqual(stored.lottery_terminal_sales, Decimal("700.00"))
        self.assertFalse(stored.terminal_values_cumulative)

    def test_editing_earlier_cumulative_reading_recalculates_later_shift(self):
        first = self.create(lottery_terminal_sales="500", lottery_terminal_payout="100")
        second = self.create(lottery_terminal_sales="1200", lottery_terminal_payout="250")
        response = self.patch(first, {"lottery_terminal_sales": "550", "lottery_terminal_payout": "125"})
        self.assertEqual(response.status_code, 200, response.content)
        later = self.fetch(second)["calculated"]["terminal"]
        self.assertEqual(later["shift_sales"], "650.00")
        self.assertEqual(later["shift_payout"], "125.00")

    def test_invalid_earlier_terminal_edit_rolls_back_the_whole_history(self):
        first = self.create(lottery_terminal_sales="500", lottery_terminal_payout="100")
        second = self.create(lottery_terminal_sales="600", lottery_terminal_payout="150")
        response = self.patch(first, {"lottery_terminal_sales": "700"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("history", response.json()["errors"])
        self.assertEqual(self.fetch(first)["calculated"]["terminal"]["cumulative_sales"], "500.00")
        self.assertEqual(self.fetch(second)["calculated"]["terminal"]["shift_sales"], "100.00")

    def test_terminal_cumulative_readings_restart_on_each_business_date(self):
        self.create(lottery_terminal_sales="1600", lottery_terminal_payout="320")
        next_day = self.create(
            "2026-09-11", lottery_terminal_sales="200", lottery_terminal_payout="40",
        )
        self.assertEqual(next_day["calculated"]["terminal"]["shift_sales"], "200.00")
        self.assertEqual(next_day["calculated"]["terminal"]["shift_payout"], "40.00")

    def test_cumulative_terminal_reading_cannot_decrease(self):
        self.create(lottery_terminal_sales="500", lottery_terminal_payout="100")
        response = self.client.post(
            "/api/reports/",
            report_payload(lottery_terminal_sales="499.99", lottery_terminal_payout="99.99"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("lottery_terminal_sales", response.json()["errors"])

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

    def test_edit_that_moves_later_counter_backward_infers_rollover(self):
        prior = self.create("2026-09-09", readings=[reading(5)], tickets=[{"amount": "2", "description": "Original"}])
        later = self.create(readings=[reading(10)])
        response = self.patch(prior, {"scratch_offs": [reading(15)], "tickets": [{"amount": "9"}]})
        self.assertEqual(response.status_code, 200, response.content)
        refreshed = self.fetch(later)
        self.assertEqual(refreshed["calculated"]["scratch_off"]["sales"], "400.00")
        self.assertEqual(refreshed["calculated"]["normalized_scratch_offs"][0]["new_roll_count"], 1)

    def test_backdated_create_that_moves_later_counter_backward_infers_rollover(self):
        later = self.create(readings=[reading(10)])
        response = self.client.post("/api/reports/", report_payload("2026-09-09", scratch_offs=[reading(15)]), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(DailyReport.objects.count(), 2)
        self.assertEqual(self.sales(later), "400.00")
        saved = DailyReport.objects.get(pk=later["id"])
        self.assertEqual(saved.scratch_offs[0]["new_roll_count"], 1)
        self.assertEqual(saved.scratch_off_rolls.get().starting_number, 15)

    def test_moving_a_report_to_another_date_replays_old_and_new_positions(self):
        first = self.create("2026-09-08", readings=[reading(5)])
        second = self.create("2026-09-10", readings=[reading(15)])
        response = self.patch(first, {"report_date": "2026-09-11", "scratch_offs": [reading(18)]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.sales(second), "300.00")
        self.assertEqual(self.sales(first), "60.00")

    def test_legacy_missing_payment_remains_unknown_during_history_replay(self):
        prior = self.create("2026-09-09", readings=[reading(5)])
        later = self.create(readings=[reading(10)])
        DailyReport.objects.filter(pk=later["id"]).update(gas_card_payment_sales=None)
        response = self.patch(prior, {"scratch_offs": [reading(6)]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(self.fetch(later)["calculated"]["registers"]["gas_net_difference"])
        self.assertIsNone(self.fetch(later)["calculated"]["inputs"]["gas_card_payment_sales"])

    def test_new_manual_day_closes_and_close_type_changes_are_rejected(self):
        response = self.client.post(
            "/api/reports/", report_payload(close_type="day"), content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("automatically", str(response.json()["errors"]["close_type"]))
        shift = self.create()
        changed = self.patch(shift, {"close_type": "day"})
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(DailyReport.objects.get(pk=shift["id"]).close_type, "shift")

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
