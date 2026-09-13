# Register Report Requirements

The application is organized around shift closes. Users enter only the activity
for each shift, and the application automatically builds the day-end summary
from every shift on that business date. Previously saved manual day closes stay
available as legacy history, but users do not create new ones.

## Lottery

There are 20 scratch-off games, each assigned a number:

- Game 1 costs $20 and runs from 000 to 024.
- Games 2–3 cost $10 and run from 000 to 024.
- Games 4–7 cost $5 and run from 000 to 049.
- Games 8–10 cost $3 and run from 000 to 074.
- Games 11–15 cost $2 and run from 000 to 124.
- Games 16–20 cost $1 and run from 000 to 249.

Scratch-off ending numbers must be whole numbers within the valid range for the
game. Decimal values are not allowed, but users may leave an ending number empty.
This allows the application to calculate actual scratch-off sales.

When a slot has no prior ending number, its starting counter defaults to `000`.
The first close uses `ending number - 000`; for example, ending number `006` on a
$3 ticket produces `(6 - 0) × $3 = $18`.

The lottery terminal provides cumulative sales and payout readings that cannot
be reset between shifts. At each shift close, the user enters exactly what the
terminal currently displays. The user must not subtract an earlier reading.
Verifone and the Bodega AI register each provide the lottery sales and payout
that belong to the current shift.

For the first shift, the shift terminal amount equals the cumulative reading.
For every later shift on the same business date, the backend subtracts the
amounts already assigned to earlier shifts. This is equivalent to subtracting
the immediately previous cumulative reading:

```text
Current shift terminal sales
    = current cumulative terminal sales - previous cumulative terminal sales

Current shift terminal payout
    = current cumulative terminal payout - previous cumulative terminal payout
```

The derived shift amounts are compared with Bodega plus Verifone lottery sales
and payouts for that shift. Scratch-off sales are calculated and reported
separately.

Users must be able to enter the number of new scratch-off rolls added before the
day ends. When an ending number is lower than the previous night's ending number,
the backend must count one new roll by default. A larger new-roll count entered
by the user must take precedence.

## Phone Cards

One phone-card machine provides actual phone-card sales for each shift. The
backend compares that amount with the shift's combined phone-card sales from
both POS registers. The automated day summary adds every shift's values.

## Tickets (Verifone only)

This store allows known regular customers to receive a ticket and pay the store
the next day. At each shift close, the owner enters the ticket activity for that
shift on Verifone. This feature does not apply to
the Bodega AI register.

Users must be able to enter multiple optional amounts. Each amount may have an
optional description containing any relevant information. The total is used for
the shift and automatic day summary. Ticket amounts may be positive or negative.
The frontend must provide a `+`/`-` selector: `+` when a ticket is created for
the customer and `-` when the customer pays the ticket. The amount input accepts
the unsigned value.

## Vendor Payouts (Verifone only)

Vendor payouts work like tickets. Users must be able to enter multiple optional
amounts with optional descriptions. The total is used for the shift and automatic
day summary.

## Card Sales (Verifone only)

The owner will enter Verifone's total cash sales. Verifone has a
separate card machine that is not connected to the POS, so it operates
independently. These card-machine sales are recorded as cash sales for the POS.

At each shift close, the owner enters Verifone's card sales for that shift. The
frontend must accept the amount without fees, and the backend uses it for the
shift and automatic day summary.

## Safe Drops (Verifone only)

This is the total cash amount dropped into the locked safe, similar to an
in-store locker. Users must be able to enter multiple optional amounts.

## Gas (Bodega AI register only)

This is the total amount of gas sold through the Bodega AI register. That POS does
not have access to the pumps, so the money is collected in this register while the
gas is sold through Verifone. This is a simulated sale for Verifone, and the
backend uses it for the shift and automatic day summary.

## Net Difference (Bodega AI register only)

At the end of each shift, this is the difference shown by the Bodega AI register.
It can be positive or negative, so users must be able to enter either value.
The entered value remains the original raw value.

