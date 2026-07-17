# Spec: Edit Expense

## Overview
Step 8 replaces the placeholder `GET /expenses/<id>/edit` route (currently
`return "Edit expense — coming in Step 8"`) with a real form that lets a
logged-in user modify an expense they previously created. This is the first
update path into the `expenses` table from the UI. The route must handle
both displaying the form pre-filled with the existing expense (GET) and
saving changes (POST), then send the user back to their profile page where
the updated values appear in the transaction list and stats. A user must
only be able to edit their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 2: Registration (users exist)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (`database/queries.py` pattern,
  profile page reads live expenses)
- Step 7: Add expense (`add_expense.html` form pattern, `CATEGORIES`
  validation, sticky-form-on-error pattern, `create_expense` helper style)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the
  expense's current values — logged-in only, owner only
- `POST /expenses/<int:id>/edit` — validate and update the expense, then
  redirect to `/profile` — logged-in only, owner only

Both methods are handled by the existing `edit_expense` view in `app.py`
(update its `methods=` to `["GET", "POST"]`).

If the expense does not exist, or exists but belongs to a different
`user_id`, respond with `404 Not Found` (do not reveal whether the id
belongs to someone else).

## Database changes
No schema changes. The `expenses` table already has all required columns
(`user_id`, `amount`, `category`, `date`, `description`, `created_at`).

`get_recent_transactions` in `database/queries.py` currently selects only
`date, description, category, amount` — it must be updated to also select
`id`, since `profile.html` needs each transaction's id to link to its edit
page.

## Templates
- **Create**: `templates/edit_expense.html`
  - Extends `base.html`
  - Same fields as `add_expense.html`: `amount` (number input), `category`
    (select, populated from `database.db.CATEGORIES`), `date` (date input),
    `description` (optional text input) — all pre-filled with the expense's
    current values on GET
  - Form posts to `{{ url_for('edit_expense', id=expense.id) }}`
  - Shows a validation error message above the form when present (reuse the
    `auth-error` pattern used on `add_expense.html`)
- **Modify**: `templates/profile.html` — add an "Edit" link on each row in
  the "Recent transactions" list, pointing to
  `{{ url_for('edit_expense', id=txn.id) }}`

## Files to change
- `app.py` — update `edit_expense(id)` to accept `GET`/`POST`, require
  login, look up the expense and verify ownership (404 if missing or not
  owned), validate form input on POST, call the new query helpers, and
  redirect to `/profile` on success
- `database/queries.py` — add `get_expense_by_id(expense_id, user_id)` and
  `update_expense(expense_id, user_id, amount, category, date, description)`
  helpers; update `get_recent_transactions` to also select `id`
- `templates/profile.html` — add the edit link to each transaction row

## Files to create
- `templates/edit_expense.html` — the edit-expense form

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (n/a for this feature, no password fields)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $
- `get_expense_by_id` and `update_expense` must both filter by `user_id` in
  the `WHERE` clause (not just `id`) so one user can never read or write
  another user's expense via a guessed id
- `category` must be validated against `database.db.CATEGORIES` — reject
  anything else with a 400 and an error message
- `amount` must parse as a positive number (> 0) — reject zero, negative, or
  non-numeric input with a 400 and an error message
- `date` must be a valid `YYYY-MM-DD` string (reuse the same validation
  style as `_parse_date_filter` in `app.py` / the `add_expense` route)
- `description` is optional — store `None`/empty as-is, no default text
  substitution at write time
- On any validation error, re-render `edit_expense.html` with the error and
  the user's submitted values still filled in (sticky form, same pattern as
  `add_expense.html`)
- On success, redirect to `/profile` (not back to the edit-expense form)
- `edit_expense()` must redirect to `/login` if `session["user_id"]` is not
  set
- `edit_expense()` must return `404` if the expense does not exist or does
  not belong to the logged-in user (checked before touching `request.form`)

## Tests to write

### Unit tests
File: `tests/test_edit_expense.py`

| Function | Input | Expected output |
|---|---|---|
| `get_expense_by_id` | valid id + owning user_id | returns the expense row |
| `get_expense_by_id` | valid id + non-owning user_id | returns `None` |
| `get_expense_by_id` | non-existent id | returns `None` |
| `update_expense` | valid id, owning user_id, new values | row updated in `expenses`, visible via `get_recent_transactions` |
| `update_expense` | valid id, non-owning user_id | no row changed |

### Route tests
`GET /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/<id>/edit` — authenticated, owns the expense:
- Returns 200 and includes a form pre-filled with the expense's current
  `amount`, `category`, `date`, `description`

`GET /expenses/<id>/edit` — authenticated, does not own the expense:
- Returns 404

`GET /expenses/<id>/edit` — authenticated, id does not exist:
- Returns 404

`POST /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302), no row changed

`POST /expenses/<id>/edit` — authenticated, owns the expense, valid data:
- Redirects to `/profile` (302)
- Updated expense appears in the profile page's transaction list and is
  reflected in `total_spent` / `transaction_count` / category breakdown

`POST /expenses/<id>/edit` — authenticated, does not own the expense:
- Returns 404, no row changed

`POST /expenses/<id>/edit` — authenticated, owns the expense, invalid data:
- Missing/zero/negative `amount` → 400, form re-rendered with error, row
  unchanged
- Invalid `category` (not in `CATEGORIES`) → 400, form re-rendered with
  error, row unchanged
- Invalid/missing `date` → 400, form re-rendered with error, row unchanged

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense you own shows a form
      pre-filled with its current amount, category, date, and description
- [ ] Visiting `/expenses/<id>/edit` for an expense you don't own, or an id
      that doesn't exist, returns a 404
- [ ] The "Recent transactions" list on `/profile` has a working edit link
      per row
- [ ] Submitting the edit form with valid data redirects to `/profile`
- [ ] The updated values appear in "Recent transactions" on the profile
      page immediately after saving
- [ ] `Total spent`, `Transactions`, and the category breakdown on
      `/profile` reflect the edited expense immediately
- [ ] Submitting with a negative or zero amount shows a validation error
      and does not change the row
- [ ] Submitting with an invalid date format shows a validation error and
      does not change the row
- [ ] Submitting with no description succeeds and the transaction row falls
      back to showing the category name (existing profile page behavior)
