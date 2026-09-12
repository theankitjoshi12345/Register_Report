"""JSON endpoints for entering, saving, and reviewing store closes."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from itertools import groupby
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.http import JsonResponse

from stores.access import store_required
from stores.models import Store

from .lottery.catalog import SCRATCH_OFF_SLOTS
from .lottery.services import MAX_LINE_ITEMS, MONEY_FIELDS, _text, calculate_daily_report, normalize_scratch_offs
from .models import DailyReport, ReportLineItem, ScratchOffRoll

LINE_ITEM_FIELDS = (
    (ReportLineItem.TICKET, "tickets"),
    (ReportLineItem.VENDOR_PAYOUT, "vendor_payouts"),
    (ReportLineItem.SAFE_DROP, "safe_drops"),
)


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _report_json(report):
    calculated = _json_value(report.calculated_report)
    calculated["normalized_line_items"] = [
        {"item_type": item.item_type, "amount": format(item.amount, ".2f"), "description": item.description}
        for item in report.line_items.all()
    ]
    calculated["normalized_scratch_offs"] = [
        {"slot_number": roll.slot_number, "ending_number": roll.ending_number,
         "new_roll_count": roll.new_roll_counter - 1}
        for roll in report.scratch_off_rolls.all()
    ]
    return {
        "id": report.id, "store_id": report.store_id,
        "report_date": report.report_date.isoformat(), "close_type": report.close_type,
        "close_label": report.close_label, "calculated": calculated,
        "created_at": report.created_at.isoformat(),
    }


def lottery_catalog(request):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed."}, status=405)
    return JsonResponse({"slots": [slot.to_dict() for slot in SCRATCH_OFF_SLOTS]})


def _parse_payload(request):
    def invalid_constant(value):
        raise ValueError(f"Invalid JSON number: {value}.")

    try:
        payload = json.loads(request.body, parse_constant=invalid_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValidationError("Enter valid JSON.") from error
    if not isinstance(payload, dict):
        raise ValidationError("The report must be a JSON object.")
    return payload


def _report_payload(report):
    return {
        "report_date": report.report_date.isoformat(), "close_type": report.close_type,
        "close_label": report.close_label,
        **{field: getattr(report, field) for field in MONEY_FIELDS},
        **{key: deepcopy(getattr(report, key)) for _, key in LINE_ITEM_FIELDS},
        "scratch_offs": deepcopy(report.scratch_offs),
    }


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError("The report must be a JSON object.")
    try:
        report_date = date.fromisoformat(payload.get("report_date", ""))
        if report_date.isoformat() != payload["report_date"]:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError({"report_date": "Enter a date as YYYY-MM-DD."}) from None
    if payload.get("close_type") not in (DailyReport.DAY, DailyReport.SHIFT):
        raise ValidationError({"close_type": "Choose day or shift close."})
    close_label = _text(payload.get("close_label", ""), "close_label", 80)
    scratch_offs = normalize_scratch_offs(payload.get("scratch_offs", []))
    inputs = calculate_daily_report({**payload, "scratch_offs": scratch_offs})["inputs"]
    return {
        "report_date": report_date, "close_type": payload["close_type"], "close_label": close_label,
        **{field: inputs[field] for field in MONEY_FIELDS},
        **{key: _json_value(inputs[key]) for _, key in LINE_ITEM_FIELDS},
        "scratch_offs": scratch_offs,
    }


def _calculate_from_history(report, baseline, initial_active_slots=(), previous_terminal=None):
    payload = _report_payload(report)
    if report.close_type == DailyReport.SHIFT and not report.terminal_values_cumulative:
        previous_terminal = previous_terminal or {"sales": Decimal("0.00"), "payout": Decimal("0.00")}
        # Old shift rows stored the amount for that shift. Convert it only for
        # calculation and display; the original database values remain intact.
        payload["lottery_terminal_sales"] += previous_terminal["sales"]
        payload["lottery_terminal_payout"] += previous_terminal["payout"]
    readings = normalize_scratch_offs(payload["scratch_offs"])
    payload["scratch_offs"] = [
        {**reading, "previous_number": baseline.get(reading["slot_number"], (None, False))[0],
         "previous_exhausted": baseline.get(reading["slot_number"], (None, False))[1],
         "initial_roll_active": reading["slot_number"] in initial_active_slots}
        for reading in readings
    ]
    calculated = calculate_daily_report(
        payload,
        allow_missing_card_payments=True,
        previous_terminal=previous_terminal,
        legacy_day=report.close_type == DailyReport.DAY,
    )
    # Persist an automatically inferred rollover so history, edits, and the
    # final report all show the effective number of new rolls.
    for reading in readings:
        reading["new_roll_count"] = calculated["scratch_off"]["slots"][reading["slot_number"]]["new_roll_count"]
    return calculated, readings


def _apply_endings(state, calculated):
    for slot, result in calculated["scratch_off"]["slots"].items():
        state[slot] = (result["ending_number"], result["ending_exhausted"])


def _persist_calculation(report, calculated, readings, baseline):
    serialized = _json_value(calculated)
    serialized_readings = _json_value(readings)
    update_fields = []
    if report.calculated_report != serialized:
        report.calculated_report = serialized
        update_fields.append("calculated_report")
    if report.scratch_offs != serialized_readings:
        report.scratch_offs = serialized_readings
        update_fields.append("scratch_offs")
    if update_fields:
        report.save(update_fields=[*update_fields, "updated_at"])
    # Keep every submitted slot, including exhausted and initial blank readings.
    report.scratch_off_rolls.all().delete()
    ScratchOffRoll.objects.bulk_create([
        ScratchOffRoll(
            report=report, slot_number=reading["slot_number"],
            last_night_number=baseline.get(reading["slot_number"], (None, False))[0],
            starting_number=calculated["scratch_off"]["slots"][reading["slot_number"]]["starting_number"],
            ending_number=reading["ending_number"], new_roll_counter=reading["new_roll_count"] + 1,
            ending_exhausted=calculated["scratch_off"]["slots"][reading["slot_number"]]["ending_exhausted"],
        )
        for reading in readings
    ])
    # Prefetched relations were invalidated by replacing the rows.
    report._prefetched_objects_cache = {}


def _validate_day_after_shifts(calculated, readings, shift_state, shift_roll_counts):
    """Day readings cover the whole day, including any rolls opened in shifts."""
    for reading in readings:
        slot = reading["slot_number"]
        if slot not in shift_roll_counts:
            continue
        count = reading["new_roll_count"]
        shift_count = shift_roll_counts[slot]
        ending, exhausted = shift_state[slot]
        day_result = calculated["scratch_off"]["slots"][slot]
        if count < shift_count or (count == shift_count and (
            (ending is not None and reading["ending_number"] is not None and reading["ending_number"] < ending)
            or (exhausted and not day_result["ending_exhausted"])
        )):
            raise ValidationError(
                f"Day close slot {slot} must include all same-day shifts and their cumulative new-roll count."
            )


def _replay_history(store, changed_report_id):
    """Rebuild scratch and cumulative-terminal history chronologically."""
    history = list(DailyReport.objects.filter(store=store).order_by("report_date", "created_at", "id"))
    previous_day = {}
    for _, reports_for_date in groupby(history, key=lambda item: item.report_date):
        day_reports = list(reports_for_date)
        shift_state = previous_day.copy()
        shift_roll_counts = {}
        initial_active_slots = set()
        ordered = [item for item in day_reports if item.close_type == DailyReport.SHIFT]
        ordered += [item for item in day_reports if item.close_type == DailyReport.DAY]
        next_day = shift_state.copy()
        previous_terminal = {"sales": Decimal("0.00"), "payout": Decimal("0.00")}
        for report in ordered:
            baseline = previous_day if report.close_type == DailyReport.DAY else shift_state
            try:
                calculated, readings = _calculate_from_history(
                    report,
                    baseline,
                    initial_active_slots if report.close_type == DailyReport.DAY else (),
                    previous_terminal if report.close_type == DailyReport.SHIFT else None,
                )
                if report.close_type == DailyReport.DAY:
                    _validate_day_after_shifts(calculated, readings, shift_state, shift_roll_counts)
                _persist_calculation(report, calculated, readings, baseline)
            except ValidationError as error:
                if report.pk == changed_report_id:
                    raise
                raise ValidationError({"history": (
                    f"This change conflicts with report {report.pk} on {report.report_date}: "
                    + "; ".join(error.messages)
                    + " Correct that report's counters or new-roll counts first. No reports were changed."
                )}) from error
            if report.close_type == DailyReport.SHIFT:
                for reading in readings:
                    slot = reading["slot_number"]
                    if (previous_day.get(slot, (None, False)) == (None, False)
                            and shift_roll_counts.get(slot, 0) == 0
                            and reading["new_roll_count"] == 0 and reading["ending_number"] is not None):
                        initial_active_slots.add(slot)
                _apply_endings(shift_state, calculated)
                for reading in readings:
                    slot = reading["slot_number"]
                    shift_roll_counts[slot] = shift_roll_counts.get(slot, 0) + reading["new_roll_count"]
                previous_terminal = {
                    "sales": calculated["terminal"]["cumulative_sales"],
                    "payout": calculated["terminal"]["cumulative_payout"],
                }
                # In the shift-only workflow the final shift carries inventory
                # into the next business date.
                next_day = shift_state.copy()
            else:
                # Legacy manually entered day closes remain authoritative for
                # historical dates and may still be corrected.
                next_day = shift_state.copy()
                _apply_endings(next_day, calculated)
        previous_day = next_day.copy()
    if changed_report_id is not None:
        return next(item for item in history if item.pk == changed_report_id)
    return None


@transaction.atomic
def recalculate_store_history(store, *, dry_run=False):
    """Upgrade derived snapshots without changing any entered report values."""
    Store.objects.filter(pk=store.pk).update(name=F("name"))
    count = DailyReport.objects.filter(store=store).count()
    _replay_history(store, None)
    if dry_run:
        transaction.set_rollback(True)
    return count


@transaction.atomic
def _save_report(payload, store, report=None, *, partial=False):
    submitted_terminal = any(field in payload for field in ("lottery_terminal_sales", "lottery_terminal_payout"))
    # Limit only submitted collections: historical reports may predate this
    # bound and must remain readable, recalculable, and partially editable.
    for _, field in LINE_ITEM_FIELDS:
        items = payload.get(field, [])
        if isinstance(items, list) and len(items) > MAX_LINE_ITEMS:
            raise ValidationError({field: f"Enter no more than {MAX_LINE_ITEMS} items per report."})
    # UPDATE is deliberately the transaction's first database operation: SQLite
    # acquires its write lock here; PostgreSQL serializes on this store row.
    Store.objects.filter(pk=store.pk).update(name=F("name"))
    if report is not None:
        report = DailyReport.objects.get(pk=report.pk, store=store)
        if partial:
            existing = _report_payload(report)
            if submitted_terminal and not report.terminal_values_cumulative:
                existing["lottery_terminal_sales"] = report.calculated_report.get("inputs", {}).get(
                    "lottery_terminal_sales", report.lottery_terminal_sales,
                )
                existing["lottery_terminal_payout"] = report.calculated_report.get("inputs", {}).get(
                    "lottery_terminal_payout", report.lottery_terminal_payout,
                )
            payload = {**existing, **payload}
        if payload.get("close_type") != report.close_type:
            raise ValidationError({"close_type": "The close type of a saved report cannot be changed."})
    elif payload.get("close_type") != DailyReport.SHIFT:
        raise ValidationError({"close_type": "New reports must be shift closes. Daily summaries are created automatically."})
    values = _validate_payload(payload)
    if values["close_type"] == DailyReport.DAY and DailyReport.objects.filter(
        store=store, report_date=values["report_date"], close_type=DailyReport.DAY,
    ).exclude(pk=report.pk if report else None).exists():
        raise ValidationError({"report_date": "A day close already exists for this date."})
    if report is None:
        report = DailyReport.objects.create(store=store, terminal_values_cumulative=True, **values)
    else:
        for field, value in values.items():
            setattr(report, field, value)
        if submitted_terminal:
            report.terminal_values_cumulative = True
        report.save()
    report.line_items.all().delete()
    ReportLineItem.objects.bulk_create([
        ReportLineItem(report=report, item_type=item_type, amount=item["amount"],
                       description=item["description"], position=index)
        for item_type, key in LINE_ITEM_FIELDS
        for index, item in enumerate(values[key])
    ])
    return _replay_history(store, report.pk)


def _error_response(error):
    if isinstance(error, OperationalError):
        if "locked" not in str(error).lower() and "deadlock" not in str(error).lower():
            raise error
        response = JsonResponse({"errors": "Another report is being saved. Please retry."}, status=503)
        response["Retry-After"] = "1"
        return response
    if isinstance(error, IntegrityError):
        return JsonResponse({"errors": "A conflicting report already exists. Refresh and try again."}, status=400)
    details = error.message_dict if hasattr(error, "message_dict") else error.messages
    return JsonResponse({"errors": details}, status=400)


def _summary_comparison(expected, actual):
    difference = actual - expected
    return {
        "expected": format(expected, ".2f"),
        "actual": format(actual, ".2f"),
        "difference": format(difference, ".2f"),
        "status": "match" if difference == 0 else "mismatch",
    }


def _daily_summaries(history):
    """Build day-end results from saved shifts without duplicating inputs."""
    summaries = []
    scratch_state = {}
    summed_fields = tuple(
        field for field in MONEY_FIELDS
        if field not in {"lottery_terminal_sales", "lottery_terminal_payout"}
    )
    for report_date, reports_for_date in groupby(history, key=lambda item: item.report_date):
        date_reports = list(reports_for_date)
        shifts = [item for item in date_reports if item.close_type == DailyReport.SHIFT]
        for report in shifts:
            for slot, result in report.calculated_report.get("scratch_off", {}).get("slots", {}).items():
                scratch_state[str(slot)] = {
                    "ending_number": result.get("ending_number"),
                    "ending_exhausted": result.get("ending_exhausted", False),
                }
        if shifts:
            inputs = {}
            for field in summed_fields:
                values = [getattr(report, field) for report in shifts]
                inputs[field] = None if any(value is None for value in values) else sum(values, Decimal("0.00"))
            scratch_sales = sum(
                (Decimal(str(report.calculated_report["scratch_off"]["sales"])) for report in shifts),
                Decimal("0.00"),
            )
            new_rolls_by_slot = {}
            for report in shifts:
                for reading in report.scratch_offs:
                    slot = str(reading["slot_number"])
                    new_rolls_by_slot[slot] = new_rolls_by_slot.get(slot, 0) + reading["new_roll_count"]
            line_items = {}
            for item_type, key in LINE_ITEM_FIELDS:
                entries = [
                    {
                        "report_id": report.pk,
                        "shift_name": report.close_label,
                        "amount": item.amount,
                        "description": item.description,
                    }
                    for report in shifts
                    for item in report.line_items.all()
                    if item.item_type == item_type
                ]
                line_items[key] = {
                    "total": sum((entry["amount"] for entry in entries), Decimal("0.00")),
                    "entries": entries,
                }
            latest = shifts[-1]
            latest_terminal = latest.calculated_report.get("terminal", {})
            terminal_sales = Decimal(str(latest_terminal.get("cumulative_sales", latest.lottery_terminal_sales)))
            terminal_payout = Decimal(str(latest_terminal.get("cumulative_payout", latest.lottery_terminal_payout)))
            register_sales = inputs["bodega_lottery_sales"] + inputs["gas_lottery_sales"]
            register_payout = inputs["bodega_lottery_payout"] + inputs["gas_lottery_payout"]
            phone_register = inputs["bodega_phone_card_sales"] + inputs["gas_phone_card_sales"]
            gas_differences = [report.calculated_report["registers"].get("gas_net_difference") for report in shifts]
            summaries.append({
                "report_date": report_date.isoformat(),
                "shift_count": len(shifts),
                "shifts": [
                    {
                        "id": report.pk,
                        "close_label": report.close_label,
                        "created_at": report.created_at.isoformat(),
                        "terminal_sales": report.calculated_report.get("terminal", {}).get(
                            "shift_sales", format(report.lottery_terminal_sales, ".2f"),
                        ),
                        "terminal_payout": report.calculated_report.get("terminal", {}).get(
                            "shift_payout", format(report.lottery_terminal_payout, ".2f"),
                        ),
                        "scratch_off_sales": report.calculated_report["scratch_off"]["sales"],
                    }
                    for report in shifts
                ],
                "terminal": {
                    "final_cumulative_sales": terminal_sales,
                    "final_cumulative_payout": terminal_payout,
                },
                "scratch_off": {
                    "sales": scratch_sales,
                    "total_new_rolls": sum(new_rolls_by_slot.values()),
                    "new_rolls_by_slot": new_rolls_by_slot,
                    "final_state": deepcopy(scratch_state),
                },
                "inputs": inputs,
                "line_items": line_items,
                "registers": {
                    "lottery_sales": register_sales,
                    "lottery_payout": register_payout,
                    "bodega_net_difference": inputs["bodega_net_difference"],
                    "gas_net_difference": None if any(value is None for value in gas_differences) else sum(
                        (Decimal(str(value)) for value in gas_differences), Decimal("0.00"),
                    ),
                },
                "comparisons": {
                    "phone_card_sales": _summary_comparison(inputs["phone_card_actual_sales"], phone_register),
                    "lottery_sales": _summary_comparison(terminal_sales, register_sales),
                    "lottery_payout": _summary_comparison(terminal_payout, register_payout),
                },
            })
        # A legacy day close, when present, remains the saved closing inventory
        # for the following date. It is not included in the generated summary.
        for report in (item for item in date_reports if item.close_type == DailyReport.DAY):
            for slot, result in report.calculated_report.get("scratch_off", {}).get("slots", {}).items():
                scratch_state[str(slot)] = {
                    "ending_number": result.get("ending_number"),
                    "ending_exhausted": result.get("ending_exhausted", False),
                }
    return _json_value(summaries)


def _history_json(store):
    history = list(
        DailyReport.objects.filter(store=store)
        .prefetch_related("line_items", "scratch_off_rolls")
        .order_by("report_date", "created_at", "id")
    )
    return {
        "reports": [_report_json(report) for report in reversed(history)],
        "daily_summaries": list(reversed(_daily_summaries(history))),
    }


@store_required
def reports(request):
    if request.method == "GET":
        return JsonResponse(_history_json(request.store))
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)
    try:
        report = _save_report(_parse_payload(request), request.store)
        return JsonResponse(_report_json(report), status=201)
    except (ValidationError, IntegrityError, OperationalError) as error:
        return _error_response(error)


@store_required
def report_detail(request, report_id):
    try:
        report = DailyReport.objects.get(pk=report_id, store=request.store)
    except DailyReport.DoesNotExist:
        return JsonResponse({"error": "Report not found."}, status=404)
    if request.method == "GET":
        return JsonResponse(_report_json(report))
    if request.method not in {"PUT", "PATCH"}:
        return JsonResponse({"error": "Method not allowed."}, status=405)
    try:
        updated = _save_report(_parse_payload(request), request.store, report, partial=request.method == "PATCH")
        return JsonResponse(_report_json(updated))
    except (ValidationError, IntegrityError, OperationalError) as error:
        return _error_response(error)
