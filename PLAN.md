# Register Report implementation status

## Implemented

- React/TypeScript/Tailwind form with five validated steps.
- Day and shift closes, report history, and editable saved reports.
- Independent lottery/phone-card comparisons and gas-register cash reconciliation.
- Separate gas phone-card sales and independent debit/credit-card payments.
- Decimal money validation, bounded ticket counters, and optional described line items.
- Scratch-off history scoped to each store, including exhausted rolls.
- Shift counters chained by creation order within a business date; full-day closes
  calculated separately against the preceding date's closing state.
- Recalculation of later reports following corrections/backdated entries, with
  atomic rollback for inconsistent history.
- One day close per store and business date; pending day-close indicators.
- Normalized line items and scratch-off rows alongside calculation snapshots.
- Django session login, CSRF-protected writes, store memberships, and store selection.
- Administrator management of stores and users through Django admin.
- Backend regression tests and frontend interaction tests in `make check`.
- SQLite development setup and optional PostgreSQL Compose configuration.

## Clarified during the fixes

The existing gas `gas_card_sales` value is **phone-card sales**. It is renamed
`gas_phone_card_sales` without losing stored values. Debit/credit payments used
in gas cash reconciliation have their own field, `gas_card_payment_sales`.
Historical reports require that newly separate payment figure to complete their
gas balance; the app does not fabricate it.

Authentication and store authorization are now included, superseding the earlier
deferral in the original project notes. `PERSONAL.md` remains unchanged.

Shift totals and new rolls cover a shift. Day totals and new rolls cover the full
day. Same-date shift ordering follows report creation order. The form explicitly
uses **last ticket sold** for ending counters, consistently across roll boundaries.
This resolves the old formulas' one-ticket double count when a roll finished.
A blank scratch-off
counter exhausts a known roll, but a first blank with no history establishes no
sales. These conventions are documented in the README and form.

## Remaining product work

- Hosting, HTTPS deployment, database backup/restore procedures, and production
  browser verification.
- Printing/exporting reports if needed.
- Store-configurable scratch-off catalogs and business time zones if needed.
- Explicit shift times/reordering and an opening-inventory workflow if needed.

These are additional product/deployment features, not prerequisites for the local
entry, reconciliation, history, and access workflows.
