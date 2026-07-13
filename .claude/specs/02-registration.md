# Spec: Registration

## Overview

This step implements user registration for Spendly. Visitors can create an account with a name, email, and password from the existing `/register` page. On success, the password is hashed and the user is stored in the `users` table, then logged in automatically via a Flask session so they can reach the (still-placeholder) authenticated pages built in later steps. This is the first step that writes to the `users` table outside of `seed_db()`, and it establishes the session-based login pattern that Step 3 (logout) and Step 4 (profile) will build on.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`) must be complete.

## Routes

- `GET /register` — renders the registration form — public (already exists, unchanged)
- `POST /register` — validates input, creates the user, starts a session, redirects to `/profile` — public

## Database changes

No database changes. The existing `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) already supports registration as defined in `database/db.py`.

## Templates

**Create:** None — `register.html` already exists.

**Modify:**
- `templates/register.html` — no structural changes required; it already renders `{{ error }}` and repopulates via standard form fields. Only re-verify field `name` attributes (`name`, `email`, `password`) match what `app.py` reads from `request.form`.

## Files to change

- `app.py`
  - Set `app.secret_key` so Flask sessions work.
  - Change the `/register` route to accept `methods=["GET", "POST"]`.
  - On `POST`: read and trim `name`, `email`, `password` from `request.form`.
  - Validate: all fields required, password minimum 8 characters, email not already registered.
  - On validation failure: re-render `register.html` with `error` set and a 400 status, without hitting the database.
  - On success: hash the password with `generate_password_hash`, insert the user via `get_db()` using a parameterized query, set `session["user_id"]` to the new user's id, and redirect to `url_for("profile")`.

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterized queries only — never format SQL strings.
- Passwords hashed with `werkzeug.security.generate_password_hash`.
- Use CSS variables — never hardcode hex values (only relevant if templates/styles are touched).
- All templates extend `base.html`.
- Check for an existing email before inserting; do not rely solely on the `UNIQUE` constraint to surface the error to the user.
- Keep `/register` a single route handling both `GET` and `POST` (no separate submit endpoint).

## Definition of done

- [ ] Visiting `/register` and submitting valid name/email/password creates a row in `users` with a hashed password (verify `password_hash` is not plaintext).
- [ ] After successful registration, the browser is redirected to `/login` and a session cookie is set.
- [ ] Submitting with a missing field re-renders `register.html` with an error message and does not create a user.
- [ ] Submitting a password shorter than 8 characters re-renders `register.html` with an error message and does not create a user.
- [ ] Submitting an email that already exists in `users` re-renders `register.html` with an error message and does not create a duplicate row.
- [ ] Re-running the app (`init_db()` / `seed_db()` on startup) does not affect or duplicate newly registered users.
- [ ] App starts without errors and existing routes (`/`, `/login`) are unaffected.
