# Spec: Profile Page Design

## Overview

This step implements the `/profile` route, replacing the placeholder text (`"Profile page — coming in Step 4"`) with a real page. It gives a logged-in user a place to see their own account details — name, email, and member-since date — styled consistently with the existing auth pages. This is a read-only view; editing account details, expense summaries, and avatar/bio fields are out of scope and belong to later steps if introduced.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`) must be complete.
- Step 2 — Registration (`users.name`, `users.email`, `users.created_at` populated at signup) must be complete.
- Step 3 — Login and Logout (`session["user_id"]` set on login, cleared on logout) must be complete.

## Routes

- `GET /profile` — renders the current user's profile (name, email, member-since date) — logged-in only. If no `session["user_id"]`, redirect to `/login`.

## Database changes

No database changes. The existing `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) already has everything this page displays, as defined in `database/db.py`.

## Templates

**Create:**
- `templates/profile.html` — displays the user's name, email, and formatted member-since date inside a card, reusing the `auth-section` / `auth-container` / `auth-card` layout classes already defined in `style.css`.

**Modify:**
- `templates/base.html` — add a `Profile` link in `.nav-links` next to `Sign out`, shown only when `session.user_id` is set (`{% if session.user_id %}` block), pointing to `url_for('profile')`.

## Files to change

- `app.py`
  - Replace the placeholder `/profile` route body.
  - Guard the route: if `session.get("user_id")` is falsy, redirect to `url_for("login")`.
  - Look up the user with `SELECT id, name, email, created_at FROM users WHERE id = ?` using the parameterized query and the session's `user_id`.
  - Close the `get_db()` connection after the query.
  - Pass the user row to `render_template("profile.html", user=user)`.
- `templates/base.html`
  - Add the `Profile` nav link described above.

## Files to create

- `templates/profile.html`

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterised queries only.
- Passwords hashed with werkzeug (unaffected by this step — no password field is shown or edited).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Close the `get_db()` connection on every code path (found user and, defensively, the not-found case).
- Do not render `password_hash` anywhere in the template.
- Format `created_at` for display (e.g. `"Member since March 2026"`) rather than showing the raw SQLite timestamp string.
- Keep the page read-only — no edit form, no POST handling, in this step.

## Definition of done

- [ ] Visiting `/profile` while not logged in redirects to `/login`.
- [ ] Logging in with the seeded demo user (`demo@spendly.com` / `demo123`) and visiting `/profile` shows the name "Demo User", email "demo@spendly.com", and a member-since date.
- [ ] The `Profile` nav link appears in the navbar only when logged in, and navigates to `/profile`.
- [ ] The profile page visually matches the site's design system (fonts, colors, card style consistent with `/login` and `/register`).
- [ ] No raw password hash or other sensitive data appears in the rendered HTML.
- [ ] App starts without errors and existing routes (`/`, `/register`, `/login`, `/logout`) are unaffected.
