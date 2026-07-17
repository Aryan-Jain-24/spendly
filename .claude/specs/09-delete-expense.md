# Spec: Delete Expense

## Overview
Step 9 replaces the placeholder `GET /expenses/<id>/delete` route (currently
`return "Delete expense — coming in Step 9"`) with a real action that lets a
logged-in user permanently remove an expense they previously created. This is
the first delete path into the `expenses` table from the UI. Because deleting
is a destructive, state-changing action, it must be triggered by a `POST`
request (never a plain `GET` link) and must ask for confirmation before it
fires. A user must only be able to delete their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 2: Registration (users exist)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend routes for profile page (`database/queries.py` pattern,
  profile page reads live expenses)
- Step 7: Add expense (`create_expense` helper style)
- Step 8: Edit expense (`get_expense_by_id` ownership-check pattern,
  `transaction-actions` markup on `profile.html`)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense, then redirect to
  `/profile` — logged-in only, owner only

The existing `delete_expense` view in `app.py` is rewritten as a POST-only
route (`methods=["POST"]`); the placeholder `GET` behavior is removed
entirely — deleting must never be reachable via a plain link or browser
prefetch.

If the expense does not exist, or exists but belongs to a different
`user_id`, respond with `404 Not Found` (do not reveal whether the id belongs
to someone else) — same pattern as `edit_expense`.

## Database changes
No schema changes. The `expenses` table already supports row deletion by
`id`.

## Templates
- **Modify**: `templates/profile.html` — add a "Delete" control next to the
  existing "Edit" link in each `transaction-actions` block. It must be a
  small `<form method="POST" action="{{ url_for('delete_expense', id=txn.id) }}">`
  containing a single submit button (styled as a link/ghost button, e.g.
  `transaction-delete-link`) — not an `<a>` tag, since the action mutates
  state.
- **Modify**: `static/js/main.js` — add a confirmation guard so submitting
  any `.transaction-delete-form` shows a native `confirm()` dialog ("Delete
  this expense?") and only submits if the user accepts.

## Files to change
- `app.py` — rewrite `delete_expense(id)` to require login, look up the
  expense and verify ownership via `get_expense_by_id` (404 if missing or not
  owned), call the new query helper, and redirect to `/profile` on success
- `database/queries.py` — add `delete_expense(expense_id, user_id)` helper
- `templates/profile.html` — add the delete form to each transaction row
- `static/js/main.js` — add the delete-confirmation guard

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (n/a for this feature, no password fields)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- The delete action must only be triggerable via `POST` — no `GET` route, no
  plain `<a href>` link
- `delete_expense` (the query helper) must filter by `user_id` in the `WHERE`
  clause (not just `id`) so one user can never delete another user's expense
  via a guessed id
- `delete_expense()` (the view) must redirect to `/login` if
  `session["user_id"]` is not set
- `delete_expense()` (the view) must return `404` if the expense does not
  exist or does not belong to the logged-in user (checked before deleting
  anything), reusing `get_expense_by_id` from Step 8
- On success, redirect to `/profile` (no confirmation page server-side; the
  confirmation happens client-side before the request is sent)
- The client-side confirmation must not block or replace the server-side
  ownership/404 checks — it's a UX safeguard only, not a security control

## Tests to write

### Unit tests
File: `tests/test_delete_expense.py`

| Function | Input | Expected output |
|---|---|---|
| `delete_expense` | valid id + owning user_id | row removed from `expenses`, no longer returned by `get_expense_by_id` or `get_recent_transactions` |
| `delete_expense` | valid id + non-owning user_id | no row removed |
| `delete_expense` | non-existent id | no error, no row removed |

### Route tests
`POST /expenses/<id>/delete` — unauthenticated:
- Redirects to `/login` (302), no row removed

`POST /expenses/<id>/delete` — authenticated, owns the expense:
- Redirects to `/profile` (302)
- Expense no longer appears in the profile page's transaction list and is
  reflected in `total_spent` / `transaction_count` / category breakdown

`POST /expenses/<id>/delete` — authenticated, does not own the expense:
- Returns 404, no row removed

`POST /expenses/<id>/delete` — authenticated, id does not exist:
- Returns 404

`GET /expenses/<id>/delete` — any state:
- Returns 405 Method Not Allowed (no GET handler exists)

## Definition of done
- [ ] Visiting `/expenses/<id>/delete` directly via `GET` (e.g. typing the
      URL) returns a 405, not a deletion
- [ ] Each row in "Recent transactions" on `/profile` has a working Delete
      control next to Edit
- [ ] Clicking Delete shows a confirmation dialog before anything is sent
- [ ] Confirming the dialog removes the expense and redirects to `/profile`
- [ ] The deleted expense no longer appears in "Recent transactions"
- [ ] `Total spent`, `Transactions`, and the category breakdown on
      `/profile` reflect the deletion immediately
- [ ] Dismissing the confirmation dialog leaves the expense untouched
- [ ] Submitting a delete for an expense you don't own (e.g. via a crafted
      request) returns 404 and the row is not removed
