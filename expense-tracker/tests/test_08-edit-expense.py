"""
Tests for Step 8 -- Edit Expense.

Spec: .claude/specs/08-edit-expense.md

Covers:
- Unit tests for `database.queries.get_expense_by_id` and `update_expense`
  (ownership filtering, non-existent ids, DB side effects visible via
  `get_recent_transactions`).
- GET /expenses/<id>/edit auth guard (unauthenticated -> redirect to
  /login).
- GET /expenses/<id>/edit for the owning user -> 200, form pre-filled with
  the expense's current amount/category/date/description.
- GET /expenses/<id>/edit for a non-owning user, or a non-existent id
  -> 404 (no leakage of the other user's data).
- POST /expenses/<id>/edit auth guard (unauthenticated -> redirect to
  /login, no row changed).
- POST /expenses/<id>/edit for a non-owning user, or a non-existent id
  -> 404, no row changed.
- POST /expenses/<id>/edit authenticated + valid data -> redirect to
  /profile, updated expense visible in the profile transaction list and
  reflected in total_spent / transaction_count / category breakdown.
- POST /expenses/<id>/edit authenticated + invalid data (missing/zero/
  negative/non-numeric amount, invalid category, invalid/missing date)
  -> 400, form re-rendered with an error message, row unchanged, sticky
  values preserved.
- Successful submission with empty description falls back to category on
  the profile page (existing profile page behavior).
"""

import re

import pytest

import database.db as db_module
from database.db import CATEGORIES
from database.queries import get_expense_by_id, update_expense, get_recent_transactions, get_category_breakdown

from conftest import extract_input_value, extract_stat_value


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


