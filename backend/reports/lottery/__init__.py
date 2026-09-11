"""Lottery input definitions and reconciliation helpers."""

from .catalog import (
    SCRATCH_OFF_SLOTS,
    ScratchOffSlot,
    get_slot,
    validate_ticket_number,
)

__all__ = [
    "SCRATCH_OFF_SLOTS",
    "ScratchOffSlot",
    "get_slot",
    "validate_ticket_number",
]
