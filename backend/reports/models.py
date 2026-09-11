"""Saved daily lottery reports and their scratch-off counter readings."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class LotteryLedger(models.Model):
    """Singleton row used to serialize writes to the store's lottery history."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1),
                name="lottery_ledger_singleton",
            ),
        ]


class LotteryReport(models.Model):
    report_date = models.DateField(unique=True)
    terminal_instant_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    terminal_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    gas_lottery_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    gas_lottery_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    bodega_ai_lottery_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    bodega_ai_lottery_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["report_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(terminal_instant_sales__gte=0),
                name="lottery_terminal_sales_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(terminal_payout__gte=0),
                name="lottery_terminal_payout_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(gas_lottery_sales__gte=0),
                name="lottery_gas_sales_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(gas_lottery_payout__gte=0),
                name="lottery_gas_payout_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(bodega_ai_lottery_sales__gte=0),
                name="lottery_bodega_sales_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(bodega_ai_lottery_payout__gte=0),
                name="lottery_bodega_payout_nonnegative",
            ),
        ]

    def __str__(self):
        return f"Lottery report for {self.report_date}"


class DailyReport(models.Model):
    """A completed day or shift close with the store's reconciliation inputs."""

    DAY = "day"
    SHIFT = "shift"
    CLOSE_TYPES = ((DAY, "Day close"), (SHIFT, "Shift close"))

    store = models.ForeignKey("stores.Store", on_delete=models.PROTECT, default=1)
    report_date = models.DateField()
    close_type = models.CharField(max_length=5, choices=CLOSE_TYPES)
    close_label = models.CharField(max_length=80, blank=True)
    lottery_terminal_sales = models.DecimalField(max_digits=12, decimal_places=2)
    lottery_terminal_payout = models.DecimalField(max_digits=12, decimal_places=2)
    phone_card_actual_sales = models.DecimalField(max_digits=12, decimal_places=2)
    bodega_net_difference = models.DecimalField(max_digits=12, decimal_places=2)
    bodega_lottery_sales = models.DecimalField(max_digits=12, decimal_places=2)
    bodega_lottery_payout = models.DecimalField(max_digits=12, decimal_places=2)
    bodega_phone_card_sales = models.DecimalField(max_digits=12, decimal_places=2)
    bodega_gas_sales = models.DecimalField(max_digits=12, decimal_places=2)
    gas_cash_sales = models.DecimalField(max_digits=12, decimal_places=2)
    gas_lottery_sales = models.DecimalField(max_digits=12, decimal_places=2)
    gas_lottery_payout = models.DecimalField(max_digits=12, decimal_places=2)
    gas_phone_card_sales = models.DecimalField(max_digits=12, decimal_places=2)
    # Existing reports do not contain an independent card-payment total.
    gas_card_payment_sales = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    tickets = models.JSONField(default=list)
    vendor_payouts = models.JSONField(default=list)
    safe_drops = models.JSONField(default=list)
    scratch_offs = models.JSONField(default=list)
    calculated_report = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date", "-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["store", "report_date"], condition=models.Q(close_type="day"), name="unique_store_day_close"),
        ]

    def __str__(self):
        return f"{self.get_close_type_display()} for {self.report_date}"


class ReportLineItem(models.Model):
    """A queryable ticket, vendor payout, or safe-drop entry."""

    TICKET = "ticket"
    VENDOR_PAYOUT = "vendor_payout"
    SAFE_DROP = "safe_drop"
    ITEM_TYPES = (
        (TICKET, "Ticket"),
        (VENDOR_PAYOUT, "Vendor payout"),
        (SAFE_DROP, "Safe drop"),
    )

    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="line_items")
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["item_type", "position", "id"]
        indexes = [models.Index(fields=["report", "item_type"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="report_line_item_nonnegative"),
        ]


class ScratchOffRoll(models.Model):
    """Counter readings for one scratch-off slot on one close."""

    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="scratch_off_rolls")
    slot_number = models.PositiveSmallIntegerField()
    last_night_number = models.PositiveSmallIntegerField(null=True, blank=True)
    starting_number = models.PositiveSmallIntegerField(null=True, blank=True)
    ending_number = models.PositiveSmallIntegerField(null=True, blank=True)
    ending_exhausted = models.BooleanField(default=False)
    new_roll_counter = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["slot_number"]
        constraints = [
            models.UniqueConstraint(fields=["report", "slot_number"], name="unique_report_scratch_slot"),
            models.CheckConstraint(condition=models.Q(slot_number__gte=1, slot_number__lte=20), name="report_scratch_slot_range"),
            models.CheckConstraint(condition=models.Q(new_roll_counter__gte=1), name="report_scratch_roll_counter_positive"),
        ]


class ScratchOffReading(models.Model):
    report = models.ForeignKey(
        LotteryReport,
        on_delete=models.CASCADE,
        related_name="scratch_off_readings",
    )
    slot_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    opening_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(249)],
    )
    closing_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(249)],
    )
    ticket_price = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ["slot_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["report", "slot_number"],
                name="lottery_unique_report_slot",
            ),
            models.CheckConstraint(
                condition=models.Q(slot_number__gte=1, slot_number__lte=20),
                name="lottery_slot_number_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(opening_number__isnull=True)
                    | models.Q(opening_number__gte=0, opening_number__lte=249)
                ),
                name="lottery_opening_number_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closing_number__isnull=True)
                    | models.Q(closing_number__gte=0, closing_number__lte=249)
                ),
                name="lottery_closing_number_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(ticket_price__gte=0),
                name="lottery_ticket_price_nonnegative",
            ),
        ]

    def __str__(self):
        return f"Slot {self.slot_number} for {self.report.report_date}"
