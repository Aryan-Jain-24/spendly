"""
Tests for Step 7 -- Add Expense.

Spec: .claude/specs/07-add-expense.md

Covers:
- GET /expenses/add auth guard (unauthenticated -> redirect to /login).
- GET /expenses/add authenticated -> 200, form with amount/category/date/
  description fields, category <select> lists all 7 database.db.CATEGORIES
  values.
- POST /expenses/add auth guard (unauthenticated -> redirect to /login, no
  row inserted).
- POST /expenses/add authenticated + valid data -> redirect to /profile, new
  expense visible in the profile transaction list and reflected in
  total_spent / transaction_count.
- POST /expenses/add authenticated + invalid data (missing/zero/negative/
  non-numeric amount, invalid category, invalid/missing date) -> 400, form
  re-rendered with an error message, no row inserted, sticky values
  preserved.
- Successful submission with empty/omitted description.
"""

import re

import pytest

import database.db as db_module
from database.db import CATEGORIES

from conftest import extract_input_value, extract_stat_value


# --------------------------------------------------------------------- #
# Local helpers (this file only -- not shared via conftest.py)
# --------------------------------------------------------------------- #

def _expense_rows_for_user(user_id):
    """Direct read of the expenses table for a given user, bypassing the
    route/query layer, so DB side effects can be verified independently."""
    db = db_module.get_db()
    rows = db.execute(
        "SELECT amount, category, date, description FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    db.close()
    return rows


def _all_expense_rows():
    db = db_module.get_db()
    rows = db.execute("SELECT * FROM expenses").fetchall()
    db.close()
    return rows


def _extract_select_options(html, field_name):
    """Return the list of `value="..."` options inside the <select
    name="{field_name}"> element."""
    match = re.search(
        rf'<select[^>]*name="{field_name}"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    if match is None:
        return []
    return re.findall(r'<option\s+value="([^"]*)"', match.group(1))


def _selected_select_option(html, field_name):
    """Return the value of whichever <option> inside <select name="...">
    carries the `selected` attribute, or None if none do."""
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
        "amount": "42.50",
        "category": "Food",
        "date": "2026-07-10",
        "description": "Groceries",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------- #
# Auth guard -- GET
# --------------------------------------------------------------------- #

class TestAddExpenseGetAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"


# --------------------------------------------------------------------- #
# GET form rendering -- authenticated
# --------------------------------------------------------------------- #

class TestAddExpenseGetFormDisplay:
    def test_get_authenticated_returns_200(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200, "Authenticated GET should render the form"

    def test_get_authenticated_form_has_amount_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'name="amount"' in html, "Form must include an amount field"

    def test_get_authenticated_form_has_category_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'name="category"' in html, "Form must include a category field"

    def test_get_authenticated_form_has_date_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'name="date"' in html, "Form must include a date field"

    def test_get_authenticated_form_has_description_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'name="description"' in html, "Form must include a description field"

    def test_get_authenticated_category_select_lists_all_categories(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        options = _extract_select_options(html, "category")

        assert len(CATEGORIES) == 7, (
            "Sanity check: spec expects exactly 7 categories in database.db.CATEGORIES"
        )
        for category in CATEGORIES:
            assert category in options, f"Category select must include '{category}'"

    def test_get_authenticated_no_error_shown(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert "auth-error" not in html, "A fresh GET should not show a validation error"


# --------------------------------------------------------------------- #
# Auth guard -- POST
# --------------------------------------------------------------------- #

class TestAddExpensePostAuthGuard:
    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post("/expenses/add", data=_valid_payload())
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"

    def test_post_unauthenticated_does_not_insert_row(self, client):
        client.post("/expenses/add", data=_valid_payload())
        assert _all_expense_rows() == [], (
            "No expense row should be created by an unauthenticated POST"
        )


# --------------------------------------------------------------------- #
# Successful submission
# --------------------------------------------------------------------- #

class TestAddExpenseValidSubmission:
    def test_post_valid_data_redirects_to_profile(self, auth_client):
        response = auth_client.post("/expenses/add", data=_valid_payload())
        assert response.status_code == 302, "Valid submission should redirect"
        assert response.headers["Location"].endswith("/profile"), (
            "Valid submission should redirect to /profile"
        )

    def test_post_valid_data_inserts_row_in_db(self, auth_client):
        auth_client.post("/expenses/add", data=_valid_payload())

        rows = _expense_rows_for_user(auth_client.user_id)
        assert len(rows) == 1, "Exactly one expense row should be created"
        row = rows[0]
        assert row["amount"] == 42.50
        assert row["category"] == "Food"
        assert row["date"] == "2026-07-10"
        assert row["description"] == "Groceries"

    def test_post_valid_data_appears_in_profile_transaction_list(self, auth_client):
        auth_client.post("/expenses/add", data=_valid_payload())

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Groceries" in html, "New expense description should appear in transactions"
        assert "Food" in html, "New expense category should appear in transactions"
        assert "2026-07-10" in html, "New expense date should appear in transactions"
        assert "₹42.50" in html, "New expense amount should appear with the ₹ symbol"

    def test_post_valid_data_reflected_in_summary_stats(self, auth_client):
        auth_client.post("/expenses/add", data=_valid_payload(amount="10.00"))
        auth_client.post(
            "/expenses/add",
            data=_valid_payload(amount="15.00", category="Transport", description="Bus"),
        )

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹25.00" in html, "Total spent should sum both newly added expenses"
        assert extract_stat_value(html, "Transactions") == "2", (
            "Transaction count stat should reflect both newly added expenses"
        )

    def test_post_with_omitted_description_succeeds(self, auth_client):
        payload = _valid_payload()
        del payload["description"]

        response = auth_client.post("/expenses/add", data=payload)
        assert response.status_code == 302, "Omitted description should still succeed"
        assert response.headers["Location"].endswith("/profile")

        rows = _expense_rows_for_user(auth_client.user_id)
        assert len(rows) == 1, "Row should be inserted even with description omitted"
        assert rows[0]["description"] in (None, ""), (
            "Description should be stored as empty/None, not defaulted to other text"
        )

    def test_post_with_empty_description_succeeds(self, auth_client):
        response = auth_client.post("/expenses/add", data=_valid_payload(description=""))
        assert response.status_code == 302, "Empty description should still succeed"

        rows = _expense_rows_for_user(auth_client.user_id)
        assert len(rows) == 1
        assert rows[0]["description"] in (None, "")

    def test_post_with_empty_description_falls_back_to_category_on_profile(self, auth_client):
        auth_client.post("/expenses/add", data=_valid_payload(category="Bills", description=""))

        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Bills" in html, (
            "With no description, the profile page should fall back to showing the category"
        )


# --------------------------------------------------------------------- #
# Invalid amount
# --------------------------------------------------------------------- #

class TestAddExpenseInvalidAmount:
    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_returns_400(self, auth_client, bad_amount):
        response = auth_client.post("/expenses/add", data=_valid_payload(amount=bad_amount))
        assert response.status_code == 400, (
            f"Amount '{bad_amount}' should be rejected with 400"
        )

    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_shows_error_message(self, auth_client, bad_amount):
        html = auth_client.post(
            "/expenses/add", data=_valid_payload(amount=bad_amount)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Amount '{bad_amount}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-10", "abc"],
        ids=["missing", "zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_does_not_insert_row(self, auth_client, bad_amount):
        auth_client.post("/expenses/add", data=_valid_payload(amount=bad_amount))
        assert _expense_rows_for_user(auth_client.user_id) == [], (
            f"Amount '{bad_amount}' must not create an expense row"
        )

    @pytest.mark.parametrize(
        "bad_amount",
        ["0", "-10", "abc"],
        ids=["zero", "negative", "non_numeric"],
    )
    def test_invalid_amount_preserves_sticky_values(self, auth_client, bad_amount):
        html = auth_client.post(
            "/expenses/add",
            data=_valid_payload(amount=bad_amount, category="Transport", date="2026-07-11",
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
        assert _selected_select_option(html, "category") == "Transport", (
            "Category should stay selected with the submitted value on amount error"
        )


# --------------------------------------------------------------------- #
# Invalid category
# --------------------------------------------------------------------- #

class TestAddExpenseInvalidCategory:
    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],  # empty, unknown, wrong-case
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_returns_400(self, auth_client, bad_category):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(category=bad_category)
        )
        assert response.status_code == 400, (
            f"Category '{bad_category}' is not in CATEGORIES and should be rejected with 400"
        )

    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_shows_error_message(self, auth_client, bad_category):
        html = auth_client.post(
            "/expenses/add", data=_valid_payload(category=bad_category)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Category '{bad_category}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_category",
        ["", "Bogus", "food"],
        ids=["missing", "unknown", "wrong_case"],
    )
    def test_invalid_category_does_not_insert_row(self, auth_client, bad_category):
        auth_client.post("/expenses/add", data=_valid_payload(category=bad_category))
        assert _expense_rows_for_user(auth_client.user_id) == [], (
            f"Category '{bad_category}' must not create an expense row"
        )

    def test_invalid_category_preserves_other_sticky_values(self, auth_client):
        html = auth_client.post(
            "/expenses/add",
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


# --------------------------------------------------------------------- #
# Invalid / missing date
# --------------------------------------------------------------------- #

class TestAddExpenseInvalidDate:
    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_returns_400(self, auth_client, bad_date):
        response = auth_client.post("/expenses/add", data=_valid_payload(date=bad_date))
        assert response.status_code == 400, (
            f"Date '{bad_date}' should be rejected with 400"
        )

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_shows_error_message(self, auth_client, bad_date):
        html = auth_client.post(
            "/expenses/add", data=_valid_payload(date=bad_date)
        ).get_data(as_text=True)
        assert "auth-error" in html, (
            f"Date '{bad_date}' should re-render the form with a validation error"
        )

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "07/10/2026", "2026-13-40"],
        ids=["missing", "garbage", "wrong_format", "out_of_range"],
    )
    def test_invalid_date_does_not_insert_row(self, auth_client, bad_date):
        auth_client.post("/expenses/add", data=_valid_payload(date=bad_date))
        assert _expense_rows_for_user(auth_client.user_id) == [], (
            f"Date '{bad_date}' must not create an expense row"
        )

    def test_invalid_date_preserves_other_sticky_values(self, auth_client):
        html = auth_client.post(
            "/expenses/add",
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
