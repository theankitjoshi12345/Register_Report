"""Store reconciliation using exact money and last-ticket-sold scratch counters."""

from django.core.exceptions import ValidationError

from .catalog import get_slot, validate_ticket_number
from .forms import LotteryTotalsForm


MONEY_FIELDS = (
    "lottery_terminal_sales", "lottery_terminal_payout", "phone_card_actual_sales",
    "bodega_net_difference", "bodega_lottery_sales", "bodega_lottery_payout",
    "bodega_phone_card_sales", "bodega_gas_sales", "gas_cash_sales",
    "gas_lottery_sales", "gas_lottery_payout", "gas_phone_card_sales", "gas_card_payment_sales",
)
MAX_NEW_ROLL_COUNT = 32766  # Stored as count + 1 in a PositiveSmallIntegerField.


def normalize_scratch_offs(readings):
    """Validate public readings before using any value as a mapping key."""
    if not isinstance(readings, list):
        raise ValidationError({"scratch_offs": "Enter a list of scratch-off readings."})
    if len(readings) > 20:
        raise ValidationError({"scratch_offs": "Enter each of the 20 slots at most once."})
    result = []
    seen = set()
    for index, reading in enumerate(readings):
        prefix = f"scratch_offs.{index}"
        if not isinstance(reading, dict):
            raise ValidationError({"scratch_offs": "Each reading must be an object."})
        try:
            slot = get_slot(reading.get("slot_number"))
        except ValidationError as error:
            raise ValidationError({f"{prefix}.slot_number": error.messages}) from error
        if slot.slot_number in seen:
            raise ValidationError({f"{prefix}.slot_number": f"Scratch-off slot {slot.slot_number} was entered more than once."})
        seen.add(slot.slot_number)
        if "ending_number" not in reading:
            raise ValidationError({f"{prefix}.ending_number": "Enter an ending number or null."})
        try:
            ending = validate_ticket_number(slot.slot_number, reading["ending_number"])
        except ValidationError as error:
            raise ValidationError({f"{prefix}.ending_number": error.messages}) from error
        if "new_roll" in reading and type(reading["new_roll"]) is not bool:
            raise ValidationError({f"{prefix}.new_roll_count": "The legacy new-roll flag must be boolean."})
        count = reading.get("new_roll_count", 1 if reading.get("new_roll", False) else 0)
        if type(count) is not int or not 0 <= count <= MAX_NEW_ROLL_COUNT:
            raise ValidationError(
                {f"{prefix}.new_roll_count": f"Enter a whole-number new-roll count from 0 to {MAX_NEW_ROLL_COUNT}."}
            )
        result.append({"slot_number": slot.slot_number, "ending_number": ending, "new_roll_count": count})
    return result


def calculate_scratch_off_sales(readings):
    """Counters identify the last ticket sold; blank finishes an active roll.

    No previous reading and an empty counter establish a zero-sales baseline.
    An empty counter following a number exhausts that roll. A later counter
    needs a new roll; repeated empty counters cannot sell the same roll again.
    """
    normalized = normalize_scratch_offs(readings)
    slots = {}
    from decimal import Decimal
    total_sales = Decimal("0.00")
    for index, (reading, normalized_reading) in enumerate(zip(readings, normalized)):
        slot_number = normalized_reading["slot_number"]
        slot = get_slot(slot_number)
        ending_number = normalized_reading["ending_number"]
        previous_number = validate_ticket_number(slot_number, reading.get("previous_number"))
        exhausted = reading.get("previous_exhausted", False)
        initial_roll_active = reading.get("initial_roll_active", False)
        if type(exhausted) is not bool:
            raise ValidationError("Previous exhausted-roll state must be boolean.")
        new_roll_count = normalized_reading["new_roll_count"]
        # A lower counter means the prior roll ended and one replacement roll
        # was opened. Preserve larger explicit counts when multiple rolls were
        # added during the close period.
        if (new_roll_count == 0 and previous_number is not None
                and ending_number is not None and ending_number < previous_number):
            new_roll_count = 1
        roll_size = slot.max_ticket_number + 1
        starting_number = 0 if previous_number is None else previous_number
        current_roll_sold = roll_size if ending_number is None else ending_number + 1
        if previous_number is None and ending_number is not None:
            # With no prior close, 000 is the baseline counter. For example,
            # ending 006 represents six counter steps, not tickets 000–006.
            current_roll_sold = ending_number
        if new_roll_count:
            # With no active previous roll, the counter counts all rolls opened.
            prior_remaining = (roll_size if initial_roll_active else 0) if previous_number is None else slot.max_ticket_number - previous_number
            if exhausted:
                prior_remaining = 0
            tickets_sold = prior_remaining + (new_roll_count - 1) * roll_size + current_roll_sold
        elif exhausted:
            if ending_number is not None:
                raise ValidationError({f"scratch_offs.{index}.new_roll_count": f"Scratch-off slot {slot_number} was exhausted; add a new roll before entering a counter."})
            tickets_sold = 0
        elif previous_number is None:
            if ending_number is None:
                tickets_sold = slot.max_ticket_number if initial_roll_active else 0
            else:
                tickets_sold = current_roll_sold
        elif ending_number is None:
            tickets_sold = slot.max_ticket_number - previous_number
        else:
            tickets_sold = ending_number - previous_number
        sales = tickets_sold * slot.ticket_price
        slots[slot_number] = {
            "tickets_sold": tickets_sold,
            "ticket_price": slot.ticket_price,
            "sales": sales,
            "new_roll_count": new_roll_count,
            "starting_number": starting_number,
            "ending_number": ending_number,
            "ending_exhausted": ending_number is None and (exhausted or previous_number is not None or new_roll_count > 0 or initial_roll_active),
        }
        total_sales += sales
    return {"slots": slots, "total_sales": total_sales}


