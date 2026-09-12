# Register Report

A store-closing reconciliation app built with React, TypeScript, Tailwind CSS,
and Django. Enter machine totals, scratch-off counters, and figures from the
Bodega AI and Verifone registers. The app saves a report showing sales/payout
comparisons and register differences.

## Run locally

Requirements: Node.js (see `.nvmrc`), Python 3 with pip, and `make`. Docker is
optional. The setup script installs the locked frontend dependencies and a
project-local Python 3.13 environment, creates `backend/.env` if it does not
exist, and applies the database migrations. SQLite is the default, so no database
server is needed for local development.

Run setup once from the project directory:

```sh
make setup
make admin
```

`make admin` prompts for a username and password for the first administrator.
There are no default credentials. Run it again only when you need another
administrator.

Start the two development servers in separate terminals, leaving both running:

Terminal 1:

```sh
make backend
```

Terminal 2:

```sh
make frontend
```

Open <http://127.0.0.1:5173> and sign in. Django listens on port 8000; Vite
forwards `/api/`, `/admin/`, and `/static/` to it. Keep both terminals open while
using the app. On an existing checkout, use `make migrate` instead of running the
full setup again.

The administrator site is separate from the report app:

- Report app: <http://127.0.0.1:5173>
- Django admin: <http://127.0.0.1:8000/admin/>
- API health check: <http://127.0.0.1:8000/api/health/>

### If the app says “failure to load”

That message normally means the frontend cannot reach Django. Check that both
`make backend` and `make frontend` are still running, then open the health-check
URL above. It should return `{"status": "ok", ...}`. If the health check works,
refresh <http://127.0.0.1:5173>. If either server reports an error, stop that
process, run `make migrate`, and start it again. The app must be opened at port
5173; opening the Django port directly does not serve the React interface.

When upgrading an existing database, refresh its saved calculation snapshots
after migrating. First validate without saving, then perform the recalculation:

```sh
backend/.venv/bin/python backend/manage.py recalculate_reports --dry-run
make recalculate
```

The first command validates history without saving changes. Recalculation is
atomic per store and reports incompatible counters without changing that store's
data. Original entries are preserved. To limit the operation to one store, pass
the option directly:

```sh
backend/.venv/bin/python backend/manage.py recalculate_reports --store 2 --dry-run
backend/.venv/bin/python backend/manage.py recalculate_reports --store 2
```

## Stores and access

The migration creates **Main store** and assigns existing daily reports to it.
Administrators can access every store. To add stores or give another user access,
open <http://127.0.0.1:8000/admin/>:

1. Create a user under **Users**. Ordinary report users do not need staff status.
2. Create or open a store under **Stores**.
3. Add the user to that store's **membership** list and save.

Members can view, create, and edit reports for their assigned stores. The app has
a store selector when more than one store is available. Report queries, edits,
and scratch-off history are scoped to the selected store. Login uses Django
sessions, and writes require a CSRF token. Removing membership revokes access on
the next request.

Sign-in attempts are limited in the database across application instances: ten
attempts per account and sixty attempts per client network within fifteen
minutes. The stored counters use keyed hashes rather than usernames or IP
addresses. Successful attempts count toward the limit, and a blocked retry does
not extend the fifteen-minute window.

## Closing shifts and reviewing the day

The form has five steps: shift details, machine totals, scratch-off counters,
Bodega AI figures, and Verifone figures. Monetary fields are required;
explicit zero is accepted. Bodega's net difference may be negative. Tickets,
vendor payouts, and safe drops are optional lists with amounts and descriptions.
Signed fields use a separate `+`/`−` selector so they work with mobile numeric
keypads that do not provide a minus key.

A shift close covers activity since the previous shift. Scratch-off counters
follow earlier shifts in creation order, including the final shift from the
previous business date. Register amounts and new-roll counts cover only the
current shift.

Lottery terminal sales and payout are different: enter the terminal's current
**cumulative** readings without subtracting earlier shifts. The backend assigns
the first shift the full reading and assigns later shifts the difference from
the preceding cumulative reading. A cumulative reading cannot decrease within a
business date.