def _extract_select_options(html, field_name):
    match = re.search(
        rf'<select[^>]*name="{field_name}"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    if match is None:
        return []
    return re.findall(r'<option\s+value="([^"]*)"', match.group(1))


def _selected_select_option(html, field_name):
    match = re.search(
        rf'<select[^>]*name="{field_name}"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    if match is None:
        return None
    for opt in re.finditer(r'<option\s+value="([^"]*)"([^>]*)>', match.group(1)):
        value, attrs = opt.group(1), opt.group(2)
        if "selected" in attrs:
            return value
    return None


def _valid_payload(**overrides):
    payload = {
        "amount": "75.25",
        "category": "Transport",
        "date": "2026-07-15",
        "description": "Updated desc",
    }
    payload.update(overrides)
    return payload


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
# Unit tests -- database.queries.get_expense_by_id / update_expense
# ======================================================================= #

class TestGetExpenseByIdUnit:
    def test_returns_row_for_owning_user(self, app):
        owner_id = _create_user(email="owner1@example.com")
        expense_id = _insert_expense_row(
            owner_id, amount=12.34, category="Food", date_str="2026-07-01", description="Lunch"
        )

        result = get_expense_by_id(expense_id, owner_id)

        assert result is not None, "Owning user should be able to fetch their own expense"
        assert result["id"] == expense_id
        assert result["amount"] == 12.34
        assert result["category"] == "Food"
        assert result["date"] == "2026-07-01"
        assert result["description"] == "Lunch"

    def test_returns_none_for_non_owning_user(self, app):
        owner_id = _create_user(email="owner2@example.com")
        other_id = _create_user(email="other2@example.com")
        expense_id = _insert_expense_row(owner_id)

        result = get_expense_by_id(expense_id, other_id)

        assert result is None, "A non-owning user must not be able to fetch someone else's expense"

    def test_returns_none_for_nonexistent_id(self, app):
        owner_id = _create_user(email="owner3@example.com")

        result = get_expense_by_id(999_999, owner_id)

        assert result is None, "A non-existent expense id should return None"


class TestUpdateExpenseUnit:
    def test_updates_row_for_owning_user_and_is_visible_via_recent_transactions(self, app):
        owner_id = _create_user(email="owner4@example.com")
        expense_id = _insert_expense_row(
            owner_id, amount=10.0, category="Food", date_str="2026-07-01", description="Old"
        )

        update_expense(expense_id, owner_id, 99.99, "Transport", "2026-07-15", "New")

        row = _expense_row(expense_id)
        assert row["amount"] == 99.99, "Amount should be updated"
        assert row["category"] == "Transport", "Category should be updated"
        assert row["date"] == "2026-07-15", "Date should be updated"
        assert row["description"] == "New", "Description should be updated"

        txns = get_recent_transactions(owner_id)
        matching = [t for t in txns if t["id"] == expense_id]
        assert len(matching) == 1, "Updated expense should still appear exactly once in recent transactions"
        assert matching[0]["amount"] == 99.99
        assert matching[0]["category"] == "Transport"
        assert matching[0]["date"] == "2026-07-15"
        assert matching[0]["description"] == "New"

    def test_does_not_update_row_for_non_owning_user(self, app):
        owner_id = _create_user(email="owner5@example.com")
        other_id = _create_user(email="other5@example.com")
        expense_id = _insert_expense_row(
            owner_id, amount=10.0, category="Food", date_str="2026-07-01", description="Old"
        )

        update_expense(expense_id, other_id, 999.0, "Bills", "2026-01-01", "Hacked")

        row = _expense_row(expense_id)
        assert row["amount"] == 10.0, "Non-owning user's update must not change the amount"
        assert row["category"] == "Food", "Non-owning user's update must not change the category"
        assert row["date"] == "2026-07-01", "Non-owning user's update must not change the date"
        assert row["description"] == "Old", "Non-owning user's update must not change the description"


# ======================================================================= #
# Auth guard -- GET
# ======================================================================= #

class TestEditExpenseGetAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/1/edit")
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"


# ======================================================================= #
# GET form rendering -- authenticated, owns the expense
# ======================================================================= #

class TestEditExpenseGetFormDisplay:
    def test_get_owned_expense_returns_200(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 200, "Authenticated GET for an owned expense should render the form"

    def test_get_owned_expense_prefills_amount(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, amount=55.5)
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        value = extract_input_value(html, "amount")
        assert value is not None, "Form must include an amount field"
        assert float(value) == 55.5, "Amount field should be pre-filled with the expense's current amount"

    def test_get_owned_expense_prefills_category(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, category="Health")
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        assert _selected_select_option(html, "category") == "Health", (
            "Category select should have the expense's current category pre-selected"
        )

    def test_get_owned_expense_prefills_date(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, date_str="2026-06-20")
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        assert extract_input_value(html, "date") == "2026-06-20", (
            "Date field should be pre-filled with the expense's current date"
        )

    def test_get_owned_expense_prefills_description(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, description="Bought textbooks")
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        assert extract_input_value(html, "description") == "Bought textbooks", (
            "Description field should be pre-filled with the expense's current description"
        )

    def test_get_owned_expense_category_select_lists_all_categories(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        options = _extract_select_options(html, "category")
        for category in CATEGORIES:
            assert category in options, f"Category select must include '{category}'"

    def test_get_owned_expense_no_error_shown(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        assert "auth-error" not in html, "A fresh GET should not show a validation error"


# ======================================================================= #
# GET -- ownership / IDOR checks
# ======================================================================= #

class TestEditExpenseGetOwnership:
    def test_get_not_owned_expense_returns_404(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(other_auth_client.user_id, description="Not yours")
        response = auth_client.get(f"/expenses/{expense_id}/edit")
        assert response.status_code == 404, (
            "A user must not be able to view another user's expense edit form"
        )

    def test_get_not_owned_expense_does_not_leak_data(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(
            other_auth_client.user_id, description="SecretOtherUserDescription"
        )
        html = auth_client.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
        assert "SecretOtherUserDescription" not in html, (
            "The 404 response must not leak another user's expense data"
        )

    def test_get_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.get("/expenses/999999/edit")
        assert response.status_code == 404, "Editing a non-existent expense id should return 404"


# ======================================================================= #
# Auth guard -- POST
# ======================================================================= #

class TestEditExpensePostAuthGuard:
    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post("/expenses/1/edit", data=_valid_payload())
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"

    def test_post_unauthenticated_does_not_change_row(self, app, client):
        owner_id = _create_user(email="unauth_owner@example.com")
        expense_id = _insert_expense_row(owner_id)

        client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())

        row = _expense_row(expense_id)
        assert row["amount"] == 20.00, "Unauthenticated POST must not change the expense row"
        assert row["category"] == "Food"


# ======================================================================= #
# POST -- ownership / IDOR checks
# ======================================================================= #

class TestEditExpensePostOwnership:
    def test_post_not_owned_expense_returns_404(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(other_auth_client.user_id)
        response = auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())
        assert response.status_code == 404, (
            "A user must not be able to edit another user's expense"
        )

    def test_post_not_owned_expense_does_not_change_row(self, auth_client, other_auth_client, make_expense):
        expense_id = make_expense(
            other_auth_client.user_id, amount=20.00, category="Food",
            date_str="2026-07-01", description="Original desc",
        )

        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())

        row = _expense_row(expense_id)
        assert row["amount"] == 20.00, "Non-owner's POST must not change the amount"
        assert row["category"] == "Food", "Non-owner's POST must not change the category"
        assert row["date"] == "2026-07-01", "Non-owner's POST must not change the date"
        assert row["description"] == "Original desc", "Non-owner's POST must not change the description"

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post("/expenses/999999/edit", data=_valid_payload())
        assert response.status_code == 404, "Editing a non-existent expense id should return 404"


# ======================================================================= #
# Successful submission
# ======================================================================= #

class TestEditExpenseValidSubmission:
    def test_post_valid_data_redirects_to_profile(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())
        assert response.status_code == 302, "Valid submission should redirect"
        assert response.headers["Location"].endswith("/profile"), (
            "Valid submission should redirect to /profile"
        )

    def test_post_valid_data_updates_row_in_db(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())

        row = _expense_row(expense_id)
        assert row["amount"] == 75.25
        assert row["category"] == "Transport"
        assert row["date"] == "2026-07-15"
        assert row["description"] == "Updated desc"

    def test_post_valid_data_appears_in_profile_transaction_list(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload())

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Updated desc" in html, "Updated description should appear in transactions"
        assert "Transport" in html, "Updated category should appear in transactions"
        assert "2026-07-15" in html, "Updated date should appear in transactions"
        assert "₹75.25" in html, "Updated amount should appear with the ₹ symbol"
        assert "Original desc" not in html, "The stale (pre-edit) description should no longer appear"

    def test_post_valid_data_reflected_in_summary_stats(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, amount=20.00)
        auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(amount="75.25")
        )

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹75.25" in html, "Total spent should reflect the edited amount, not the original"
        assert extract_stat_value(html, "Transactions") == "1", (
            "Editing must not change the total transaction count"
        )

    def test_post_valid_data_reflected_in_category_breakdown(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id, amount=20.00, category="Food")
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data=_valid_payload(amount="75.25", category="Transport"),
        )

        breakdown = get_category_breakdown(auth_client.user_id)
        assert len(breakdown) == 1, "Only one expense exists, so only one category should appear"
        assert breakdown[0]["name"] == "Transport", "Breakdown should reflect the new category"
        assert breakdown[0]["amount"] == 75.25, "Breakdown should reflect the new amount"

    def test_post_with_empty_description_succeeds(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(description="")
        )
        assert response.status_code == 302, "Empty description should still succeed"
        assert response.headers["Location"].endswith("/profile")

        row = _expense_row(expense_id)
        assert row["description"] in (None, ""), (
            "Description should be stored as empty/None, not defaulted to other text"
        )

    def test_post_with_empty_description_falls_back_to_category_on_profile(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data=_valid_payload(category="Bills", description=""),
        )

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Bills" in html, (
            "With no description, the profile page should fall back to showing the category"
        )


# ======================================================================= #
# Invalid amount
# ======================================================================= #

class TestEditExpenseInvalidAmount:
    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_returns_400(self, auth_client, make_expense, bad_amount):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(amount=bad_amount)
        )
        assert response.status_code == 400, f"Amount '{bad_amount}' should be rejected with 400"

    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_shows_error_message(self, auth_client, make_expense, bad_amount):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(amount=bad_amount)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Amount '{bad_amount}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_does_not_change_row(self, auth_client, make_expense, bad_amount):
        expense_id = make_expense(auth_client.user_id, amount=20.00, category="Food",
                                   date_str="2026-07-01", description="Original desc")
        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload(amount=bad_amount))

        row = _expense_row(expense_id)
        assert row["amount"] == 20.00, f"Amount '{bad_amount}' must not change the expense row"
        assert row["category"] == "Food"
        assert row["date"] == "2026-07-01"
        assert row["description"] == "Original desc"

    @pytest.mark.parametrize(
        "bad_amount",
        ["0", "-10", "abc"],
        ids=["zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_preserves_sticky_values(self, auth_client, make_expense, bad_amount):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data=_valid_payload(amount=bad_amount, category="Health", date="2026-07-11",
                                 description="StickyCheck"),
        ).get_data(as_text=True)

        assert extract_input_value(html, "amount") == bad_amount, (
            "The submitted (invalid) amount should be redisplayed in the form for correction"
        )
        assert extract_input_value(html, "date") == "2026-07-11", (
            "Date should be repopulated with the submitted value on amount error"
        )
        assert extract_input_value(html, "description") == "StickyCheck", (
            "Description should be repopulated with the submitted value on amount error"
        )
        assert _selected_select_option(html, "category") == "Health", (
            "Category should stay selected with the submitted value on amount error"
        )


