"""The store's scratch-off slots and permitted ticket serial numbers.

A serial number identifies a position in a pack; it is not a sales count.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ScratchOffSlot:
    slot_number: int
    ticket_price: Decimal
    min_ticket_number: int
    max_ticket_number: int

    def to_dict(self) -> dict[str, int | str]:
        """Return JSON-compatible catalog data without floating-point money."""
        return {
            "slot_number": self.slot_number,
            "ticket_price": format(self.ticket_price, ".2f"),
            "min_ticket_number": self.min_ticket_number,
            "max_ticket_number": self.max_ticket_number,
        }


SCRATCH_OFF_SLOTS: tuple[ScratchOffSlot, ...] = tuple(
    ScratchOffSlot(
        slot_number=slot_number,
        ticket_price=Decimal(price),
        min_ticket_number=0,
        max_ticket_number=maximum,
    )
    for first_slot, last_slot, price, maximum in (
        (1, 1, "20.00", 24),
        (2, 3, "10.00", 24),
        (4, 7, "5.00", 49),
        (8, 10, "3.00", 74),
        (11, 15, "2.00", 124),
        (16, 20, "1.00", 249),
    )
    for slot_number in range(first_slot, last_slot + 1)
)


def get_slot(slot_number: object) -> ScratchOffSlot:
    """Look up one of the integer slot IDs from 1 through 20."""
    if type(slot_number) is not int or not 1 <= slot_number <= len(SCRATCH_OFF_SLOTS):
        raise ValidationError(
            "Slot number must be an integer from 1 to 20.",
            code="invalid_slot_number",
        )
    return SCRATCH_OFF_SLOTS[slot_number - 1]


def validate_ticket_number(slot_number: object, value: object) -> int | None:
    """Validate an optional serial, preserving zero as an entered value.

    Integers and ASCII decimal-digit strings are accepted. Surrounding string
    whitespace is ignored, and None or blank strings represent missing input.
    Floats, booleans, signs, and decimal notation are not serial numbers.
    """
    slot = get_slot(slot_number)
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if not value.isascii() or not value.isdecimal():
            raise ValidationError(
                "Ticket number must contain only digits from 0 to 9, or be blank.",
                code="invalid_ticket_number",
            )
        # Avoid Python's integer-string conversion limit for malformed long
        # inputs while still accepting leading zeros on a valid serial.
        value = value.lstrip("0") or "0"
        if len(value) > len(str(slot.max_ticket_number)):
            raise _out_of_range(slot)
        ticket_number = int(value)
    elif type(value) is int:
        ticket_number = value
    else:
        raise ValidationError(
            "Ticket number must be a whole number or digit string, or be blank.",
            code="invalid_ticket_number",
        )

    if not slot.min_ticket_number <= ticket_number <= slot.max_ticket_number:
        raise _out_of_range(slot)
    return ticket_number


def _out_of_range(slot: ScratchOffSlot) -> ValidationError:
    return ValidationError(
        "Ticket number for slot %(slot)s must be between %(minimum)s and %(maximum)s.",
        code="ticket_number_out_of_range",
        params={
            "slot": slot.slot_number,
            "minimum": f"{slot.min_ticket_number:03d}",
            "maximum": f"{slot.max_ticket_number:03d}",
        },
    )
