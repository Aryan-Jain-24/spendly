"""
Tests for Step 6 -- Date filter for the profile page.

Spec: .claude/specs/06-date-filter-profile-page.md

Covers:
- GET /profile with no query params behaves exactly as before (all-time,
  transactions capped at 10).
- GET /profile?start=...&end=... narrows summary stats, the transaction
  list, and the category breakdown to the inclusive date range.
- Single-sided (open-ended) ranges.
- Zero-match ranges show a distinct "no expenses in range" empty state.
- Invalid input (bad format, start after end) never 500s -- falls back to
  all-time data and surfaces a `filter_error` message.
- Sticky repopulation of the start/end inputs, both on success and on
  validation failure.
- The "Clear" link returns to a plain /profile with no query params.
- Auth guard applies regardless of query params.
- Category breakdown percentages sum to 100 for a filtered subset.
"""

from flask import url_for

from conftest import extract_percentages, extract_input_value, extract_stat_value


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestProfileAuthGuard:
    def test_profile_no_query_params_unauthenticated_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to /login"

    def test_profile_with_query_params_unauthenticated_redirects_to_login(self, client):
        response = client.get("/profile?start=2026-07-01&end=2026-07-15")
        assert response.status_code == 302, (
            "Unauthenticated /profile with a date filter should still redirect, "
            "not leak filtered data"
        )
        assert "/login" in response.headers["Location"], "Should redirect to /login"

    def test_profile_with_invalid_query_params_unauthenticated_redirects_to_login(self, client):
        response = client.get("/profile?start=not-a-date&end=also-not-a-date")
        assert response.status_code == 302, "Auth guard must run before date validation"
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# Baseline (no query params) behaviour is unchanged from before Step 6
# --------------------------------------------------------------------- #

class TestProfileBaselineUnfiltered:
    def test_no_query_params_shows_all_time_totals(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 10.00, "Food", "2026-01-01", "Groceries")
        add_expense(auth_client.user_id, 20.00, "Transport", "2026-02-01", "Bus pass")
        add_expense(auth_client.user_id, 30.00, "Bills", "2026-03-01", "Electricity")

        response = auth_client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "₹60.00" in html, "Total spent should sum every expense when unfiltered"
        assert "Groceries" in html and "Bus pass" in html and "Electricity" in html
        assert "auth-error" not in html, "No filter was submitted, so no validation error should show"

    def test_no_query_params_caps_transactions_at_ten(self, auth_client, add_expense):
        for day in range(1, 13):  # 12 expenses, only the 10 most recent should show
            add_expense(
                auth_client.user_id, 1.00, "Other",
                f"2026-01-{day:02d}", f"Item-{day:02d}",
            )

        response = auth_client.get("/profile")
        html = response.get_data(as_text=True)

        shown = sum(1 for day in range(1, 13) if f"Item-{day:02d}" in html)
        assert shown == 10, f"Expected exactly 10 transactions shown unfiltered, got {shown}"
        # The most recent (highest day numbers) should be the ones kept.
        assert "Item-12" in html and "Item-11" in html
        assert "Item-01" not in html and "Item-02" not in html

    def test_no_query_params_new_account_shows_generic_empty_state(self, auth_client):
        response = auth_client.get("/profile")
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "No transactions yet." in html, "Brand-new account should show the generic empty state"

    def test_no_query_params_start_end_inputs_are_empty(self, auth_client):
        response = auth_client.get("/profile")
        html = response.get_data(as_text=True)
        assert 'id="start"' in html and 'id="end"' in html, "Filter form inputs must be present"
        assert extract_input_value(html, "start") == "", (
            "start input should be empty when no filter is active"
        )
        assert extract_input_value(html, "end") == "", (
            "end input should be empty when no filter is active"
        )


# --------------------------------------------------------------------- #
# Valid range narrows all three panels
# --------------------------------------------------------------------- #