def _money(value, field, allow_negative=False):
    from decimal import Decimal, InvalidOperation

    if value is None or isinstance(value, bool) or value == "":
        raise ValidationError({field: "Enter an amount."})
    if not isinstance(value, (str, int, float, Decimal)) or len(str(value)) > 64:
        raise ValidationError({field: "Enter a valid amount."})
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise ValidationError({field: "Use no more than two decimal places."})
        if amount.copy_abs() > Decimal("9999999999.99"):
            raise ValidationError({field: "Amount cannot exceed 9,999,999,999.99."})
        if not allow_negative and amount < 0:
            raise ValidationError({field: "Amount cannot be negative."})
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: "Enter a valid amount."}) from None


def _text(value, field, max_length):
    if not isinstance(value, str):
        raise ValidationError({field: "Enter text."})
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError({field: f"Use no more than {max_length} characters."})
    return value


def _line_items(values, field):
    if not isinstance(values, list):
        raise ValidationError({field: "Enter a list of amounts."})
    result = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValidationError({field: f"Item {index + 1} is invalid."})
        result.append({
            "amount": _money(
                item.get("amount"), f"{field}.{index}.amount",
                allow_negative=field == "tickets",
            ),
            "description": _text(item.get("description", ""), f"{field}.{index}.description", 255),
        })
    return result


def calculate_daily_report(data, *, allow_missing_card_payments=False):
    """Validate and calculate all day/shift close comparisons."""
    if not isinstance(data, dict):
        raise ValidationError("The report must be a JSON object.")
    values = {
        field: (None if field == "gas_card_payment_sales" and data.get(field) is None and allow_missing_card_payments
                else _money(data.get(field), field, field == "bodega_net_difference"))
        for field in MONEY_FIELDS
    }
    scratch = calculate_scratch_off_sales(data.get("scratch_offs", []))
    tickets = _line_items(data.get("tickets", []), "tickets")
    vendor_payouts = _line_items(data.get("vendor_payouts", []), "vendor_payouts")
    safe_drops = _line_items(data.get("safe_drops", []), "safe_drops")

    scratch_sales = scratch["total_sales"]
    ticket_total = sum((item["amount"] for item in tickets), _money("0", "tickets"))
    vendor_total = sum((item["amount"] for item in vendor_payouts), _money("0", "vendor_payouts"))
    safe_drop_total = sum((item["amount"] for item in safe_drops), _money("0", "safe_drops"))
    pos_lottery_sales = values["bodega_lottery_sales"] + values["gas_lottery_sales"]
    pos_lottery_payout = values["bodega_lottery_payout"] + values["gas_lottery_payout"]
    pos_phone_cards = values["bodega_phone_card_sales"] + values["gas_phone_card_sales"]
    gas_net = None if values["gas_card_payment_sales"] is None else (
        values["gas_cash_sales"] - values["bodega_gas_sales"] - safe_drop_total
        - ticket_total - vendor_total - values["gas_card_payment_sales"]
    )

    def comparison(expected, actual):
        if actual is None:
            return {"expected": expected, "actual": None, "difference": None, "status": "incomplete"}
        difference = actual - expected
        return {
            "expected": expected, "actual": actual, "difference": difference,
            "status": "match" if difference == 0 else "mismatch",
        }

    return {
        "inputs": {**values, "tickets": tickets, "vendor_payouts": vendor_payouts, "safe_drops": safe_drops},
        "scratch_off": {"slots": scratch["slots"], "sales": scratch_sales},
        "comparisons": {
            "phone_card_sales": comparison(values["phone_card_actual_sales"], pos_phone_cards),
            "lottery_sales": comparison(scratch_sales + values["lottery_terminal_sales"], pos_lottery_sales),
            "lottery_payout": comparison(values["lottery_terminal_payout"], pos_lottery_payout),
        },
        "registers": {
            "bodega_net_difference": values["bodega_net_difference"],
            "gas_net_difference": gas_net,
        },
    }


def summarize_register_totals(data):
    """Add the two registers and compare payouts with the terminal's actual payout.

    A ticket serial alone cannot determine daily scratch-off sales. The sales
    reconciliation is deliberately left to the agreed ticket-counting workflow.
    """
    form = LotteryTotalsForm(data)
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())

    values = form.cleaned_data
    sales = values["gas_lottery_sales"] + values["bodega_ai_lottery_sales"]
    payout = values["gas_lottery_payout"] + values["bodega_ai_lottery_payout"]
    payout_difference = payout - values["terminal_payout"]

    return {
        "register_totals": {"lottery_sales": sales, "lottery_payout": payout},
        "terminal": {
            "instant_sales": values["terminal_instant_sales"],
            "payout": values["terminal_payout"],
        },
        "payout_comparison": {
            "actual": values["terminal_payout"],
            "recorded": payout,
            "difference": payout_difference,
            "status": "match" if payout_difference == 0 else "mismatch",
        },
    }