Existing shift rows from the earlier workflow retain their original per-shift
terminal amounts. A compatibility marker lets history replay translate them to
cumulative readings without rewriting those saved inputs. Saving an edited
legacy shift stores the displayed cumulative reading in the new format.

The application derives a daily summary automatically. It combines every shift,
uses the final cumulative terminal readings for day-end lottery reconciliation,
sums scratch-off sales and new rolls, carries the final scratch state forward,
and totals register figures, phone cards, safe drops, tickets, and vendor
payouts. Previously saved manual day closes remain editable legacy records.

History lets you review individual shifts, automatic daily summaries, and legacy
day closes. Correcting or backdating a shift recalculates subsequent scratch-off
and terminal results for that store. If a correction makes a later counter or
cumulative reading invalid, the save identifies the conflicting report and the
transaction leaves the history unchanged.

## Calculation rules

| Comparison | Expected | Recorded by the registers |
| --- | --- | --- |
| Phone-card sales | Independent phone-card machine sales | Bodega phone-card sales + Verifone phone-card sales |
| Shift lottery sales | Current cumulative terminal sales − previous cumulative terminal sales | Bodega lottery sales + Verifone lottery sales |
| Shift lottery payouts | Current cumulative terminal payout − previous cumulative terminal payout | Bodega lottery payout + Verifone lottery payout |

Difference = recorded − expected. Exactly zero is a match. Django validates
money using decimal arithmetic with up to two decimal places and at most
9,999,999,999.99 per entered amount.

Bodega's net difference is entered directly. Verifone net difference is:

```text
Verifone total cash sales
− Gas sold through Bodega
− Safe drops
− Tickets
− Vendor payouts
− Card payment without including fee
```

**Phone cards and debit/credit payments are separate entries.** The old internal
`gas_card_sales` field represented Verifone phone-card sales despite its label.
Its saved values are preserved under `gas_phone_card_sales`. The new
`gas_card_payment_sales` field supplies the independent card-payment deduction.
Older reports show an incomplete Verifone balance until that newly required amount is
entered; no historical payment amount is guessed. After entering it, save the
report once to store the completed balance.

Scratch-offs have a fixed 20-slot catalog in
`backend/reports/lottery/catalog.py`. An ending counter means the **last ticket
sold**: 020 on a 000–024 roll leaves four tickets, 021–024. For an active roll,
tickets sold normally means today's ending counter minus the previous counter.
Replacing a roll counts the remainder of the old roll, any complete additional
rolls, and tickets 000 through the last ticket sold on the current roll. This
convention is consistent across first readings, shifts, and roll replacements;
completing a 25-ticket roll can never count 26 tickets.

A blank ending after a known counter means the remainder of that roll sold.
Repeated blanks on that exhausted roll add no further sales; enter a new-roll
count before resuming a counter. With no prior reading, blank means no baseline
and zero sales, while the first numerical reading counts from ticket 000.
Omitted slots carry their prior state forward. Initial inventory therefore needs
accurate opening history before relying on the first reported day's sales.

## API

All report endpoints require a signed-in session. Select a store with the
`X-Store-ID` header; if omitted, the first accessible store is used. Mutations also
require `X-CSRFToken`, obtained from the session endpoint.

API request bodies are limited to 1 MiB, with a 16 KiB limit for login. A report
can contain up to 500 entries in each optional line-item group. These limits keep
one request from consuming unbounded memory or database work. API responses use
`private, no-store` and vary by session and selected store so authenticated data
is not reused by shared caches.

| Endpoint | Methods | Purpose |
| --- | --- | --- |
| `/api/auth/session/` | GET | Current user, accessible stores, CSRF token |
| `/api/auth/login/` | POST | Sign in with username/password; returns a fresh token |
| `/api/auth/logout/` | POST | End the session |
| `/api/lottery/catalog/` | GET | Public slot prices and counter limits |
| `/api/reports/` | GET, POST | List shifts and derived daily summaries, or create a shift |
| `/api/reports/<id>/` | GET, PUT, PATCH | Retrieve, replace, or partially update a report |
| `/api/health/` | GET | Application liveness; does not check the database |

