# Register Report architecture

This document explains the complete Register Report system as it exists in this
repository. It is intended for developers who need to operate, debug, extend, or
rebuild the application without relying on undocumented context.

## Contents

1. [What the system does](#1-what-the-system-does)
2. [System overview](#2-system-overview)
3. [Repository map](#3-repository-map)
4. [Domain model and terminology](#4-domain-model-and-terminology)
5. [Data model](#5-data-model)
6. [Report input contract](#6-report-input-contract)
7. [Accounting calculations](#7-accounting-calculations)
8. [Saving and replaying history](#8-saving-and-replaying-history)
9. [Automatic daily summaries and history](#9-automatic-daily-summaries-and-history)
10. [HTTP API](#10-http-api)
11. [Authentication and authorization](#11-authentication-and-authorization)
12. [Other security boundaries](#12-other-security-boundaries)
13. [Frontend architecture](#13-frontend-architecture)
14. [Local development](#14-local-development)
15. [Production deployment](#15-production-deployment)
16. [Testing and quality gates](#16-testing-and-quality-gates)
17. [Safe extension patterns](#17-safe-extension-patterns)
18. [Debugging guide](#18-debugging-guide)
19. [Rebuilding the system from scratch](#19-rebuilding-the-system-from-scratch)
20. [Architectural invariants](#20-architectural-invariants)

## 1. What the system does

Register Report records store activity at each shift close and reconciles three
categories across independent machines and two registers:

- lottery sales, including scratch-off sales and lottery-terminal sales;
- lottery payouts;
- phone-card sales.

It also calculates a final balance for each register:

- **Bodega AI** starts with the net difference entered by the user and adds
  optional Bodega AI ticket adjustments;
- **Verifone** starts with total cash sales and subtracts gas sold through
  Bodega AI, safe drops, signed tickets, vendor payouts, and card payments.

Users save individual shifts. The backend generates an automatic daily summary
from every shift on a business date. A correction to an older report causes the
backend to replay that store's later history so cumulative terminal values and
scratch-off counters remain consistent.

The application is multi-store. Authentication identifies the user; store
memberships determine which data that user may access. Every report query and
write is scoped to one authorized store.

## 2. System overview

```mermaid
flowchart LR
    U[Browser user] -->|HTTPS| V[Vercel routing]
    V -->|Static files and SPA fallback| F[React/Vite frontend]
    V -->|/api/*| D[Django WSGI function]
    F -->|Session cookie, CSRF token, X-Store-ID| D
    D -->|Django ORM| DB[(Neon PostgreSQL)]
    D -->|Local default| SQ[(SQLite)]
```

The main production deployment is one origin. Vercel serves the compiled React
application and sends `/api/*` to the Django Python Function. Locally, Vite and
Django run on separate ports; Django's explicit CORS middleware allows only
configured frontend origins.

### Technology choices

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Browser | React 19, TypeScript, Tailwind CSS, Vite | Login, five-step form, validation hints, history, shift and daily views |
| API | Django 5.2 | Authentication, authorization, validation, calculations, history replay, JSON responses |
| Production database | Neon PostgreSQL | Users, sessions, stores, reports, normalized entries, login limits |
| Local database | SQLite by default | Zero-configuration development and tests |
| Production host | Vercel | Frontend build, static hosting, SPA routing, Django serverless function |
| Dependency tools | `uv`, npm | Locked Python environment and frontend packages |

## 3. Repository map

```text
api/index.py                  Vercel WSGI entry point
backend/config/               Django settings, security middleware, URLs, health endpoint
backend/stores/               Store models, memberships, session API, CORS, login throttling
backend/reports/              Report models, API, replay, calculations, migrations
backend/reports/lottery/      Scratch catalog, validation, and accounting functions
backend/reports/management/   History recalculation command
frontend/src/App.tsx          Frontend state machine, bootstrapping, save/edit workflow
frontend/src/report.ts        Shared types, field definitions, defaults, formatters
frontend/src/FormFields.tsx   Amount, line-item, and scratch-off form controls
frontend/src/Header.tsx       Store selector and ordered history menu
frontend/src/ReportView.tsx   Individual shift and legacy-day presentation
frontend/src/DailySummaryView.tsx
                              Automatic daily-summary presentation
frontend/src/api.ts           Fetch wrapper and normalized API errors
frontend/tests/app.test.mjs   Browser workflow tests using JSDOM and real components
vercel.json                   Production build, routing, function inclusion, headers
compose.yaml                  Optional local PostgreSQL 17 service
scripts/setup.sh              Repeatable local setup
Makefile                      Development, migration, recalculation, and check commands
README.md                     Operator setup and common commands
PERSONAL.md                   Product rules and historical decisions
PLAN.md                       Implementation status
```

## 4. Domain model and terminology

### Business date

`report_date` is the store's business date, written as `YYYY-MM-DD`. The
frontend derives a new report's default from local browser calendar components,
not from UTC. The backend validates the exact ISO date form.

The Django project timezone is currently UTC. There is no per-store timezone
column. The business date entered by the user is therefore authoritative.

### Shift close

A shift close contains activity since the previous shift close, except for the
lottery terminal's sales and payout fields. Those two fields are cumulative
readings from the terminal. The backend subtracts the preceding shift's
cumulative reading to derive the amount assigned to the current shift.

New reports must have `close_type: "shift"`.

### Automatic daily summary

An automatic daily summary is computed from saved shifts whenever report history
is requested. It is not a database row and has no independent ID. Changing a
shift changes the next generated summary.

### Legacy day close

Older manual day closes remain in `reports_dailyreport` with
`close_type: "day"`. They are not stored in a separate table. Existing legacy
day closes remain editable, but the API rejects new manual day closes and rejects
changing a saved report's close type. A conditional database constraint permits
at most one legacy day close per store and business date.

A legacy day close is excluded from the generated daily totals. Its closing
scratch inventory is authoritative for the following business date.

### Expected and actual

Reconciliation objects use:

```text
difference = actual register amount - expected machine amount
```

Zero is a match. A nonzero difference is displayed as `Off $X`. Register-balance
sign conventions do not apply to reconciliation differences.

## 5. Data model

```mermaid
erDiagram
    AUTH_USER ||--o{ STORE_MEMBERSHIP : has
    STORE ||--o{ STORE_MEMBERSHIP : authorizes
    STORE ||--o{ DAILY_REPORT : owns
    DAILY_REPORT ||--o{ REPORT_LINE_ITEM : contains
    DAILY_REPORT ||--o{ SCRATCH_OFF_ROLL : records

    STORE {
        bigint id PK
        varchar name
        datetime created_at
    }
    STORE_MEMBERSHIP {
        bigint id PK
        bigint store_id FK
        bigint user_id FK
    }
    DAILY_REPORT {
        bigint id PK
        bigint store_id FK
        date report_date
        varchar close_type
        varchar close_label
        decimal money_fields
        boolean terminal_values_cumulative
        json calculated_report
        datetime created_at
        datetime updated_at
    }
    REPORT_LINE_ITEM {
        bigint id PK
        bigint report_id FK
        varchar item_type
        decimal amount
        varchar description
        int position
    }
    SCRATCH_OFF_ROLL {
        bigint id PK
        bigint report_id FK
        smallint slot_number
        smallint last_night_number
        smallint starting_number
        smallint ending_number
        boolean ending_exhausted
        smallint new_roll_counter
    }
```

### Current operational tables

Django uses its standard authentication, permission, content-type, migration,
session, and admin-log tables. The application-specific tables are:

| Django model | Default table | Purpose |
| --- | --- | --- |
| `stores.Store` | `stores_store` | Store identity |
| `stores.StoreMembership` | `stores_storemembership` | User-to-store authorization |
| `stores.LoginAttemptBucket` | `stores_loginattemptbucket` | Shared hashed login-rate counters |
| `reports.DailyReport` | `reports_dailyreport` | Raw shift or legacy-day inputs plus calculated snapshot |
| `reports.ReportLineItem` | `reports_reportlineitem` | Queryable Bodega tickets, Verifone tickets, vendor payouts, and safe drops |
| `reports.ScratchOffRoll` | `reports_scratchoffroll` | Queryable per-report scratch counter state |

`DailyReport.store` uses `PROTECT`, preventing deletion of a store that still has
reports. Memberships cascade with their user or store. A report's normalized
line items and scratch rows cascade when that report is deleted at the database
level, although the public API currently provides no delete endpoint.

### Compatibility models

`LotteryReport`, `ScratchOffReading`, and `LotteryLedger` come from the original
lottery-only design. The current `/api/reports/` workflow does not read or write
them. They remain in the schema and their calculation helper remains covered by
tests. A future cleanup should migrate or confirm unused production data before
removing these models and tables.

### Schema evolution

The migration sequence explains why some compatibility fields exist:

| Migration | Architectural change |
| --- | --- |
| `0001` | Original lottery-only reports and scratch readings |
| `0002` | Singleton lottery ledger used by the earlier design |
| `0003` | Unified `DailyReport` for day and shift closes |
| `0004` | Normalized report line items and scratch rolls |
| `0005` | Store ownership, independent card payments, phone-card rename, historical backfill |
| `0006` | Signed Verifone ticket amounts |
| `0007` | Marker distinguishing cumulative from legacy per-shift terminal values |
| `0008` | Positive-only Bodega AI ticket adjustments |

Never squash these migrations on a database that may contain production history.
Data migrations in `0005` preserve old phone-card inputs, intentionally mark the
new card-payment value unknown, and backfill normalized rows.

### Raw fields and calculated snapshots

`DailyReport` deliberately stores both:

1. raw entered fields in typed database columns and compatibility JSON arrays;
2. derived output in the `calculated_report` JSON snapshot.

Normalized `ReportLineItem` and `ScratchOffRoll` rows make collection data
queryable. The JSON arrays remain for backward compatibility and replay. On each
save or recalculation, the system rebuilds derived snapshots and normalized
scratch rows. Line items are replaced from the validated submitted values.

Money is stored with `DecimalField(max_digits=12, decimal_places=2)`. Calculations
use Python `Decimal`, and API money values are serialized as two-decimal strings.
The frontend must not use floating-point arithmetic for authoritative accounting;
its numeric conversion is only used for display formatting.

## 6. Report input contract

Every new form starts with the current local business date, `close_type` set to
`shift`, an empty optional label, visually empty monetary fields, empty line-item
lists, and 20 scratch slots with zero new rolls. Core amount boxes show a `0.00`
placeholder and untouched blanks are normalized to `0.00` in the submitted JSON.
Line-item amounts remain explicitly required.

### Required monetary fields

| API field | UI meaning | Negative allowed? |
| --- | --- | --- |
| `lottery_terminal_sales` | Current cumulative lottery-terminal sales | No |
| `lottery_terminal_payout` | Current cumulative lottery-terminal payout | No |
| `phone_card_actual_sales` | Independent actual phone-card sales | No |
| `bodega_net_difference` | Raw Bodega AI net difference | Yes |
| `bodega_lottery_sales` | Lottery sales recorded by Bodega AI | No |
| `bodega_lottery_payout` | Lottery payout recorded by Bodega AI | No |
| `bodega_phone_card_sales` | Phone cards recorded by Bodega AI | No |
| `bodega_gas_sales` | Gas sold through Bodega AI | No |
| `gas_cash_sales` | Verifone total cash sales | No |
| `gas_lottery_sales` | Lottery sales recorded by Verifone | No |
| `gas_lottery_payout` | Lottery payout recorded by Verifone | No |
| `gas_phone_card_sales` | Phone cards recorded by Verifone | No |
| `gas_card_payment_sales` | Debit/credit payment amount, excluding fees | No; nullable only for old rows |

Amounts may contain at most two decimal places and may not exceed
`9,999,999,999.99` in absolute value. Booleans, blanks, non-finite numbers,
oversized values, and malformed types are rejected by the backend even if the
browser has already validated the form.

### Line items

Each line item is an object with:

```json
{
  "amount": "10.00",
  "description": "Optional note"
}
```

| Collection | Rules |
| --- | --- |
| `bodega_ai_tickets` | Optional; each amount must be strictly positive |
| `tickets` | Optional; signed amounts allowed; `+` means ticket created and `-` means ticket paid |
| `vendor_payouts` | Optional; nonnegative amounts |
| `safe_drops` | Optional; nonnegative amounts |

Descriptions are trimmed, limited to 255 characters, and checked for characters
that PostgreSQL or UTF-8 cannot store. Each submitted collection is limited to
500 items. Add controls appear after the existing rows so the new row appears
beside the action on both mobile and desktop.

### Scratch-off input

Each submitted scratch entry contains:

```json
{
  "slot_number": 8,
  "ending_number": "006",
  "new_roll_count": 0
}
```

- A report may contain each slot from 1 through 20 at most once.
- `ending_number` is the last ticket sold, not a count and not money.
- It must be an integer or ASCII digit string within that slot's range, or blank
  to represent a sold-out/exhausted roll.
- Floats, decimal strings, booleans, signed numbers, and non-ASCII digits are
  rejected.
- `new_roll_count` is an integer from 0 through 32,766.
- Sparse legacy reports may omit slots. Editing preserves omitted slots unless
  the user changes them.

The fixed catalog is:

| Slots | Ticket value | Serial range | Tickets per roll |
| --- | ---: | --- | ---: |
| 1 | $20 | 000–024 | 25 |
| 2–3 | $10 | 000–024 | 25 |
| 4–7 | $5 | 000–049 | 50 |
| 8–10 | $3 | 000–074 | 75 |
| 11–15 | $2 | 000–124 | 125 |
| 16–20 | $1 | 000–249 | 250 |

### Canonical create request

This example starts from zero defaults while recording one scratch counter and
one Bodega ticket adjustment. All required money keys must be present.

```http
POST /api/reports/
Content-Type: application/json
X-CSRFToken: <current token>
X-Store-ID: 1
```

```json
{
  "report_date": "2026-09-14",
  "close_type": "shift",
  "close_label": "Evening",
  "lottery_terminal_sales": "0.00",
  "lottery_terminal_payout": "0.00",
  "phone_card_actual_sales": "0.00",
  "bodega_net_difference": "0.00",
  "bodega_lottery_sales": "0.00",
  "bodega_lottery_payout": "0.00",
  "bodega_phone_card_sales": "0.00",
  "bodega_gas_sales": "0.00",
  "gas_cash_sales": "0.00",
  "gas_lottery_sales": "0.00",
  "gas_lottery_payout": "0.00",
  "gas_phone_card_sales": "0.00",
  "gas_card_payment_sales": "0.00",
  "bodega_ai_tickets": [
    {"amount": "10.00", "description": "Customer ticket"}
  ],
  "tickets": [],
  "vendor_payouts": [],
  "safe_drops": [],
  "scratch_offs": [
    {"slot_number": 8, "ending_number": "006", "new_roll_count": 0}
  ]
}
```

The create response has this high-level shape:

```json
{
  "id": 123,
  "store_id": 1,
  "report_date": "2026-09-14",
  "close_type": "shift",
  "close_label": "Evening",
  "created_at": "2026-09-15T01:00:00+00:00",
  "calculated": {
    "inputs": {},
    "scratch_off": {"sales": "18.00", "slots": {}},
    "terminal": {},
    "comparisons": {},
    "registers": {},
    "normalized_line_items": [],
    "normalized_scratch_offs": []
  }
}
```

The omitted nested keys follow the TypeScript `Report` contract in
`frontend/src/report.ts` and the `_report_json` serializer in
`backend/reports/views.py`.

## 7. Accounting calculations

All authoritative formulas live in
`backend/reports/lottery/services.py::calculate_daily_report`.

### Cumulative terminal values

For a shift:

```text
shift terminal sales  = current cumulative sales - previous cumulative sales
shift terminal payout = current cumulative payout - previous cumulative payout
```

The first shift on each business date starts from cumulative zero. Neither
cumulative value may decrease within a date. Old shifts created before cumulative
entry was introduced have `terminal_values_cumulative = false`; replay adds their
stored per-shift values to the previous cumulative total in memory without
rewriting the historical input.

### Scratch-off sales

For each slot, the backend determines tickets sold and multiplies by the catalog
ticket value. Let:

- `P` be the previous last-ticket-sold number;
- `E` be the current ending number;
- `M` be the maximum serial;
- `R = M + 1` be the roll size;
- `N` be the number of new rolls added.

The principal cases are:

| Situation | Tickets sold |
| --- | ---: |
| No previous number, current `E` | `E` |
| Same active roll, `E >= P` | `E - P` |
| Current roll becomes blank/sold out | `M - P` |
| New rolls added | remaining prior tickets + complete middle rolls + current-roll tickets |

The no-prior rule intentionally treats 000 as the baseline counter. Therefore,
with no prior reading, ending `006` on a $3 ticket produces `6 × $3 = $18`, not
seven tickets.

When `E < P` and the user entered zero new rolls, the backend infers one new roll.
An explicit larger new-roll count is preserved. For a replacement:

```text
prior remaining = M - P            (zero if the prior roll was exhausted)
middle rolls    = (N - 1) × R
current portion = E + 1             (subject to the no-prior baseline rule)
tickets sold    = prior remaining + middle rolls + current portion
sales           = tickets sold × ticket value
```

A blank after an active numbered roll sells the remaining tickets and marks it
exhausted. A later numbered counter requires a new roll. Repeated blank readings
cannot sell the same exhausted roll again. The normalized database column
`new_roll_counter` stores `new_roll_count + 1` because it is a positive small
integer; API responses subtract one again.

### Reconciliation formulas

For an individual shift:

```text
phone expected = independent actual phone-card sales
phone actual   = Bodega phone-card sales + Verifone phone-card sales

lottery-sales expected = scratch-off sales + derived shift terminal sales
lottery-sales actual   = Bodega lottery sales + Verifone lottery sales

lottery-payout expected = derived shift terminal payout
lottery-payout actual   = Bodega lottery payout + Verifone lottery payout

difference = actual - expected
```

For a legacy day close, the entered terminal values are treated as day values.
For an automatic daily summary, scratch sales are summed across shifts, terminal
sales and payout use the final cumulative readings, and register values are
summed across shifts.

### Bodega AI Register Balance

```text
Bodega AI ticket total = sum(positive Bodega AI ticket entries)
Bodega AI Register Balance = entered Bodega net difference + ticket total
```

The raw entered net difference remains stored unchanged. Its sign convention is:

- positive (`+`) means short;
- negative (`-`) means over;
- zero means balanced.

The frontend explicitly adds `+` to positive final values and displays
`+ short / − over` below the result.

### Verifone Register Balance

The backend stores this raw value in `gas_net_difference`:

```text
gas_net_difference =
    Verifone total cash sales
  - gas sold through Bodega AI
  - safe-drop total
  - signed Verifone ticket total
  - vendor-payout total
  - card payments without fees
```

Phone-card sales are separate and do not participate in this formula. A negative
Verifone ticket amount is subtracted as a negative number and therefore adds to
the result, matching a customer payment of an earlier ticket.

The raw backend sign has the opposite meaning from the desired display. The
frontend alone transforms it:

```text
displayed Verifone Register Balance = -1 × gas_net_difference
```

Thus displayed `+` means over, displayed `-` means short, and zero is `$0.00`.
The UI shows `+ over / − short` beneath the signed currency. It does not mutate
the API value or database value.

Old reports that predate the independent card-payment field store that field as
`NULL`; their Verifone balance and related daily balance remain incomplete until
the report is edited with a real card-payment amount. The system does not guess
historical card payments.

## 8. Saving and replaying history

A save is more than inserting one row. It validates the report and reconstructs
the chronological state of that store.

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as Django API
    participant DB as Database
    B->>A: POST/PATCH report + session + CSRF + X-Store-ID
    A->>A: Parse bounded JSON and validate fields
    A->>DB: BEGIN transaction
    A->>DB: No-op UPDATE selected Store row
    Note over A,DB: Serializes concurrent saves for this store
    A->>DB: Insert/update raw report and replace line items
    A->>DB: Load all store reports in chronological order
    loop Every date, shifts first, legacy day last
        A->>A: Derive terminal delta and scratch baseline
        A->>A: Recalculate comparisons and register balances
        A->>DB: Update calculated snapshot and scratch rows
    end
    alt Any later report conflicts
        A-->>DB: ROLLBACK entire transaction
        A-->>B: 400 with conflicting report/date
    else Replay succeeds
        A-->>DB: COMMIT
        A-->>B: Saved report JSON
        B->>A: GET complete history
        A-->>B: Refreshed reports and daily summaries
    end
```

### Why the store row is updated

The transaction's first database write is a harmless update to the selected
`Store`. PostgreSQL serializes concurrent writers on that row; SQLite acquires
its write lock. Reports for different stores do not share the same serialization
row. This prevents two simultaneous closes from calculating against the same
stale scratch or terminal baseline.

### Replay order

The backend loads reports by `report_date`, `created_at`, and ID. Within each
date it processes shifts first in creation order, then the legacy day close. It
tracks:

- the previous business date's scratch ending state;
- scratch state after each shift;
- rolls added during the date;
- the prior cumulative terminal readings for the current date.

The final shift normally carries scratch inventory into the next date. If a
legacy day close exists, its ending inventory overrides that carry-forward.

If editing or backdating a report makes a later report invalid, Django raises a
history error identifying the later report. Because all work is inside one
atomic transaction, no partial recalculation is saved.

### Recalculation command

Use the management command after changing formulas or derived snapshot structure:

```bash
make recalculate
backend/.venv/bin/python backend/manage.py recalculate_reports --dry-run
backend/.venv/bin/python backend/manage.py recalculate_reports --store 1
```

It recalculates each store atomically and preserves entered values. Always run
`--dry-run` against production data first and back up the database before a rule
change that may expose historical conflicts.

## 9. Automatic daily summaries and history

`GET /api/reports/` returns two arrays:

```json
{
  "reports": [],
  "daily_summaries": []
}
```

`reports` contains saved shift and legacy-day rows. `daily_summaries` is built in
memory from chronologically ordered shifts.

For each business date, the daily builder:

1. sums all non-terminal money fields;
2. uses the last shift's cumulative terminal sales and payout;
3. aggregates scratch tickets, sales, new rolls, and final state by slot;
4. combines each line-item collection and retains the source shift ID/name;
5. computes daily register balances;
6. computes daily phone-card, lottery-sales, and payout comparisons.

If any included legacy shift has a missing card-payment value, the daily
Verifone balance is `null` rather than a misleading partial sum.

The frontend history menu sorts newest business dates first. Within a date it
shows automatic summaries, legacy day closes, and then shifts newest first. A
date filter narrows all three categories.

## 10. HTTP API

All bodies and successful responses are JSON. Decimal amounts are returned as
strings to preserve exact cents.

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health/` | Public | Liveness only; deliberately does not query the database |
| `GET` | `/api/auth/session/` | Public | User, accessible stores, and CSRF bootstrap/refresh |
| `POST` | `/api/auth/login/` | CSRF token | Authenticate and rotate the Django session/CSRF state |
| `POST` | `/api/auth/logout/` | Session and CSRF | End the session |
| `GET` | `/api/lottery/catalog/` | Public | Fixed 20-slot catalog |
| `GET` | `/api/reports/` | Session and store access | Saved history plus generated daily summaries |
| `POST` | `/api/reports/` | Session, CSRF, store access | Create a shift |
| `GET` | `/api/reports/{id}/` | Session and store access | One report within the selected store |
| `PUT` | `/api/reports/{id}/` | Session, CSRF, store access | Replace an existing report |
| `PATCH` | `/api/reports/{id}/` | Session, CSRF, store access | Merge fields into an existing report |

There is no public delete endpoint. Unsupported methods return 405. A report ID
from another store returns 404, avoiding disclosure of its existence.

### Required request headers

Authenticated report requests use the Django session cookie. Store-scoped calls
send:

```http
X-Store-ID: 1
```

Mutating calls also send the current token returned by the session endpoint:

```http
X-CSRFToken: <token>
```

The frontend sets `credentials: same-origin` when frontend and API share an
origin. If `VITE_API_BASE_URL` points to another origin, it uses
`credentials: include`; that deployment also needs exact CORS, trusted-origin,
HTTPS, and cross-site cookie settings.

### Errors

Validation errors use an `errors` value that may be a string, mapping, or nested
collection. `frontend/src/api.ts` flattens nested paths such as
`scratch_offs.2.ending_number`. `errorStep` sends the user to the earliest form
step containing an invalid field.

Important status codes include:

- `400`: malformed JSON, invalid values, history conflict, or conflicting row;
- `401`: authentication required or invalid credentials;
- `403`: no store membership or failed CSRF;
- `404`: inaccessible store/report;
- `405`: method not allowed;
- `413`: request body too large;
- `429`: login limit reached;
- `503`: transient SQLite lock or database deadlock that should be retried.

All `/api/` responses receive `Cache-Control: private, no-store` and vary by
cookie and store header so private data is not cached across sessions or stores.

## 11. Authentication and authorization

### Authentication

The application uses Django's built-in user model, password hashing,
authentication backend, database-backed sessions, and CSRF middleware. It does
not use JWTs or store credentials in the browser.

Login flow:

1. the browser calls `GET /api/auth/session/`;
2. Django ensures a CSRF cookie and returns the matching token;
3. the browser posts username/password with `X-CSRFToken`;
4. Django authenticates, rotates the session, and returns a fresh session view;
5. later writes use the current session cookie and CSRF token.

Login and logout are not CSRF-exempt. The custom CSRF failure response returns a
controlled JSON message for API calls.

### Store authorization

`StoreMembership` links ordinary users to stores. Superusers can access every
store. The `store_required` decorator:

1. requires an authenticated user;
2. obtains only that user's accessible stores;
3. validates `X-Store-ID` as a bounded positive ASCII integer;
4. finds the selected store inside the accessible queryset;
5. attaches it to `request.store`;
6. scopes every report query by that store.

The header is a selector, not proof of authorization. Sending another store's
ID cannot grant access. Membership revocation takes effect on the next request
without requiring logout. If the header is omitted, the backend selects the
first accessible store; the frontend sends it explicitly for every report call.

### Login throttling

Login attempts are limited in the database so the limits work across serverless
instances:

- 10 attempts per normalized account in 15 minutes;
- 60 attempts per client address in 15 minutes.

Keys are HMAC hashes, so usernames and IP addresses are not stored in the
throttle table. Successful and unsuccessful attempts both consume the budget;
blocked retries do not extend the window. Updates are atomic. On Vercel, the
middleware trusts only Vercel's overwritten forwarded-address header. IPv6
addresses are grouped by `/64`. Expired records are reset and old records are
deleted.

## 12. Other security boundaries

- Production requires a nonempty `DJANGO_SECRET_KEY`.
- Secure session and CSRF cookies default on when debug is off.
- Session cookies are HTTP-only and normally `SameSite=Lax`.
- Production redirects HTTP to HTTPS and enables one-year HSTS.
- Proxy HTTPS headers are trusted automatically only on Vercel, or explicitly
  when `DJANGO_TRUST_PROXY_HTTPS=True` is configured behind a trusted proxy.
- API request bodies are capped at 1 MiB; login bodies are capped at 16 KiB.
- JSON rejects `NaN`, `Infinity`, deeply malformed input, NULs, unsupported
  Unicode, invalid types, and excessively large strings/numbers.
- CORS echoes an origin only when it exactly matches
  `DJANGO_CORS_ALLOWED_ORIGINS`; credentialed requests are supported.
- Vercel adds a restrictive Content Security Policy, frame denial, MIME sniffing
  protection, a same-origin referrer policy, and disabled camera/geolocation/
  microphone permissions.

For same-origin production, CSRF is origin-and-token protection rather than
"port-to-port" security. Local ports are different origins, which is why local
trusted-origin/CORS configuration matters.

## 13. Frontend architecture

### Shared domain definitions

`frontend/src/report.ts` is the frontend source of truth for:

- API response types;
- field groups and labels;
- five form steps;
- initial values;
- edit hydration;
- money and register-balance display formatting;
- nested-error flattening and error-to-step routing.

Backend validation remains authoritative. Frontend types and constraints improve
the user experience but do not replace server validation.

### Application state

`App.tsx` owns session, selected store, catalog, reports, daily summaries, draft,
current step, selected report/summary, edit ID, errors, loading states, and
notices. No global state library is used.

On startup, it fetches session data and the scratch catalog concurrently. Once a
user and store are selected, a second effect fetches report history.

A monotonically increasing `generation` ref prevents late network responses from
an old user/store/session from overwriting newer state. Store changes, login,
logout, expiration, and access revocation clear private report state and drafts.

### Form workflow

The form has five steps:

1. shift date and optional name;
2. cumulative terminal readings and actual phone cards;
3. scratch-off counters;
4. Bodega AI inputs and optional tickets;
5. Verifone inputs and optional line items.

Native HTML constraint validation gates each step. Core amount boxes start empty
and untouched values become zero only at submission, so users can type without
first erasing `0.00` and can save a first zero-activity shift without repetitive typing.
These defaults do not bypass history rules: a later shift must enter cumulative
terminal readings at least as large as the preceding shift. Amount selectors
provide signs separately because iPhone numeric keyboards may omit a minus key.
Scratch serials use a digit-only text input to avoid floats.

When the server returns field errors, the app maps sparse submitted scratch rows
back to their visible catalog slots, moves to the earliest affected step, keeps
the draft, and renders accessible field messages.

### Save and refresh behavior

The final submit sends `POST` for new reports or `PATCH` for edits. On success it
shows the returned report, then requests the entire history because editing an
older report may have recalculated later reports. If saving succeeds but history
refresh fails, the UI says the report was saved and offers a refresh rather than
claiming the save failed.

### Views

- `ReportView` renders one shift or legacy day close.
- `DailySummaryView` renders a generated day summary and links to included shifts.
- `RegisterBalance` centralizes the two register display conventions.
- `Header` groups history by descending date, then daily summary, legacy day,
  and shifts.

The **Register Balances** card is the only primary display of calculated final
balances. **Entered figures** contains raw/user-entered values, including the raw
Bodega net difference and the Bodega ticket total. Reconciliation maintains its
own mathematical sign.

Responsive classes change tables into labeled cards and make action controls
full-width or sticky on small screens. Semantic labels, focus movement, status
roles, error associations, and minimum touch heights support keyboard and mobile
use.

## 14. Local development

### Prerequisites

- Python 3 and a platform supported by the locked Python 3.13 environment;
- Node.js 22.12 or newer (the setup script recommends Node 24 LTS);
- npm;
- optional Docker for local PostgreSQL.

### First setup

```bash
git clone https://github.com/theankitjoshi12345/Register_Report.git
cd Register_Report
make setup
```

The setup script installs/uses `uv`, creates `backend/.venv`, writes a private
`backend/.env` from the example when missing, runs migrations, and installs
frontend packages with `npm ci`.

### Run locally

Use two terminals:

```bash
make backend
```

```bash
make frontend
```

The frontend runs at `http://127.0.0.1:5173/` and Django at
`http://127.0.0.1:8000/`. Vite proxies `/api` to Django in development. Verify:

```bash
curl -I http://127.0.0.1:5173/
curl http://127.0.0.1:8000/api/health/
```

### Create administrative data

```bash
make admin
```

Then use local Django admin at `http://127.0.0.1:8000/admin/` to create stores
and memberships. The current Vercel routing sends only `/api/*` to Django, so
`/admin/` is not exposed by the production deployment.

### Optional local PostgreSQL

```bash
make db-up
```

Set this in `backend/.env`:

```dotenv
DATABASE_URL=postgresql://register_report:local-development-only@127.0.0.1:5432/register_report
```

Then run `make migrate` and restart Django. `make db-stop` stops PostgreSQL while
retaining its named volume. Switching database URLs does not copy data.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required signing secret; never commit it |
| `DJANGO_DEBUG` | Enables development behavior; false in production |
| `DATABASE_URL` | Django database connection; defaults to local SQLite |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated accepted hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact trusted frontend origins |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Exact cross-origin frontend origins |
| `DJANGO_CROSS_SITE_COOKIES` | Uses `SameSite=None` for a cross-site HTTPS frontend |
| `DJANGO_SECURE_COOKIES` | Overrides secure cookie behavior |
| `DJANGO_SSL_REDIRECT` | Overrides production HTTPS redirect behavior |
| `DJANGO_TRUST_PROXY_HTTPS` | Trust configured proxy HTTPS header outside Vercel |
| `VITE_API_BASE_URL` | Optional separately hosted API URL compiled into frontend |

Real process environment variables override `backend/.env`.

## 15. Production deployment

### Vercel request routing

`vercel.json` performs:

1. `npm --prefix frontend ci`;
2. `npm --prefix frontend run build`;
3. static serving from `frontend/dist`;
4. `/api/*` routing to `api/index.py`;
5. filesystem serving for built assets;
6. fallback of remaining browser routes to `index.html`.

`api/index.py` adds `backend/` to Python's import path, sets
`DJANGO_SETTINGS_MODULE=config.settings`, and exports the Django WSGI application
as `app`. Vercel includes the backend config, stores, and reports packages in the
function bundle. Root `requirements.txt` tells Vercel which Python dependencies
to install.

### Neon PostgreSQL

Production uses Neon through `DATABASE_URL`. SQLite is unsuitable for persistent
serverless production storage because the function filesystem is ephemeral.

Required production configuration normally includes:

```text
DATABASE_URL=<Neon connection string>
DJANGO_SECRET_KEY=<long random secret>
DJANGO_DEBUG=False
```

Add custom domains to allowed hosts and CSRF trusted origins when they are not
covered by Vercel's automatically supplied project host variables. Never put
database credentials or Django secrets in `VITE_*` variables because Vite embeds
those values in public JavaScript.

### Migrations

The Vercel build does not run Django migrations. Run them deliberately against
the production `DATABASE_URL` after reviewing migrations:

```bash
backend/.venv/bin/python backend/manage.py migrate --plan
backend/.venv/bin/python backend/manage.py migrate
```

Ensure the process has the production `DATABASE_URL` and `DJANGO_SECRET_KEY`
without printing them. When Vercel marks a value as non-downloadable, define it
in a protected local environment rather than expecting `vercel env pull` to
return the secret.

### Deployment verification

After pushing `main`:

```bash
npx vercel ls register-report
npx vercel inspect <deployment-url> --wait
curl -fsS https://register-report.vercel.app/api/health/
```

The health endpoint proves that the Django function imports and answers; it does
not prove database connectivity. Sign in and load report history, or run a
controlled database-backed check, to verify Neon separately.

## 16. Testing and quality gates

Run the complete project gate:

```bash
make check
```

It runs:

1. Django system checks;
2. `makemigrations --check --dry-run` to catch model changes without migrations;
3. all Django tests;
4. frontend lint;
5. frontend JSDOM workflow tests;
6. TypeScript and the production Vite build.

### Backend test responsibilities

| Test area | What it protects |
| --- | --- |
| `test_lottery_catalog.py` | Fixed slots, prices, ranges, integer parsing |
| `test_lottery_totals.py` | Scratch counting, roll transitions, money and reconciliation formulas |
| `test_report_history.py` | API saves, cumulative terminal logic, summaries, replay, legacy behavior |
| `test_recalculate_reports.py` | Management-command atomicity and dry runs |
| `test_report_migrations.py` | Preservation and backfill of historical data |
| `test_report_security.py` | Bounds, malformed input, concurrent and legacy edge cases |
| `stores/tests.py` | Sessions, CSRF, store isolation, revocation, CORS, login throttling |
| `config/tests.py` | Health contract, body limits, cache and proxy protections |

### Frontend test strategy

`frontend/tests/app.test.mjs` transpiles the actual TypeScript/React source and
runs it in JSDOM. It mocks only the network boundary. Tests exercise complete
form navigation, signed inputs, untouched zero closes, line items, edit
round-trips, history refresh, store switching, stale-response protection,
session expiration, error mapping, daily summaries, register sign presentation,
history ordering, and mobile-relevant input rules.

When changing a formula, add backend tests for the raw value and frontend tests
only for presentation. When changing a shared UI formatter, test both individual
shift and daily-summary views so they cannot diverge.

## 17. Safe extension patterns

### Add a required monetary field

1. Add it to `MONEY_FIELDS` in the backend calculation service.
2. Add a typed `DecimalField` migration to `DailyReport`.
3. Decide whether negative values are allowed and pass that rule to `_money`.
4. Include it in the relevant formula or summary aggregation.
5. Add it to the frontend field group and `AmountKey` source in `report.ts`.
6. Update response types and report/daily presentation.
7. Handle old rows explicitly: nullable migration, data migration, or safe
   backfill. Never invent unknown historical values.
8. Add calculation, API, migration, and frontend workflow tests.

### Add a line-item type

1. Add an `ITEM_TYPES` value and database migration.
2. Add the `(item_type, payload_key)` pair to `LINE_ITEM_FIELDS`.
3. Define sign and positivity validation in `_line_items` and database checks.
4. Add the frontend collection type, form group, editor, and summary card.
5. Confirm save replacement, normalized serialization, summary totals, maximum
   count, and descriptions with tests.

### Change scratch-off rules

Treat this as a historical-data change. Update the pure calculation service and
cover first readings, same-roll movement, exhaustion, lower counters, one and
multiple new rolls, omitted slots, and consecutive shifts. Then run the
recalculation command in dry-run mode against a copy of production data. A new
formula changes later baselines, so testing one isolated report is insufficient.

### Change a register sign convention

Keep three concepts separate:

1. raw entered value;
2. backend calculated/stored value;
3. user-facing formatted value.

The Bodega and Verifone displays intentionally use different meanings. Change
shared formatters and presentation tests without silently multiplying stored
values. Reconciliation signs are a separate mathematical difference.

### Add a new report type

Do not overload `close_type` without defining replay order, uniqueness, daily
aggregation, scratch baseline authority, terminal semantics, edit behavior, API
validation, history ordering, and migration behavior. Those rules are what make
shift and legacy-day records safe today.

## 18. Debugging guide

### Frontend says it failed to load

Check both processes locally:

```bash
curl -I http://127.0.0.1:5173/
curl http://127.0.0.1:8000/api/health/
```

Then inspect the browser network request. A frontend HTML response to `/api/*`
usually means proxy/routing is wrong. A controlled JSON 401 means the backend is
running and the user needs to sign in. CORS errors indicate the exact frontend
origin is missing from Django configuration.

### `DJANGO_SECRET_KEY must not be empty`

Django settings load before management commands such as `createsuperuser` or
`migrate`. Supply a nonempty secret in `backend/.env` or the process environment.
The database URL alone is insufficient.

### `createsuperuser` appears missing

That message can be secondary to settings import failure. Fix the first settings
exception, then rerun:

```bash
backend/.venv/bin/python backend/manage.py createsuperuser
```

### Production health works but login/history fails

The health endpoint makes no database query. Verify `DATABASE_URL`, migrations,
Neon reachability, session tables, and that the account has a `StoreMembership`.

### Older report says card payment is needed

That report predates `gas_card_payment_sales`. Edit it, enter the historical card
payment, and save. This will replay dependent history. The application correctly
keeps the old Verifone balance incomplete until the missing fact is supplied.

### Editing an older report reports a later conflict

The edited value changes a later scratch or terminal baseline. The entire save
was rolled back. Correct the identified later report or revise the earlier input;
do not bypass replay, because doing so would leave calculated history internally
inconsistent.

### Concurrent save returns 503

Another write holds the store/SQLite lock or PostgreSQL reported a deadlock. The
response includes `Retry-After: 1`; retry after the first transaction finishes.

## 19. Rebuilding the system from scratch

Build an equivalent implementation in dependency order. Starting with screens
before defining the historical accounting model usually creates data that cannot
be replayed safely.

### Step 1: define domain invariants

Write down business-date semantics, both register sign conventions, exact
reconciliation formulas, cumulative terminal behavior, scratch serial meaning,
roll transitions, store isolation, and the authority of legacy day closes. Use
the invariants in the final section as acceptance criteria.

### Step 2: create exact pure calculations

Implement the catalog and pure validation/calculation functions before database
or HTTP code. Use decimal money. Cover each scratch case with examples and test
off-by-one boundaries such as 000, maximum serial, blank exhaustion, lower
counters, and multiple rolls.

The pure calculation input should contain one report plus its explicit historical
baseline. Its output should contain normalized inputs, scratch results, terminal
deltas, comparisons, and register results. Keeping this layer free of request
and ORM code makes accounting tests deterministic.

### Step 3: model raw and normalized persistence

Create stores and memberships, then the report with typed raw money columns and
a calculated snapshot. Add normalized child rows for line items and scratch
state, foreign keys, uniqueness checks, value constraints, and useful indexes.
Plan nullable transitions for facts that older reports did not capture.

### Step 4: implement chronological replay

Load one store's reports oldest-first. Group by business date, reset cumulative
terminal baselines per date, process shifts in stable creation order, and apply
legacy-day inventory last. Persist each calculated snapshot and normalized
scratch state. Wrap save plus full replay in one transaction and serialize writes
using a per-store lock row.

### Step 5: derive daily summaries

Generate summaries from saved shifts rather than saving another editable total.
Use the last cumulative terminal reading, sum shift-local fields and line items,
aggregate scratch results, retain source shift identities, and propagate unknown
historical values instead of treating them as zero.

### Step 6: add authenticated, store-scoped APIs

Use secure session authentication and CSRF. Resolve the selected store through
the authenticated user's memberships for every report endpoint. Bound body
sizes, collection sizes, text, numbers, and nesting. Return structured field
errors and no-store cache headers.

### Step 7: build the frontend around the API contract

Define shared TypeScript types and field metadata, then implement bootstrapping,
login, store selection, the five-step form, save/edit refresh, history, individual
reports, and generated summaries. Keep raw, calculated, and displayed signs
separate. Protect state from stale asynchronous responses when identity or store
changes.

### Step 8: add compatibility and migrations

For every schema or formula change, decide how old rows behave before deploying.
Use explicit markers when the meaning of an existing field changes. Write data
migrations and recalculation tools that preserve original inputs and can run in
dry-run mode.

### Step 9: deploy as one origin

Build the SPA, route API traffic to the WSGI application, provide a durable
PostgreSQL database, set secure secrets, run migrations separately, and verify
both liveness and database-backed flows. Never rely on a serverless local file
for production persistence.

### Step 10: enforce the complete test gate

Test pure arithmetic, API validation, store isolation, CSRF, concurrency,
historical replay, migrations, user workflows, error recovery, and production
build output. Make the full gate a requirement for every deployment.

## 20. Architectural invariants

These rules should remain true after every change:

1. Every report read and write is scoped through authenticated store access.
2. CSRF protects login, logout, and report mutations.
3. Raw entered money uses exact decimals and remains distinguishable from derived
   and displayed values.
4. Cumulative terminal readings never decrease within a business date.
5. Scratch inventory is replayed chronologically within one atomic store save.
6. A failed replay changes no report.
7. Automatic daily summaries are derived from shifts and are not independently
   persisted.
8. Legacy day closes share the report table, cannot be newly created, and remain
   authoritative only for next-date scratch inventory.
9. Reconciliation difference is always `actual - expected`.
10. Bodega display signs mean `+ short / − over`.
11. Verifone raw values remain unchanged; displayed values are negated and mean
    `+ over / − short`.
12. Missing historical values remain unknown instead of being guessed.
13. Private API responses are never cacheable.
14. Late requests from a previous user or store cannot populate current UI state.
15. `make check` passes before a change reaches production.

Following these invariants and the extension procedures above is the shortest
path to rebuilding or extending the system without changing its accounting
meaning.
