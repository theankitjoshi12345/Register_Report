"""Validate the terminal and POS amounts used in lottery reconciliation."""

from decimal import Decimal

from django import forms


class MoneyField(forms.DecimalField):
    """Require an explicit, nonnegative amount with at most two decimal places."""

    def __init__(self, **kwargs):
        super().__init__(
            min_value=Decimal("0.00"),
            max_digits=12,
            decimal_places=2,
            **kwargs,
        )


class LotteryTotalsForm(forms.Form):
    terminal_instant_sales = MoneyField(label="Terminal actual instant ticket sales")
    terminal_payout = MoneyField(label="Terminal actual payout")
    gas_lottery_sales = MoneyField(label="Verifone lottery sales")
    gas_lottery_payout = MoneyField(label="Verifone lottery payout")
    bodega_ai_lottery_sales = MoneyField(label="Bodega AI register lottery sales")
    bodega_ai_lottery_payout = MoneyField(label="Bodega AI register lottery payout")
