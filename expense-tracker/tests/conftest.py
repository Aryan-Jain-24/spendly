"""
Shared pytest fixtures for the Spendly test suite.

Spendly's DB layer (database/db.py) does not accept a Flask config value for
the database path -- `get_db()` always opens `sqlite3.connect(DB_PATH)` where
DB_PATH is a module-level constant. To keep tests fully isolated from the
real dev database (expense_tracker.db) and from each other, we monkeypatch
`database.db.DB_PATH` to a fresh temp file for every test and re-create the
schema with `init_db()`. Because `get_db()` re-reads the module global on
every call (rather than capturing it at import time), patching it before a
request is issued is sufficient -- no need to touch `app.py` or `queries.py`.

IMPORTANT: `app.py` calls `init_db()` / `seed_db()` once at *import* time
(`with app.app_context(): init_db(); seed_db()`). To make sure that one-time
call never touches the real `expense_tracker.db`, we patch `DB_PATH` to a
throwaway temp file *before* `app` is imported anywhere in this session.
"""

import os
import re
import sys
import tempfile

import pytest

# --------------------------------------------------------------------- #
# Make the Flask app root (expense-tracker/) importable as `app`,
# `database.db`, `database.queries`, etc. Tests live in
# expense-tracker/tests/, so the app root is one directory up.
# --------------------------------------------------------------------- #
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import database.db as db_module  # noqa: E402

# Redirect DB_PATH *before* `app` is imported, since importing app.py has the
# side effect of calling init_db()/seed_db() against whatever DB_PATH is
# currently set.
_import_fd, _IMPORT_TIME_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_import_fd)
db_module.DB_PATH = _IMPORT_TIME_DB_PATH

from app import app as flask_app  # noqa: E402
from database.db import init_db  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    """Flask app configured for testing, backed by a fresh isolated SQLite
    file for this test only (no seed data -- each test builds its own
    known fixture data)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    flask_app.config.update(TESTING=True)
    init_db()

    yield flask_app

    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def _register(client, name, email, password):
    return client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=True,
    )


def _login(client, email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def _user_id_for_email(email):
    db = db_module.get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    return row["id"] if row else None


@pytest.fixture
def auth_client(client):
    """A test client that is registered, logged in, and has its user_id
    stashed as `client.user_id` for convenience."""
    email = "filtertester@example.com"
    password = "TestPass123"
    _register(client, "Filter Tester", email, password)
    _login(client, email, password)
    client.user_id = _user_id_for_email(email)
    assert client.user_id is not None, "Fixture setup failed: test user was not created"
    return client


@pytest.fixture
def add_expense(app):
    """Factory fixture: insert an expense row directly via parameterized SQL
    (there is no expense-creation route yet -- Step 7 is still a stub)."""

    def _add(user_id, amount, category, date_str, description=""):
        db = db_module.get_db()
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, description),
        )
        db.commit()
        db.close()

    return _add


def extract_percentages(html):
    """Pull every category-breakdown percentage value out of rendered HTML."""
    return [int(m) for m in re.findall(r'breakdown-pct">(\d+)%', html)]


def extract_stat_value(html, label):
    """Return the text of the <span class="stat-value"> that immediately
    follows a <span class="stat-label">{label}</span> block (e.g. "Total
    spent", "Transactions", "Top category"). Returns None if not found."""
    match = re.search(
        rf'stat-label">{re.escape(label)}</span>\s*<span class="stat-value">([^<]*)</span>',
        html,
    )
    return match.group(1).strip() if match else None


def extract_input_value(html, field_name):
    """Return the `value` attribute of the <input name="{field_name}" ...>
    element, regardless of attribute ordering in the markup. Returns None if
    no such input is found."""
    match = re.search(rf'<input[^>]*name="{field_name}"[^>]*>', html)
    if match is None:
        return None
    value_match = re.search(r'value="([^"]*)"', match.group(0))
    return value_match.group(1) if value_match else None
