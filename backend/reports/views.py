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
from .lottery.services import MONEY_FIELDS, _text, calculate_daily_report, normalize_scratch_offs
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


def _calculate_from_history(report, baseline, initial_active_slots=()):
    payload = _report_payload(report)
    readings = normalize_scratch_offs(payload["scratch_offs"])
    payload["scratch_offs"] = [
        {**reading, "previous_number": baseline.get(reading["slot_number"], (None, False))[0],
         "previous_exhausted": baseline.get(reading["slot_number"], (None, False))[1],
         "initial_roll_active": reading["slot_number"] in initial_active_slots}
        for reading in readings
    ]
    calculated = calculate_daily_report(payload, allow_missing_card_payments=True)
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
    """Rebuild each slot chronologically; day closes do not double-count shifts."""
    history = list(DailyReport.objects.filter(store=store).order_by("report_date", "created_at", "id"))
    previous_day = {}
    for _, reports_for_date in groupby(history, key=lambda item: item.report_date):
        day_reports = list(reports_for_date)
        shift_state = previous_day.copy()
        shift_roll_counts = {}
        initial_active_slots = set()
        ordered = [item for item in day_reports if item.close_type == DailyReport.SHIFT]
        ordered += [item for item in day_reports if item.close_type == DailyReport.DAY]
        next_day = shift_state
        for report in ordered:
            baseline = previous_day if report.close_type == DailyReport.DAY else shift_state
            try:
                calculated, readings = _calculate_from_history(
                    report, baseline, initial_active_slots if report.close_type == DailyReport.DAY else (),
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
            else:
                # Omitted day slots retain the most recent shift reading.
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
    # UPDATE is deliberately the transaction's first database operation: SQLite
    # acquires its write lock here; PostgreSQL serializes on this store row.
    Store.objects.filter(pk=store.pk).update(name=F("name"))
    if report is not None:
        report = DailyReport.objects.get(pk=report.pk, store=store)
        if partial:
            payload = {**_report_payload(report), **payload}
    values = _validate_payload(payload)
    if values["close_type"] == DailyReport.DAY and DailyReport.objects.filter(
        store=store, report_date=values["report_date"], close_type=DailyReport.DAY,
    ).exclude(pk=report.pk if report else None).exists():
        raise ValidationError({"report_date": "A day close already exists for this date."})
    if report is None:
        report = DailyReport.objects.create(store=store, **values)
    else:
        for field, value in values.items():
            setattr(report, field, value)
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


@store_required
def reports(request):
    if request.method == "GET":
        queryset = DailyReport.objects.filter(store=request.store).prefetch_related("line_items", "scratch_off_rolls")
        return JsonResponse({"reports": [_report_json(report) for report in queryset]})
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