# ======================================================================= #
# Invalid category
# ======================================================================= #

class TestEditExpenseInvalidCategory:
    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_returns_400(self, auth_client, make_expense, bad_category):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(category=bad_category)
        )
        assert response.status_code == 400, (
            f"Category '{bad_category}' is not in CATEGORIES and should be rejected with 400"
        )

    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_shows_error_message(self, auth_client, make_expense, bad_category):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(category=bad_category)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Category '{bad_category}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_does_not_change_row(self, auth_client, make_expense, bad_category):
        expense_id = make_expense(auth_client.user_id, amount=20.00, category="Food",
                                   date_str="2026-07-01", description="Original desc")
        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload(category=bad_category))

        row = _expense_row(expense_id)
        assert row["category"] == "Food", f"Category '{bad_category}' must not change the expense row"
        assert row["amount"] == 20.00
        assert row["date"] == "2026-07-01"
        assert row["description"] == "Original desc"

    def test_invalid_category_preserves_other_sticky_values(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data=_valid_payload(category="Bogus", amount="17.00", date="2026-07-12",
                                 description="StickyCategoryCheck"),
        ).get_data(as_text=True)

        assert extract_input_value(html, "amount") == "17.00", (
            "Amount should be repopulated with the submitted value on category error"
        )
        assert extract_input_value(html, "date") == "2026-07-12", (
            "Date should be repopulated with the submitted value on category error"
        )
        assert extract_input_value(html, "description") == "StickyCategoryCheck", (
            "Description should be repopulated with the submitted value on category error"
        )