Inputs and calculation snapshots are saved on `DailyReport`. Individual entries
and scratch-off states also have queryable `ReportLineItem` and `ScratchOffRoll`
records. Older lottery-only models remain for compatibility and are not used by
the current report API.

## Verification

```sh
make check
```

Runs Django system checks, migration consistency checks, backend tests, frontend
lint, frontend interaction tests, and the production frontend build. The tests
cover reconciliation, malformed inputs, report/history edits, store isolation,
session/CSRF behavior, and form navigation. Frontend interaction tests run against
a simulated DOM. The repaired workflow was also verified in local headless Chrome
against an isolated database: login, all five steps, save/edit, persistence after
reload, store switching, and logout. The Vercel deployment was verified against
its public frontend, health endpoint, and Neon-backed session endpoint.

## Vercel and production deployment

Vercel builds the React frontend and exposes Django as a Python Function at
`/api/*`. The frontend and API therefore use the same HTTPS origin, and the
frontend does not need `VITE_API_BASE_URL` in this deployment.

The production database is the `neon-blue-bucket` Neon Postgres resource
connected through the Vercel Marketplace. It supplies `DATABASE_URL` to the
Production, Preview, and Development environments. SQLite remains the default
when `DATABASE_URL` is absent, including ordinary local development.

Set these additional variables in every Vercel environment that will run the
API:

```text
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<unique private value>
DJANGO_SECURE_COOKIES=True
```

Vercel automatically supplies the generated deployment and production
hostnames; Django adds both to its allowed hosts and trusted CSRF origins. Run
database migrations before using a newly provisioned Neon database:

```sh
npx vercel env run -e production -- backend/.venv/bin/python backend/manage.py migrate
```

Create the first administrator interactively with the same command prefix and
`createsuperuser`. Vercel does not download values stored as Secret variables,
so provide a temporary local signing key for this management command:

```sh
DJANGO_SECRET_KEY=local-management-command \
  npx vercel env run -e production -- \
  backend/.venv/bin/python backend/manage.py createsuperuser
```

This temporary value only lets Django initialize locally; it does not replace
the private `DJANGO_SECRET_KEY` used by the deployed application. Do not place
`DATABASE_URL` or the production secret in source control.

In Vercel Project Settings, turn off Deployment Protection for the public
production deployment. A URL that redirects to `vercel.com/sso-api` is protected
by Vercel and cannot be used by public visitors. The repository's `vercel.json`
routes `/api/*` to Django and all other application routes to the React SPA.

## PostgreSQL and deployment

SQLite is the default local database. To use the included PostgreSQL 17 service,
start Docker and run `make db-up`. In `backend/.env`, set:

```dotenv
DATABASE_URL=postgresql://register_report:local-development-only@127.0.0.1:5432/register_report
```

Then run `make migrate` and restart Django. Switching the database does not copy
existing SQLite data. `make db-stop` retains the PostgreSQL volume.

The Vercel deployment needs HTTPS, a private Django secret, and the connected
Neon database. Secure session and CSRF cookies default on when debug is off.
Production responses redirect HTTP to HTTPS, enable HSTS, and include a content
security policy, clickjacking protection, content-type sniffing protection, a
same-origin referrer policy, and a restrictive browser permissions policy.
Vite's local preview command serves the frontend build only; use the normal
two-server development commands when testing the API locally.

## Structure

```text
backend/config/       Django settings and URL routes
backend/stores/       Store memberships, login/session API, admin management
backend/reports/      Models, report API, calculations, and history replay
frontend/src/         Form, login, report display, and browser state
api/index.py          Vercel Python Function entry point for Django
scripts/setup.sh      Repeatable local dependency/database setup
compose.yaml          Optional local PostgreSQL service
Makefile              Setup, development, and verification commands
PERSONAL.md           Store requirements and product decisions
PLAN.md               Implementation status and remaining product work
```
