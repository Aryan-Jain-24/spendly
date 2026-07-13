# Spec: Login and Logout

## Overview

This step implements session-based authentication for existing users: signing in via the already-built `/login` form, and signing out via `/logout`. Registration (Step 2) already establishes the pattern of hashing passwords and storing `user_id` in the Flask session; this step completes the auth loop so a user can leave and come back to their account. It does not add access control to any protected page — `/profile` and the expense routes remain placeholders until later steps — it only makes `session["user_id"]` settable and clearable via real routes.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`) must be complete.
- Step 2 — Registration (password hashing pattern, `app.secret_key`, session usage) must be complete.

## Routes

- `GET /login` — renders the sign-in form — public (already exists, unchanged)
- `POST /login` — validates email/password against `users`, starts a session, redirects to `/` — public
- `GET /logout` — clears the session, redirects to `/login` — logged-in (safe to hit while logged out; just redirects)

## Database changes

No database changes. The existing `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) already supports login as defined in `database/db.py`.

## Templates

**Create:** None — `login.html` already exists and posts to `/login` with `email` and `password` fields.

**Modify:**
- `templates/login.html` — no structural changes required; it already renders `{{ error }}` above the form. Only re-verify field names (`email`, `password`) match what `app.py` will read from `request.form`.

## Files to change

- `app.py`
  - Change the `/login` route to accept `methods=["GET", "POST"]`.
  - On `POST`: read and trim `email`, `password` from `request.form`; lowercase the email before lookup (matches the normalization used in `/register`).
  - Validate: both fields required.
  - On validation failure, missing user, or password mismatch: re-render `login.html` with a single generic `error` (e.g. "Invalid email or password.") and a 401 status — never reveal whether the email exists.
  - On success: verify the password with `werkzeug.security.check_password_hash` against the stored `password_hash`, set `session["user_id"]` to the user's id, and redirect to `url_for("landing")`.
  - Replace the placeholder `/logout` route body: call `session.pop("user_id", None)` and redirect to `url_for("login")`.
  - Add the `check_password_hash` import from `werkzeug.security`.

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterized queries only — never format SQL strings.
- Passwords verified with `werkzeug.security.check_password_hash` (never compare hashes or plaintext directly).
- Use CSS variables — never hardcode hex values (only relevant if templates/styles are touched).
- All templates extend `base.html`.
- Look up the user by email first, then check the password hash — don't leak which part failed in the error message shown to the user.
- Keep `/login` a single route handling both `GET` and `POST` (no separate submit endpoint), matching the `/register` pattern.
- Close the `get_db()` connection on every code path (success, invalid credentials, and missing-fields).

## Definition of done

- [ ] Visiting `/login` and submitting the seeded demo user's credentials (`demo@spendly.com` / `demo123`) sets a session cookie and redirects to `/`.
- [ ] Submitting a correct email with the wrong password re-renders `login.html` with a generic error message and does not set a session.
- [ ] Submitting an email that doesn't exist re-renders `login.html` with the same generic error message (no difference in wording from a wrong password).
- [ ] Submitting with a missing email or password re-renders `login.html` with an error and does not query the database for a matching user beyond what's needed.
- [ ] Visiting `/logout` after logging in clears the session (subsequent requests no longer carry `user_id`) and redirects to `/login`.
- [ ] Visiting `/logout` while not logged in does not error — it redirects to `/login` regardless of prior session state.
- [ ] App starts without errors and existing routes (`/`, `/register`) are unaffected.