An optional Bodega AI Ticket section appears with the net-difference entry. Its
subtitle is: "Fill this up if anybody has charged any ticket." Users may add
multiple entries, each with a required positive amount and an optional
description. This section does not use a `+`/`-` selector.

The final Bodega AI result is labeled **Register Balance** and is calculated as:

```text
Total Bodega AI Ticket Amount = sum of Bodega AI ticket amounts
Register Balance = Bodega AI Net Difference + Total Bodega AI Ticket Amount
```

An empty ticket list has a total of `$0.00`, so the Register Balance equals the
entered net difference. For example, `-$50.00 + $20.00 = -$30.00`, and
`$5.00 + $20.00 = $25.00`.

## What the owner enters for every shift close

All of these items must be organized into steps:

### Independent items

- Phone-card sales

### Lottery terminal

- Current cumulative lottery sales
- Current cumulative lottery payout

### Scratch-off tickets

- Slots 1 through 20.
- Twenty whole-number ending counters, each followed by the number of new rolls
  added during the close period.

### Bodega AI

- Net difference
- Optional positive ticket amounts with optional descriptions
- Lottery sales
- Lottery payout
- Phone cards
- Gas

### Verifone

- Total cash sales
- Verifone safe drops
- Verifone tickets
- Lottery sales
- Lottery payout
- Verifone vendor payouts
- Card payment without including fee

## Clarifications

- Django session authentication, CSRF protection, and store-scoped authorization
  are required.
- Scratch-off counters accept either a valid whole-number ticket counter or an
  empty/null value. An empty ending counter means that all tickets remaining in
  that roll were sold.
- A missing prior counter defaults to `000` for the first sales calculation.
- When an ending counter is lower than the previous ending counter and the user
  entered zero new rolls, the application automatically records one new roll.
- Scratch-off sales use the prior shift's ending state, the current ending
  counter, new-roll count, and the catalog ticket price. The final shift state
  becomes the starting state for the next business date.
- The new-roll value is a counter for each scratch-off slot, not only a checkbox.
- Every amount that may be positive or negative uses a separate `+`/`-` selector,
  including ticket amounts and the Bodega AI net difference. For tickets, `+`
  means a ticket was created for the customer and `-` means the customer paid it.
- The Bodega AI net difference is required and may be positive or negative, with
  up to two decimal places.
- Bodega AI ticket amounts are optional, positive-only adjustments. They are
  stored separately from the existing signed Verifone ticket entries.
- Reports must be editable after saving.
- Report data should use normalized, queryable records for line items and
  scratch-off rolls rather than relying only on JSON blobs.

## How the backend will function

For phone cards, the backend will check the difference described above. It will
also derive the current shift's terminal sales and payout before comparing them
with the shift register values. For Bodega AI, it stores the entered net
difference unchanged, adds the optional Bodega AI ticket total, and presents the
result as Register Balance in shift history and daily summaries.

For Verifone, it will calculate:

```text
Total cash sales
- gas (from Bodega AI)
- safe drops
- tickets
- vendor payouts
- card payment without including fee
```

This provides Verifone's net difference, which can be positive or
negative.

The backend should provide these values in a table:

```text
Bodega AI [Register Balance: ]
Verifone [Net Difference: ]

Phone card [Expected: , Actual: ]
Lottery sales [Expected: , Actual: ]
Lottery payout [Expected: , Actual: ]
```

The report should also display all information entered by the user. For every
scratch-off slot, it must show the starting number from the previous close, the
ending number entered for the current close, the number of new rolls added, and
the total sales value generated by that slot.

The application automatically produces one live daily summary for every
business date that has shifts. It includes all shifts, summed scratch-off sales
and new rolls, final scratch-off state, combined register values and line items,
the final cumulative terminal readings, and day-end sales, payout, and phone-card
comparisons. Editing an earlier shift recalculates every later shift and the
daily summary atomically. The automatic daily summary uses the same report layout
as a legacy day close, including register balances, reconciliation, entered
figures, separate line-item sections, and per-slot scratch-off results.

## UI

Users should be able to access individual shifts and automatic daily summaries
from any day.