class TestProfileValidRangeFiltering:
    def _seed_mixed_expenses(self, auth_client, add_expense):
        uid = auth_client.user_id
        # In range: 2026-07-01 .. 2026-07-15
        add_expense(uid, 10.00, "Food", "2026-07-01", "InRange-Start")
        add_expense(uid, 20.00, "Transport", "2026-07-10", "InRange-Mid")
        add_expense(uid, 30.00, "Bills", "2026-07-15", "InRange-End")
        # Out of range
        add_expense(uid, 100.00, "Shopping", "2026-06-30", "BeforeRange")
        add_expense(uid, 200.00, "Health", "2026-07-16", "AfterRange")

    def test_valid_range_narrows_summary_stats(self, auth_client, add_expense):
        self._seed_mixed_expenses(auth_client, add_expense)

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "₹60.00" in html, "Summary total should only include the 3 in-range expenses (10+20+30)"
        assert extract_stat_value(html, "Transactions") == "3", (
            "Transaction count stat should only count the 3 in-range expenses"
        )

    def test_valid_range_narrows_transaction_list(self, auth_client, add_expense):
        self._seed_mixed_expenses(auth_client, add_expense)

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        for desc in ("InRange-Start", "InRange-Mid", "InRange-End"):
            assert desc in html, f"{desc} should appear in the filtered transaction list"
        for desc in ("BeforeRange", "AfterRange"):
            assert desc not in html, f"{desc} is outside the range and must not appear"

    def test_valid_range_narrows_category_breakdown(self, auth_client, add_expense):
        self._seed_mixed_expenses(auth_client, add_expense)

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        for cat in ("Food", "Transport", "Bills"):
            assert cat in html, f"{cat} is within range and should appear in the breakdown"
        for cat in ("Shopping", "Health"):
            assert cat not in html, f"{cat} is outside range and must not appear in the breakdown"

    def test_valid_range_returns_full_matching_set_not_capped_at_ten(self, auth_client, add_expense):
        uid = auth_client.user_id
        for day in range(1, 13):  # 12 expenses all inside the filtered range
            add_expense(uid, 1.00, "Other", f"2026-07-{day:02d}", f"RangeItem-{day:02d}")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-31")
        html = response.get_data(as_text=True)

        shown = sum(1 for day in range(1, 13) if f"RangeItem-{day:02d}" in html)
        assert shown == 12, (
            "A filtered range must show every matching transaction, not just the "
            f"default 10-row cap; found {shown}"
        )

    def test_inclusive_bounds_include_boundary_dates(self, auth_client, add_expense):
        uid = auth_client.user_id
        add_expense(uid, 5.00, "Food", "2026-07-01", "OnStartBoundary")
        add_expense(uid, 5.00, "Food", "2026-07-15", "OnEndBoundary")
        add_expense(uid, 5.00, "Food", "2026-06-30", "JustBeforeStart")
        add_expense(uid, 5.00, "Food", "2026-07-16", "JustAfterEnd")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        assert "OnStartBoundary" in html, "start bound must be inclusive"
        assert "OnEndBoundary" in html, "end bound must be inclusive"
        assert "JustBeforeStart" not in html
        assert "JustAfterEnd" not in html

    def test_start_and_end_equal_includes_that_single_day(self, auth_client, add_expense):
        uid = auth_client.user_id
        add_expense(uid, 5.00, "Food", "2026-07-10", "ExactDayMatch")
        add_expense(uid, 5.00, "Food", "2026-07-09", "DayBefore")
        add_expense(uid, 5.00, "Food", "2026-07-11", "DayAfter")

        response = auth_client.get("/profile?start=2026-07-10&end=2026-07-10")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "ExactDayMatch" in html
        assert "DayBefore" not in html
        assert "DayAfter" not in html


# --------------------------------------------------------------------- #
# Single-sided (open-ended) ranges
# --------------------------------------------------------------------- #

class TestProfileOpenEndedRanges:
    def _seed(self, auth_client, add_expense):
        uid = auth_client.user_id
        add_expense(uid, 10.00, "Food", "2026-05-01", "Early")
        add_expense(uid, 20.00, "Food", "2026-07-10", "Middle")
        add_expense(uid, 30.00, "Food", "2026-09-01", "Late")

    def test_start_only_includes_everything_on_or_after(self, auth_client, add_expense):
        self._seed(auth_client, add_expense)
        response = auth_client.get("/profile?start=2026-07-01")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Middle" in html and "Late" in html
        assert "Early" not in html
        assert "₹50.00" in html, "Total should be Middle(20)+Late(30)=50"

    def test_end_only_includes_everything_on_or_before(self, auth_client, add_expense):
        self._seed(auth_client, add_expense)
        response = auth_client.get("/profile?end=2026-07-10")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Early" in html and "Middle" in html
        assert "Late" not in html
        assert "₹30.00" in html, "Total should be Early(10)+Middle(20)=30"


# --------------------------------------------------------------------- #
# Zero-match range: distinct empty state, not an error, not the
# brand-new-account message
# --------------------------------------------------------------------- #

