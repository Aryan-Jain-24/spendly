"""
Tests for Step 9 -- Delete Expense.

Spec: .claude/specs/09-delete-expense.md

Covers:
- Unit tests for `database.queries.delete_expense` (ownership filtering,
  non-existent ids, DB side effects visible via `get_recent_transactions`).
- GET /expenses/<id>/delete -> 405 (no GET handler exists; deleting must
  only be reachable via POST).
- POST /expenses/<id>/delete auth guard (unauthenticated -> redirect to
  /login, no row deleted).
- POST /expenses/<id>/delete for a non-owning user, or a non-existent id
  -> 404, no row deleted.
- POST /expenses/<id>/delete authenticated + valid data -> redirect to
  /profile, expense no longer visible in the profile transaction list and
  reflected in total_spent / transaction_count / category breakdown.
- A delete only removes the targeted expense, leaving other expenses intact.
"""

import pytest

import database.db as db_module
from database.queries import delete_expense, get_recent_transactions

from conftest import extract_stat_value


# --------------------------------------------------------------------- #
# Local helpers (this file only -- not shared via conftest.py)
# --------------------------------------------------------------------- #

def _create_user(name="Owner", email="owner@example.com"):
    """Insert a user directly via parameterized SQL -- used for the pure
    query-layer unit tests, where we don't need a real password / session,
    only a valid `users.id` to satisfy the `expenses.user_id` foreign key."""
    db = db_module.get_db()
    cursor = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, "not-a-real-hash"),
    )
    db.commit()
    user_id = cursor.lastrowid
    db.close()
    return user_id


def _insert_expense_row(user_id, amount=20.00, category="Food", date_str="2026-07-01",
                         description="Original desc"):
    db = db_module.get_db()
    cursor = db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date_str, description),
    )
    db.commit()
    expense_id = cursor.lastrowid
    db.close()
    return expense_id


def _expense_row(expense_id):
    """Direct read of a single expense row by id, bypassing the route/query
    layer, so DB side effects (or the lack of them) can be verified
    independently."""
    db = db_module.get_db()
    row = db.execute(
        "SELECT id, user_id, amount, category, date, description FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()
    db.close()
    return row


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


# --------------------------------------------------------------------- #
# Fixtures local to this file
# --------------------------------------------------------------------- #

@pytest.fixture
def other_auth_client(app):
    """A second, independently-authenticated test client sharing the same
    DB as `auth_client`, used for ownership / IDOR checks."""
    client2 = app.test_client()
    email = "otheruser@example.com"
    password = "OtherPass123"
    _register(client2, "Other User", email, password)
    _login(client2, email, password)
    client2.user_id = _user_id_for_email(email)
    assert client2.user_id is not None, "Fixture setup failed: second test user was not created"
    return client2


@pytest.fixture
def make_expense(app):
    """Factory fixture: insert an expense row directly via parameterized
    SQL and return its id."""

    def _make(user_id, amount=20.00, category="Food", date_str="2026-07-01",
              description="Original desc"):
        return _insert_expense_row(user_id, amount, category, date_str, description)

    return _make


# ======================================================================= #
# Unit tests -- database.queries.delete_expense
# ======================================================================= #

class TestDeleteExpenseUnit:
    def test_deletes_row_for_owning_user(self, app):
        owner_id = _create_user(email="owner1@example.com")
        expense_id = _insert_expense_row(owner_id)

        delete_expense(expense_id, owner_id)

        assert _expense_row(expense_id) is None, "Owning user's delete should remove the row"
        assert get_recent_transactions(owner_id) == [], (
            "Deleted expense must not appear in recent transactions"
        )

    def test_does_not_delete_row_for_non_owning_user(self, app):
        owner_id = _create_user(email="owner2@example.com")
        other_id = _create_user(email="other2@example.com")
        expense_id = _insert_expense_row(owner_id)

        delete_expense(expense_id, other_id)

        assert _expense_row(expense_id) is not None, (
            "A non-owning user's delete must not remove someone else's expense"
        )

    def test_no_error_for_nonexistent_id(self, app):
        owner_id = _create_user(email="owner3@example.com")

        delete_expense(999_999, owner_id)  # must not raise


# ======================================================================= #
# GET must not be handled -- delete is POST-only
# ======================================================================= #

class TestDeleteExpenseMethodNotAllowed:
    def test_get_returns_405(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.get(f"/expenses/{expense_id}/delete")
        assert response.status_code == 405, (
            "Deleting must only be reachable via POST, never a plain GET"
        )


# ======================================================================= #
# Auth guard -- POST
# ======================================================================= #

class TestDeleteExpensePostAuthGuard:
    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post("/expenses/1/delete")
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"

    def test_post_unauthenticated_does_not_delete_row(self, app, client):
        owner_id = _create_user(email="unauth_owner@example.com")
        expense_id = _insert_expense_row(owner_id)

        client.post(f"/expenses/{expense_id}/delete")

        assert _expense_row(expense_id) is not None, (
            "Unauthenticated POST must not delete the expense row"
        )


# ======================================================================= #
# POST -- ownership / IDOR checks
# ======================================================================= #

class TestDeleteExpensePostOwnership:
    def test_post_not_owned_expense_returns_404(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(other_auth_client.user_id)
        response = auth_client.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 404, (
            "A user must not be able to delete another user's expense"
        )

    def test_post_not_owned_expense_does_not_delete_row(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(other_auth_client.user_id)

        auth_client.post(f"/expenses/{expense_id}/delete")

        assert _expense_row(expense_id) is not None, (
            "Non-owner's POST must not delete the row"
        )

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post("/expenses/999999/delete")
        assert response.status_code == 404, "Deleting a non-existent expense id should return 404"


# ======================================================================= #
# Successful submission
# ======================================================================= #

class TestDeleteExpenseValidSubmission:
    def test_post_valid_redirects_to_profile(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 302, "Valid delete should redirect"
        assert response.headers["Location"].endswith("/profile"), (
            "Valid delete should redirect to /profile"
        )

    def test_post_valid_removes_row_from_db(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        auth_client.post(f"/expenses/{expense_id}/delete")

        assert _expense_row(expense_id) is None, "Row should be removed from the database"

    def test_post_valid_removes_from_profile_transaction_list(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, description="Soon to be gone")
        auth_client.post(f"/expenses/{expense_id}/delete")

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Soon to be gone" not in html, (
            "Deleted expense must no longer appear in recent transactions"
        )

    def test_post_valid_reflected_in_summary_stats(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, amount=20.00)
        auth_client.post(f"/expenses/{expense_id}/delete")

        html = auth_client.get("/profile").get_data(as_text=True)
        assert extract_stat_value(html, "Transactions") == "0", (
            "Deleting the only expense should drop the transaction count to 0"
        )
        assert "₹0.00" in html, "Total spent should reflect the deletion"

    def test_post_valid_only_deletes_targeted_expense(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, description="Delete me")
        keep_id = make_expense(auth_client.user_id, description="Keep me")

        auth_client.post(f"/expenses/{expense_id}/delete")

        assert _expense_row(expense_id) is None, "Targeted expense should be removed"
        assert _expense_row(keep_id) is not None, "Other expenses must be left untouched"

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Keep me" in html, "Untouched expense should still appear in the transaction list"
        assert "Delete me" not in html, "Deleted expense should no longer appear"
