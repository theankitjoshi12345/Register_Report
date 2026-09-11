# Register Report Requirements

The application must support both day closes and shift closes, depending on what
the user wants to perform. There must always be a day close.

## Lottery

There are 20 scratch-off games, each assigned a number:

- Game 1 costs $20 and runs from 000 to 024.
- Games 2–3 cost $10 and run from 000 to 024.
- Games 4–7 cost $5 and run from 000 to 049.
- Games 8–10 cost $3 and run from 000 to 074.
- Games 11–15 cost $2 and run from 000 to 124.
- Games 16–20 cost $1 and run from 000 to 249.

Users must not be able to enter invalid numbers, but they may leave a number
empty. This allows the application to calculate actual scratch-off sales.

The lottery terminal provides two values for the user to enter: actual instant-
ticket sales and actual payouts. The gas register and Bodega AI register each
provide lottery sales and lottery payout values.

The backend will add the sales and payout values from both registers and compare
them with the actual lottery-terminal values:

```text
Actual scratch-off sales + actual lottery sales
    == combined lottery sales across both POS registers

Actual payout sales == combined POS payout sales
```

There must also be a button that users can click when they add a new roll of
scratch-off tickets before the day ends. The backend must handle this using the
number provided by the user.

## Phone Cards

One phone-card machine provides the actual phone-card sales for the day. The
backend must compare that amount with the combined phone-card sales entered from
both POS registers.

## Tickets (gas register only)

This store allows known regular customers to receive a ticket and pay the store
the next day. At the end of the day or shift, the owner will enter the total value
of tickets created that day on the gas register. This feature does not apply to
the Bodega AI register.

Users must be able to enter multiple optional amounts. Each amount may have an
optional description containing any relevant information. The total will be used
at the end of the day or shift.

## Vendor Payouts (gas register only)

Vendor payouts work like tickets. Users must be able to enter multiple optional
amounts with optional descriptions. The total will be used at the end of the day
or shift.

## Card Sales (gas register only)

The owner will enter the gas register's total cash sales. The register has a
separate card machine that is not connected to the POS, so it operates
independently. These card-machine sales are recorded as cash sales for the POS.

At the end of the day or shift, the owner will enter the gas register's total card
sales. The frontend must accept the net amount without fees, and the backend must
use it at the end of the day or shift.

## Safe Drops (gas register only)

This is the total cash amount dropped into the locked safe, similar to an
in-store locker. Users must be able to enter multiple optional amounts.

## Gas (Bodega AI register only)

This is the total amount of gas sold through the Bodega AI register. That POS does
not have access to the pumps, so the money is collected in this register while the
gas is sold through the gas register. This is a simulated sale for the gas
register, and the backend will use it at the end of the day or shift.

## Net Difference (Bodega AI register only)

At the end of the day, this is the difference shown by the Bodega AI register. It
can be positive or negative, so users must be able to enter either value.

## What the owner enters for every day or shift close

All of these items must be organized into steps:

### Independent items

- Phone-card sales

### Lottery terminal

- Lottery sales
- Lottery payout

### Scratch-off tickets

- Slots 1 through 20.
- Twenty ending numbers, each followed by a checkbox indicating whether a new
  roll was added that day. The application must ask for confirmation before
  adding a new roll for a slot.

### Bodega AI

- Net difference
- Lottery sales
- Lottery payout
- Phone cards
- Gas

### Gas register

- Total cash sales
- Safe drops
- Tickets
- Lottery sales
- Lottery payout
- Vendor payouts
- Card-machine sales without fees

## Clarifications (2026-09-10)

- Authentication and authorization are intentionally deferred until the rest of
  the product is complete.
- Scratch-off counters accept either a valid whole-number ticket counter or an
  empty/null value. An empty ending counter means that all tickets remaining in
  that roll were sold.
- Scratch-off sales use the ticket price and the clarified roll formula:
  `(ending - starting) + (new roll counter - 1) * (ticket ending - starting + 1)
  + (ending - last night number + 1)`, then multiplied by the ticket price.
- The new-roll value is a counter for each scratch-off slot, not only a checkbox.
- The Bodega AI net difference is required and may be positive or negative, with
  up to two decimal places.
- Reports must be editable after saving.
- Report data should use normalized, queryable records for line items and
  scratch-off rolls rather than relying only on JSON blobs.

## How the backend will function

For phone cards, the backend will check the difference described above. It will
also check the differences for lottery sales and payouts. For Bodega AI, it will
display the net difference amount.

For the gas register, it will calculate:

```text
Total cash sales
- gas (from Bodega AI)
- safe drops
- tickets
- vendor payouts
- card-machine sales without fees
```

This provides the gas register's net difference, which can be positive or
negative.

The backend should provide these values in a table:

```text
Bodega AI [Net Difference: ]
Gas Register [Net Difference: ]

Phone card [Expected: , Actual: ]
Lottery sales [Expected: , Actual: ]
Lottery payout [Expected: , Actual: ]
```

The report should also display all information entered by the user.

## UI

Users should be able to access reports and shifts from any day.

