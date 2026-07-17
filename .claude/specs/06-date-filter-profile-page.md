
# Spec: Date Filter For Profile Page

## Overview

This step adds a date-range filter to the `/profile` page, letting a logged-in user narrow their summary stats, recent transactions, and category breakdown down to a custom time period instead of always seeing all-time data. It builds directly on Step 5, which wired those three panels to live queries in `database/queries.py` — this step adds an optional date range to those same queries and a small form on the profile page to submit it. This is the "Filter by time period" capability already teased on the landing page's feature list; no new pages, tables, or auth behavior are introduced.

## Depends on

- Step 1 — Database setup (`expenses` table with a `date` column in `YYYY-MM-DD` format).
- Step 3 — Login and Logout (`session["user_id"]`).
- Step 5 — Backend routes for profile page (`database/queries.py` helpers, dynamic `profile.html` sections) must be complete — this step modifies those exact functions and that exact template.

## Routes

No new routes. The existing `GET /profile` route is modified to accept two optional query-string parameters:

- `start` — `YYYY-MM-DD`, inclusive lower bound
- `end` — `YYYY-MM-DD`, inclusive upper bound

Both are optional. If neither is present, `/profile` behaves exactly as it does today (all-time data, transactions capped at 10).

## Database changes

No database changes. `expenses.date` is already stored as `YYYY-MM-DD` text, which sorts and compares correctly as a string, so range filtering only needs an added `WHERE date >= ? AND date <= ?` clause — no schema change.

## Templates

**Create:** None.

**Modify:**
- `templates/profile.html`
  - Add a date filter form above the stats grid: two `<input type="date">` fields (`start`, `end`), an "Apply" submit button, and a "Clear" link back to `/profile` with no query params. Form uses `method="GET"` so the range is shareable/bookmarkable via the URL.
  - Repopulate the `start`/`end` inputs with the currently active values (sticky filter) using `value="{{ start or '' }}"` / `value="{{ end or '' }}"`.
  - If a validation error is present (e.g. start after end), show it using the existing `.auth-error`-style pattern above the form.
  - When a filter is active and no expenses fall in range, show a distinct empty-state message (e.g. "No expenses between {{ start }} and {{ end }}.") instead of the generic "No transactions yet." used for a brand-new account.

## Files to change

- `app.py`
  - In `profile()`, read `start` and `end` from `request.args`.
  - Validate: if present, each must parse as `YYYY-MM-DD` (`datetime.strptime(value, "%Y-%m-%d")`); if both are present, `start` must be `<= end`.
  - On invalid input (bad format or `start` after `end`): ignore the filter values when querying (treat as all-time), but pass a `filter_error` message to the template and keep the user's raw submitted `start`/`end` in the inputs so they can correct it.
  - On valid input: pass `start`/`end` through to `get_summary_stats`, `get_recent_transactions`, and `get_category_breakdown`.
  - Pass `start`, `end`, and `filter_error` to `render_template` alongside the existing `user`, `summary`, `transactions`, `categories`.
- `database/queries.py`
  - Add optional `start_date=None, end_date=None` parameters to `get_summary_stats`, `get_recent_transactions`, and `get_category_breakdown`.
  - When either bound is provided, append a parameterized `AND date >= ?` / `AND date <= ?` clause to each function's `WHERE user_id = ?` query — never string-format the dates into SQL.
  - When `start_date`/`end_date` are provided to `get_recent_transactions`, return every matching row (not just the default `limit`) so the user sees the full period, not a truncated recent slice.
- `templates/profile.html` — filter form and sticky/error/empty-state handling described above.
- `static/css/style.css` — style for the new filter form (`.filter-form`, its date inputs, apply button, clear link), reusing `.form-input` / `.btn-primary` / `.btn-ghost` and existing CSS variables where they already fit; add only what's missing (e.g. horizontal layout for the two date fields + buttons).

## Files to create

None.

## New dependencies

No new dependencies — date parsing/validation uses the standard library `datetime`, already imported patterns exist elsewhere in this codebase.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterised queries only — the date bounds are bind parameters, never interpolated into the SQL string.
- Passwords hashed with werkzeug (unaffected by this step).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- `database/queries.py` functions stay pure (no Flask imports, no `request` access) — `app.py` is responsible for reading and validating `request.args` and passing plain values in.
- Close every `get_db()` connection on every code path, including the new filtered branches.
- Treat `start`/`end` as inclusive bounds on both ends.
- Invalid or contradictory input (bad date format, `start` after `end`) must never raise a 500 — fall back to unfiltered data and surface a user-facing error message instead.
- Category breakdown percentages must still sum to 100 for whatever subset of expenses matches the active filter (reuse the existing largest-category rounding-remainder logic from Step 5).

## Definition of done

- [ ] Visiting `/profile` with no query params behaves exactly as before Step 6 (all-time stats, 10 most recent transactions).
- [ ] Visiting `/profile?start=2026-07-01&end=2026-07-15` narrows summary stats, the transaction list, and the category breakdown to only expenses dated in that inclusive range.
- [ ] The `start` and `end` inputs are pre-filled with the values from the URL after filtering.
- [ ] A range with zero matching expenses shows ₹0.00 / 0 transactions and a "no expenses in this range" message — not an error, not the brand-new-account empty state.
- [ ] Submitting `start` after `end` shows a validation error message and falls back to showing all-time data (does not crash, does not silently apply a broken filter).
- [ ] A "Clear" link/button returns to `/profile` with no query params and restores the all-time view.
- [ ] All amounts on the filtered view still display the ₹ symbol.
- [ ] Category breakdown percentages for a filtered range sum to 100 whenever any expenses match.
- [ ] App starts without errors; `/`, `/register`, `/login`, `/logout` remain unaffected.
