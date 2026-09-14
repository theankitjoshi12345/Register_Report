# Register Report implementation status

## Implemented

- React/TypeScript/Tailwind form with five validated steps.
- Shift closes, automatic daily summaries, report history, and editable saved reports.
- Lottery comparisons using scratch-off value plus terminal sales, independent
  phone-card comparisons, and Verifone cash reconciliation.
- Separate Verifone phone-card sales and independent debit/credit-card payments.
- Verifone Register Balance shown as sign-flipped currency so displayed `+`
  means over and `-` means short, while preserving the raw backend value.
- Bodega AI Register Balance shown as signed currency where `+` means short and
  `-` means over, with register-specific sign guidance in one shared result card.
- Decimal money validation, bounded ticket counters, and optional described line items.
- Positive-only Bodega AI ticket adjustments with raw net-difference retention
  and an adjusted Register Balance in shift history and daily summaries.
- Scratch-off history scoped to each store, including exhausted rolls.
- Shift counters chained by creation order within and across business dates.
- Cumulative lottery terminal readings converted into shift-only sales and payout,
  with later shifts replayed after an earlier correction.
- Legacy per-shift terminal inputs preserved in place and translated during replay.
- Automatic daily summaries using the final terminal readings and combined shift
  register, scratch-off, phone-card, new-roll, and line-item totals.
- Legacy-style daily summary presentation with register cards, reconciliation,
  raw entered figures, separate line items, and per-slot scratch-off results.
- Recalculation of later reports following corrections/backdated entries, with
  atomic rollback for inconsistent history.
- Normalized line items and scratch-off rows alongside calculation snapshots.
- Django session login, CSRF-protected writes, store memberships, and store selection.
- Administrator management of stores and users through Django admin.
- Backend regression tests and frontend interaction tests in `make check`.
- SQLite development setup and optional PostgreSQL Compose configuration.

## Clarified during the fixes

The existing internal `gas_card_sales` value is **phone-card sales**. It is renamed
`gas_phone_card_sales` without losing stored values. Debit/credit payments used
in Verifone cash reconciliation have their own field, `gas_card_payment_sales`.
Historical reports require that newly separate payment figure to complete their
Verifone balance; the app does not fabricate it.

Authentication and store authorization are now included, superseding the earlier
deferral in the original project notes. `PERSONAL.md` reflects the current requirements.

Shift totals and new rolls cover a shift. Daily results are derived from the
saved shifts rather than entered again. Same-date shift ordering follows report
creation order. The form explicitly uses **last ticket sold** for ending counters,
consistently across roll boundaries.
This resolves the old formulas' one-ticket double count when a roll finished.
A blank scratch-off
counter exhausts a known roll, but a first blank with no history establishes no
sales. These conventions are documented in the README and form.

## Remaining product work

- Database backup and restore procedures.
- Printing/exporting reports if needed.
- Store-configurable scratch-off catalogs and business time zones if needed.
- Explicit shift times/reordering and an opening-inventory workflow if needed.

These are additional product/deployment features, not prerequisites for the local
entry, reconciliation, history, and access workflows.