# ======================================================================= #
# Invalid / missing date
# ======================================================================= #

class TestEditExpenseInvalidDate:
    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_returns_400(self, auth_client, make_expense, bad_date):
        expense_id = make_expense(auth_client.user_id)
        response = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(date=bad_date)
        )
        assert response.status_code == 400, f"Date '{bad_date}' should be rejected with 400"

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_shows_error_message(self, auth_client, make_expense, bad_date):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit", data=_valid_payload(date=bad_date)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Date '{bad_date}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_does_not_change_row(self, auth_client, make_expense, bad_date):
        expense_id = make_expense(auth_client.user_id, amount=20.00, category="Food",
                                   date_str="2026-07-01", description="Original desc")
        auth_client.post(f"/expenses/{expense_id}/edit", data=_valid_payload(date=bad_date))

        row = _expense_row(expense_id)
        assert row["date"] == "2026-07-01", f"Date '{bad_date}' must not change the expense row"
        assert row["amount"] == 20.00
        assert row["category"] == "Food"
        assert row["description"] == "Original desc"

    def test_invalid_date_preserves_other_sticky_values(self, auth_client, make_expense):
        expense_id = make_expense(auth_client.user_id)
        html = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data=_valid_payload(date="not-a-date", amount="23.00", category="Health",
                                 description="StickyDateCheck"),
        ).get_data(as_text=True)

        assert extract_input_value(html, "amount") == "23.00", (
            "Amount should be repopulated with the submitted value on date error"
        )
        assert extract_input_value(html, "description") == "StickyDateCheck", (
            "Description should be repopulated with the submitted value on date error"
        )
        assert _selected_select_option(html, "category") == "Health", (
            "Category should stay selected with the submitted value on date error"
        )
        assert extract_input_value(html, "date") == "not-a-date", (
            "The submitted (invalid) date should be redisplayed in the form for correction"
        )