class TestProfileZeroMatchRange:
    def test_zero_match_range_shows_zero_totals(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 50.00, "Food", "2026-01-01", "OutsideRange")

        response = auth_client.get("/profile?start=2026-12-01&end=2026-12-31")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "₹0.00" in html, "A zero-match filtered range should show ₹0.00"
        assert extract_stat_value(html, "Transactions") == "0", (
            "Transaction count stat should be 0 for a zero-match range"
        )

    def test_zero_match_range_shows_distinct_empty_state_not_new_account_message(
        self, auth_client, add_expense
    ):
        add_expense(auth_client.user_id, 50.00, "Food", "2026-01-01", "OutsideRange")

        response = auth_client.get("/profile?start=2026-12-01&end=2026-12-31")
        html = response.get_data(as_text=True)

        assert "No transactions yet." not in html, (
            "A filtered zero-match range must not reuse the brand-new-account message"
        )
        assert "2026-12-01" in html and "2026-12-31" in html, (
            "The range-specific empty state should reference the active filter dates"
        )
        assert "auth-error" not in html, "A zero-match range is not a validation error"

    def test_zero_match_range_shows_no_expenses(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 50.00, "Food", "2026-01-01", "OutsideRange")

        response = auth_client.get("/profile?start=2026-12-01&end=2026-12-31")
        html = response.get_data(as_text=True)

        assert "OutsideRange" not in html


# --------------------------------------------------------------------- #
# Invalid input must never 500 -- falls back to all-time data with an
# error message
# --------------------------------------------------------------------- #

class TestProfileInvalidFilterInput:
    def _all_time_total_html(self, auth_client):
        return auth_client.get("/profile").get_data(as_text=True)

    def test_start_after_end_shows_error_and_falls_back_to_all_time(
        self, auth_client, add_expense
    ):
        add_expense(auth_client.user_id, 10.00, "Food", "2026-01-01", "Alpha")
        add_expense(auth_client.user_id, 20.00, "Transport", "2026-06-01", "Beta")
        baseline_html = self._all_time_total_html(auth_client)

        response = auth_client.get("/profile?start=2026-07-15&end=2026-07-01")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Invalid input must never crash the request"
        assert "Alpha" in html and "Beta" in html, "Should fall back to showing all-time data"
        assert "₹30.00" in html, "Fallback totals should match the unfiltered total"
        assert ("auth-error" in html), "A validation error message should be surfaced to the user"
        # Fallback view matches the plain baseline view's data.
        assert "Alpha" in baseline_html and "Beta" in baseline_html

    def test_invalid_date_format_shows_error_and_falls_back_to_all_time(
        self, auth_client, add_expense
    ):
        add_expense(auth_client.user_id, 15.00, "Food", "2026-01-01", "Gamma")

        response = auth_client.get("/profile?start=not-a-date&end=2026-07-15")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Malformed date input must never crash the request"
        assert "Gamma" in html, "Should fall back to all-time data on bad format"
        assert "auth-error" in html, "A validation error message should be surfaced"

    def test_invalid_end_date_format_shows_error_and_falls_back_to_all_time(
        self, auth_client, add_expense
    ):
        add_expense(auth_client.user_id, 15.00, "Food", "2026-01-01", "Delta")

        response = auth_client.get("/profile?start=2026-01-01&end=2026-13-40")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Delta" in html
        assert "auth-error" in html

    def test_sql_injection_like_start_value_falls_back_safely(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 15.00, "Food", "2026-01-01", "SafeRow")

        malicious = "2026-01-01' OR '1'='1"
        response = auth_client.get(f"/profile?start={malicious}&end=2026-12-31")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Injection-style input must never crash the request"
        assert "SafeRow" in html, "Should still render the user's real all-time data"
        assert "auth-error" in html, "Malformed date should be reported as a validation error"


# --------------------------------------------------------------------- #
# Sticky filter inputs
# --------------------------------------------------------------------- #

class TestProfileStickyInputs:
    def test_valid_filter_repopulates_inputs_with_submitted_values(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 5.00, "Food", "2026-07-05", "Whatever")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        assert extract_input_value(html, "start") == "2026-07-01", (
            "start input should be repopulated with the submitted value"
        )
        assert extract_input_value(html, "end") == "2026-07-15", (
            "end input should be repopulated with the submitted value"
        )

    def test_invalid_filter_still_repopulates_raw_submitted_values(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 5.00, "Food", "2026-07-05", "Whatever")

        response = auth_client.get("/profile?start=2026-08-01&end=2026-07-01")  # start after end
        html = response.get_data(as_text=True)

        assert extract_input_value(html, "start") == "2026-08-01", (
            "start input must keep the raw submitted value for correction"
        )
        assert extract_input_value(html, "end") == "2026-07-01", (
            "end input must keep the raw submitted value for correction"
        )

    def test_start_only_leaves_end_input_empty(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 5.00, "Food", "2026-07-05", "Whatever")

        response = auth_client.get("/profile?start=2026-07-01")
        html = response.get_data(as_text=True)

        assert extract_input_value(html, "start") == "2026-07-01"
        assert extract_input_value(html, "end") == "", "end input should stay empty when not submitted"


