from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from reports.lottery.services import (
    calculate_daily_report,
    calculate_scratch_off_sales,
    summarize_register_totals,
)


class ScratchOffSalesTests(SimpleTestCase):
    def test_nightly_sales_use_the_previous_database_number(self):
        result = calculate_scratch_off_sales(
            [{
                "slot_number": 4,
                "previous_number": 10,
                "ending_number": 15,
            }]
        )

        self.assertEqual(result["slots"][4]["tickets_sold"], 5)
        self.assertEqual(result["slots"][4]["starting_number"], 10)
        self.assertEqual(result["slots"][4]["ending_number"], 15)
        self.assertEqual(result["total_sales"], Decimal("25.00"))

    def test_empty_ending_counter_counts_the_rest_of_the_roll(self):
        result = calculate_scratch_off_sales(
            [{
                "slot_number": 1,
                "ending_number": None,
                "previous_number": 20,
            }]
        )

        self.assertEqual(result["slots"][1]["tickets_sold"], 4)
        self.assertEqual(result["total_sales"], Decimal("80.00"))

    def test_new_roll_counts_remaining_old_roll_and_current_roll(self):
        result = calculate_scratch_off_sales(
            [{"slot_number": 1, "previous_number": 20, "ending_number": 2, "new_roll": True}]
        )

        self.assertEqual(result["slots"][1]["tickets_sold"], 7)
        self.assertEqual(result["total_sales"], Decimal("140.00"))

    def test_missing_prior_number_uses_zero_as_the_starting_counter(self):
        result = calculate_scratch_off_sales(
            [{"slot_number": 8, "previous_number": None, "ending_number": 6, "new_roll_count": 1}]
        )

        self.assertEqual(result["slots"][8]["starting_number"], 0)
        self.assertEqual(result["slots"][8]["tickets_sold"], 6)
        self.assertEqual(result["slots"][8]["sales"], Decimal("18.00"))
        self.assertEqual(result["total_sales"], Decimal("18.00"))

    def test_sales_use_the_difference_between_closing_and_opening_numbers(self):
        result = calculate_scratch_off_sales(
            [{"slot_number": 1, "previous_number": "005", "ending_number": "012"}]
        )

        self.assertEqual(result["slots"][1]["tickets_sold"], 7)
        self.assertEqual(result["slots"][1]["sales"], Decimal("140.00"))
        self.assertEqual(result["total_sales"], Decimal("140.00"))

    def test_multiple_slots_use_their_catalog_prices(self):
        result = calculate_scratch_off_sales(
            [
                {"slot_number": 1, "previous_number": 0, "ending_number": 2},
                {"slot_number": 4, "previous_number": 10, "ending_number": 13},
            ]
        )

        self.assertEqual(result["total_sales"], Decimal("55.00"))

    def test_blank_pairs_are_zero_sales(self):
        result = calculate_scratch_off_sales(
            [{"slot_number": 1, "previous_number": None, "ending_number": " "}]
        )

        self.assertEqual(result["total_sales"], Decimal("0.00"))

    def test_lower_counter_automatically_adds_one_new_roll(self):
        result = calculate_scratch_off_sales(
            [{"slot_number": 1, "previous_number": 12, "ending_number": 5}]
        )

        self.assertEqual(result["slots"][1]["new_roll_count"], 1)
        self.assertEqual(result["slots"][1]["tickets_sold"], 18)
        self.assertEqual(result["slots"][1]["sales"], Decimal("360.00"))


class DailyReportCalculationTests(SimpleTestCase):
    def test_all_report_comparisons_and_gas_difference_are_calculated(self):
        result = calculate_daily_report(
            {
                "lottery_terminal_sales": "100.00",
                "lottery_terminal_payout": "25.00",
                "phone_card_actual_sales": "60.00",
                "bodega_net_difference": "-1.25",
                "bodega_lottery_sales": "20.00",
                "bodega_lottery_payout": "10.00",
                "bodega_phone_card_sales": "20.00",
                "bodega_gas_sales": "100.00",
                "gas_cash_sales": "500.00",
                "gas_lottery_sales": "80.00",
                "gas_lottery_payout": "15.00",
                "gas_phone_card_sales": "40.00",
                "gas_card_payment_sales": "40.00",
                "scratch_offs": [{"slot_number": 1, "ending_number": 2}],
                "tickets": [{"amount": "30.00", "description": "Regular"}],
                "vendor_payouts": [{"amount": "25.00"}],
                "safe_drops": [{"amount": "50.00"}],
            }
        )

        self.assertEqual(result["comparisons"]["phone_card_sales"]["status"], "match")
        self.assertEqual(result["comparisons"]["lottery_sales"]["status"], "match")
        self.assertEqual(result["comparisons"]["lottery_payout"]["status"], "match")
        self.assertEqual(result["registers"]["gas_net_difference"], Decimal("255.00"))


class DailyReportApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from stores.models import Store, StoreMembership
        self.user = get_user_model().objects.create_user(username="report-user", password="test-password")
        self.store = Store.objects.get(pk=1)
        StoreMembership.objects.create(store=self.store, user=self.user)
        self.client.force_login(self.user)

    def test_create_and_list_report(self):
        payload = {
            "report_date": "2026-09-10",
            "close_type": "shift",
            "close_label": "",
            "lottery_terminal_sales": "0.00",
            "lottery_terminal_payout": "0.00",
            "phone_card_actual_sales": "0.00",
            "bodega_net_difference": "-1.25",
            "bodega_lottery_sales": "0.00",
            "bodega_lottery_payout": "0.00",
            "bodega_phone_card_sales": "0.00",
            "bodega_gas_sales": "0.00",
            "gas_cash_sales": "0.00",
            "gas_lottery_sales": "0.00",
            "gas_lottery_payout": "0.00",
            "gas_phone_card_sales": "0.00", "gas_card_payment_sales": "0.00",
            "scratch_offs": [],
            "tickets": [],
            "vendor_payouts": [],
            "safe_drops": [],
        }

        response = self.client.post("/api/reports/", payload, content_type="application/json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["calculated"]["registers"]["gas_net_difference"], "0.00")
        self.assertEqual(self.client.get("/api/reports/").json()["reports"][0]["report_date"], "2026-09-10")

    def test_update_report_recalculates_and_replaces_normalized_items(self):
        payload = {
            "report_date": "2026-09-10", "close_type": "shift", "close_label": "",
            "lottery_terminal_sales": "0.00", "lottery_terminal_payout": "0.00", "phone_card_actual_sales": "0.00",
            "bodega_net_difference": "-1.25", "bodega_lottery_sales": "0.00", "bodega_lottery_payout": "0.00",
            "bodega_phone_card_sales": "0.00", "bodega_gas_sales": "0.00", "gas_cash_sales": "100.00",
            "gas_lottery_sales": "0.00", "gas_lottery_payout": "0.00", "gas_phone_card_sales": "0.00", "gas_card_payment_sales": "0.00",
            "scratch_offs": [], "tickets": [{"amount": "12.00", "description": "First"}],
            "vendor_payouts": [], "safe_drops": [],
        }
        created = self.client.post("/api/reports/", payload, content_type="application/json").json()
        payload["tickets"] = [{"amount": "-22.00", "description": "Customer paid"}]

        response = self.client.patch(f"/api/reports/{created['id']}/", payload, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["calculated"]["normalized_line_items"][0]["amount"], "-22.00")
        self.assertEqual(response.json()["calculated"]["registers"]["gas_net_difference"], "122.00")


class LotteryTotalsTests(SimpleTestCase):
    def setUp(self):
        self.values = {
            "terminal_instant_sales": "100.30",
            "terminal_payout": "25.30",
            "gas_lottery_sales": "60.10",
            "gas_lottery_payout": "10.10",
            "bodega_ai_lottery_sales": "40.20",
            "bodega_ai_lottery_payout": "15.20",
        }

    def test_register_totals_use_exact_decimal_addition(self):
        result = summarize_register_totals(self.values)

        self.assertEqual(result["register_totals"]["lottery_sales"], Decimal("100.30"))
        self.assertEqual(result["register_totals"]["lottery_payout"], Decimal("25.30"))
        self.assertEqual(result["payout_comparison"]["status"], "match")
        self.assertEqual(result["payout_comparison"]["difference"], Decimal("0.00"))

    def test_a_one_cent_payout_discrepancy_is_not_lost(self):
        for recorded, difference in [("15.19", "-0.01"), ("15.21", "0.01")]:
            with self.subTest(recorded=recorded):
                result = summarize_register_totals(
                    {**self.values, "bodega_ai_lottery_payout": recorded}
                )
                comparison = result["payout_comparison"]
                self.assertEqual(comparison["status"], "mismatch")
                self.assertEqual(comparison["difference"], Decimal(difference))

    def test_explicit_zero_amounts_are_valid(self):
        result = summarize_register_totals(dict.fromkeys(self.values, 0))

        self.assertEqual(result["register_totals"]["lottery_sales"], Decimal("0"))
        self.assertEqual(result["payout_comparison"]["status"], "match")

    def test_invalid_or_blank_money_does_not_silently_become_zero(self):
        for field in self.values:
            for invalid in (None, "", " ", True, "NaN", "Infinity", "-0.01", "1.001", "10000000000.00"):
                with self.subTest(field=field, value=invalid):
                    with self.assertRaises(ValidationError) as caught:
                        summarize_register_totals({**self.values, field: invalid})
                    self.assertIn(field, caught.exception.message_dict)

    def test_missing_register_amount_is_rejected(self):
        values = self.values.copy()
        del values["gas_lottery_sales"]

        with self.assertRaises(ValidationError) as caught:
            summarize_register_totals(values)

        self.assertIn("gas_lottery_sales", caught.exception.message_dict)
