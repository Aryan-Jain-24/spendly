# Spec: Add Expense

## Overview
Step 7 replaces the placeholder `GET /expenses/add` route (currently `return
"Add expense — coming in Step 7"`) with a real form that lets a logged-in
user record a new expense. This is the first write path into the `expenses`
table from the UI — until now expenses only exist via `seed_db()`. The route
must handle both displaying the form (GET) and creating the expense (POST),
then send the user back to their profile page where the new expense appears
in the transaction list and stats.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 2: Registration (users exist)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (`database/queries.py` pattern,
  profile page reads live expenses)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert a new expense, then redirect to
  `/profile` — logged-in only

Both methods are handled by the existing `add_expense` view in `app.py`
(update its `methods=` to `["GET", "POST"]`).

## Database changes
No database changes. The `expenses` table already has all required columns
(`user_id`, `amount`, `category`, `date`, `description`, `created_at`).

## Templates
- **Create**: `templates/add_expense.html`
  - Extends `base.html`
  - Form fields: `amount` (number input), `category` (select, populated from
    `database.db.CATEGORIES`), `date` (date input, defaults to today), and
    `description` (optional text input)
  - Shows a validation error message above the form when present (reuse the
    `auth-error` pattern used on `register.html` / `login.html` /
    `profile.html`)
- **Modify**: `templates/profile.html` — none required, but confirm the
  "Recent transactions" panel picks up newly added expenses on next profile
  load (no template change expected since it already reads live data)

## Files to change
- `app.py` — update `add_expense()` to accept `GET`/`POST`, require login,
  validate form input, call the new query helper on POST, and redirect to
  `/profile` on success
- `database/queries.py` — add `create_expense(...)` helper

## Files to create
- `templates/add_expense.html` — the add-expense form
- `database/queries.py` addition: `create_expense(user_id, amount, category, date, description)`
  — inserts a row into `expenses` and returns nothing (or the new row id)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $
- `category` must be validated against `database.db.CATEGORIES` — reject
  anything else with a 400 and an error message
- `amount` must parse as a positive number (> 0) — reject zero, negative, or
  non-numeric input with a 400 and an error message
- `date` must be a valid `YYYY-MM-DD` string (reuse the same validation style
  as `_parse_date_filter` in `app.py`) — reject invalid/missing dates with a
  400 and an error message
- `description` is optional — store `None`/empty as-is, no default text
  substitution at write time (the profile page already falls back to
  `txn.category` for display when `description` is empty)
- On any validation error, re-render `add_expense.html` with the error and
  the user's submitted values still filled in (sticky form, same pattern as
  the profile date filter)
- On success, redirect to `/profile` (not back to the add-expense form)
- `add_expense()` must redirect to `/login` if `session["user_id"]` is not set

## Tests to write

### Unit tests
File: `tests/test_add_expense.py`

| Function | Input | Expected output |
|---|---|---|
| `create_expense` | valid user_id, amount, category, date, description | row inserted in `expenses`, visible via `get_recent_transactions` |
| `create_expense` | description omitted / empty | row inserted with empty/`None` description |

### Route tests
`GET /expenses/add` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/add` — authenticated:
- Returns 200 and includes a form with `amount`, `category`, `date`,
  `description` fields
- Category `<select>` includes all values from `database.db.CATEGORIES`

`POST /expenses/add` — unauthenticated:
- Redirects to `/login` (302), no row inserted

`POST /expenses/add` — authenticated, valid data:
- Redirects to `/profile` (302)
- New expense appears in the profile page's transaction list and is
  reflected in `total_spent` / `transaction_count`

`POST /expenses/add` — authenticated, invalid data:
- Missing/zero/negative `amount` → 400, form re-rendered with error, no row
  inserted
- Invalid `category` (not in `CATEGORIES`) → 400, form re-rendered with
  error, no row inserted
- Invalid/missing `date` → 400, form re-rendered with error, no row inserted

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows a form with amount,
      category, date, and description fields
- [ ] The category dropdown lists exactly the 7 categories from
      `database.db.CATEGORIES`
- [ ] Submitting the form with valid data redirects to `/profile`
- [ ] The newly added expense appears in "Recent transactions" on the
      profile page with the correct amount, category, date, and description
- [ ] `Total spent` and `Transactions` stat cards on `/profile` reflect the
      new expense immediately after adding it
- [ ] Submitting with a negative or zero amount shows a validation error and
      does not create a row
- [ ] Submitting with an invalid date format shows a validation error and
      does not create a row
- [ ] Submitting with no description succeeds and the transaction row falls
      back to showing the category name (existing profile page behavior)