# --------------------------------------------------------------------- #
# Clear behaviour
# --------------------------------------------------------------------- #

class TestProfileClearBehaviour:
    def test_clear_link_points_to_plain_profile_url(self, auth_client, app):
        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-15")
        html = response.get_data(as_text=True)

        with app.test_request_context():
            plain_profile_url = url_for("profile")

        assert f'href="{plain_profile_url}"' in html, "Clear control should link back to plain /profile"
        assert f'href="{plain_profile_url}?' not in html, (
            "Clear link must not carry the active filter's query params forward"
        )

    def test_navigating_to_plain_profile_after_filtering_restores_all_time_view(
        self, auth_client, add_expense
    ):
        uid = auth_client.user_id
        add_expense(uid, 10.00, "Food", "2026-01-01", "OldOne")
        add_expense(uid, 20.00, "Transport", "2026-07-10", "NewOne")

        filtered_html = auth_client.get("/profile?start=2026-07-01&end=2026-07-31").get_data(as_text=True)
        assert "OldOne" not in filtered_html
        assert "NewOne" in filtered_html

        cleared_response = auth_client.get("/profile")
        cleared_html = cleared_response.get_data(as_text=True)

        assert cleared_response.status_code == 200
        assert "OldOne" in cleared_html and "NewOne" in cleared_html, (
            "Clearing the filter should restore the full, unfiltered all-time view"
        )
        assert "₹30.00" in cleared_html


# --------------------------------------------------------------------- #
# Currency formatting persists under filtering
# --------------------------------------------------------------------- #

class TestProfileCurrencyDisplay:
    def test_amounts_display_rupee_symbol_when_filtered(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 42.50, "Food", "2026-07-05", "RupeeCheck")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-31")
        html = response.get_data(as_text=True)

        assert "₹42.50" in html, "Filtered transaction amounts must still show the ₹ symbol"
        assert "₹" in html.split("Total spent")[1][:100], "Summary total must still show the ₹ symbol"


# --------------------------------------------------------------------- #
# Category breakdown percentages must always sum to 100
# --------------------------------------------------------------------- #

class TestProfileCategoryBreakdownPercentages:
    def test_percentages_sum_to_100_for_filtered_subset(self, auth_client, add_expense):
        uid = auth_client.user_id
        # Amounts chosen so raw percentages don't divide evenly (33.33...%).
        add_expense(uid, 10.00, "Food", "2026-07-01", "PctFood")
        add_expense(uid, 10.00, "Transport", "2026-07-02", "PctTransport")
        add_expense(uid, 10.00, "Bills", "2026-07-03", "PctBills")
        # Outside the filter -- must not affect the filtered percentages.
        add_expense(uid, 500.00, "Shopping", "2026-01-01", "OutOfRangeBig")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-31")
        html = response.get_data(as_text=True)

        pcts = extract_percentages(html)
        assert len(pcts) == 3, f"Expected 3 category rows in the filtered breakdown, got {len(pcts)}"
        assert sum(pcts) == 100, f"Filtered category percentages must sum to 100, got {sum(pcts)}"

    def test_percentages_sum_to_100_for_unequal_filtered_amounts(self, auth_client, add_expense):
        uid = auth_client.user_id
        add_expense(uid, 7.00, "Food", "2026-07-01", "A")
        add_expense(uid, 13.00, "Transport", "2026-07-02", "B")
        add_expense(uid, 5.00, "Bills", "2026-07-03", "C")

        response = auth_client.get("/profile?start=2026-07-01&end=2026-07-31")
        html = response.get_data(as_text=True)

        pcts = extract_percentages(html)
        assert sum(pcts) == 100, f"Filtered category percentages must sum to 100, got {sum(pcts)}"

    def test_no_breakdown_rows_when_zero_matches_in_filtered_range(self, auth_client, add_expense):
        add_expense(auth_client.user_id, 10.00, "Food", "2026-01-01", "NotInRange")

        response = auth_client.get("/profile?start=2026-12-01&end=2026-12-31")
        html = response.get_data(as_text=True)

        assert extract_percentages(html) == [], "A zero-match range should have no breakdown rows at all"


# --------------------------------------------------------------------- #
# Unaffected routes / general regression guard
# --------------------------------------------------------------------- #

class TestUnaffectedRoutes:
    def test_landing_page_still_loads(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_register_page_still_loads(self, client):
        response = client.get("/register")
        assert response.status_code == 200

    def test_login_page_still_loads(self, client):
        response = client.get("/login")
        assert response.status_code == 200

    def test_logout_redirects_to_login(self, auth_client):
        response = auth_client.get("/logout")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
