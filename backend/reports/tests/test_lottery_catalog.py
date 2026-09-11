from dataclasses import FrozenInstanceError
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from reports.lottery.catalog import (
    SCRATCH_OFF_SLOTS,
    get_slot,
    validate_ticket_number,
)


class ScratchOffCatalogTests(SimpleTestCase):
    def test_all_twenty_slots_match_the_store_catalog(self):
        expected = (
            [(Decimal("20.00"), 24)]
            + [(Decimal("10.00"), 24)] * 2
            + [(Decimal("5.00"), 49)] * 4
            + [(Decimal("3.00"), 74)] * 3
            + [(Decimal("2.00"), 124)] * 5
            + [(Decimal("1.00"), 249)] * 5
        )

        self.assertEqual(len(SCRATCH_OFF_SLOTS), 20)
        for slot_number, (price, maximum) in enumerate(expected, start=1):
            with self.subTest(slot=slot_number):
                slot = get_slot(slot_number)
                self.assertEqual(slot.slot_number, slot_number)
                self.assertIsInstance(slot.ticket_price, Decimal)
                self.assertEqual(slot.ticket_price, price)
                self.assertEqual(slot.min_ticket_number, 0)
                self.assertEqual(slot.max_ticket_number, maximum)
                self.assertIs(slot, SCRATCH_OFF_SLOTS[slot_number - 1])

    def test_catalog_is_immutable(self):
        self.assertIsInstance(SCRATCH_OFF_SLOTS, tuple)
        with self.assertRaises(FrozenInstanceError):
            get_slot(1).ticket_price = Decimal("1.00")

    def test_catalog_serializes_prices_as_exact_decimal_strings(self):
        self.assertEqual(
            get_slot(1).to_dict(),
            {
                "slot_number": 1,
                "ticket_price": "20.00",
                "min_ticket_number": 0,
                "max_ticket_number": 24,
            },
        )

    def test_unknown_or_non_integer_slot_ids_are_rejected(self):
        for slot_number in (0, -1, 21, True, False, 1.0, "1", None, [], {}):
            with self.subTest(slot=slot_number):
                with self.assertRaises(ValidationError) as caught:
                    get_slot(slot_number)
                self.assertEqual(caught.exception.code, "invalid_slot_number")


class ScratchOffTicketValidationTests(SimpleTestCase):
    def test_each_slots_zero_and_inclusive_maximum_are_accepted(self):
        for slot in SCRATCH_OFF_SLOTS:
            for value, expected in (
                (0, 0),
                ("000", 0),
                (slot.max_ticket_number, slot.max_ticket_number),
                (f"{slot.max_ticket_number:03d}", slot.max_ticket_number),
            ):
                with self.subTest(slot=slot.slot_number, value=value):
                    self.assertEqual(
                        validate_ticket_number(slot.slot_number, value), expected
                    )

    def test_each_slots_maximum_plus_one_is_rejected(self):
        for slot in SCRATCH_OFF_SLOTS:
            for value in (slot.max_ticket_number + 1, str(slot.max_ticket_number + 1)):
                with self.subTest(slot=slot.slot_number, value=value):
                    with self.assertRaises(ValidationError) as caught:
                        validate_ticket_number(slot.slot_number, value)
                    self.assertEqual(
                        caught.exception.code, "ticket_number_out_of_range"
                    )
                    self.assertIn(f"{slot.max_ticket_number:03d}", str(caught.exception))

    def test_blank_inputs_are_missing_and_not_zero(self):
        for slot in SCRATCH_OFF_SLOTS:
            for value in (None, "", " ", "\t\n"):
                with self.subTest(slot=slot.slot_number, value=value):
                    self.assertIsNone(validate_ticket_number(slot.slot_number, value))

    def test_digits_allow_padding_and_surrounding_whitespace(self):
        for value in (1, "1", "001", "0001", " 001\t"):
            with self.subTest(value=value):
                self.assertEqual(validate_ticket_number(1, value), 1)

    def test_negative_numbers_and_non_ticket_types_are_rejected(self):
        invalid_values = (
            -1,
            "-1",
            "+1",
            True,
            False,
            1.0,
            0.0,
            float("nan"),
            float("inf"),
            Decimal("1"),
            "1.0",
            "1e1",
            "0x01",
            "0 01",
            "abc",
            "٠١",
            "１２",
            "²",
            b"001",
            [],
            {},
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_ticket_number(1, value)

    def test_blank_value_does_not_bypass_slot_validation(self):
        with self.assertRaises(ValidationError) as caught:
            validate_ticket_number(21, None)
        self.assertEqual(caught.exception.code, "invalid_slot_number")

    def test_very_long_digit_strings_still_have_controlled_validation(self):
        with self.assertRaises(ValidationError) as caught:
            validate_ticket_number(1, "9" * 5000)
        self.assertEqual(caught.exception.code, "ticket_number_out_of_range")
        self.assertEqual(validate_ticket_number(1, "0" * 5000 + "1"), 1)
