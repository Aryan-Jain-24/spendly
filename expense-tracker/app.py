from datetime import datetime
import math

from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, CATEGORIES
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    create_expense,
    get_expense_by_id,
    update_expense,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            return render_template("register.html", error="All fields are required."), 400

        if len(password) < 8:
            return render_template(
                "register.html", error="Password must be at least 8 characters long."
            ), 400

        db = get_db()
        existing_user = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing_user is not None:
            db.close()
            return render_template(
                "register.html", error="An account with this email already exists."
            ), 400

        password_hash = generate_password_hash(password)
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        db.commit()
        user_id = cursor.lastrowid
        db.close()

        session["user_id"] = user_id
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            return render_template("login.html", error="Invalid email or password."), 401

        db = get_db()
        user = db.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password."), 401

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


def _parse_date_filter(args):
    """Read/validate start & end from query args.

    Returns (start, end, query_start, query_end, error) — start/end are the raw
    sticky values for repopulating the form; query_start/query_end are what gets
    passed to the DB (None, None on any validation error).
    """
    def is_valid(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    start = args.get("start", "").strip() or None
    end = args.get("end", "").strip() or None

    error = None
    if start and not is_valid(start):
        error = "Start date must be in YYYY-MM-DD format."
    elif end and not is_valid(end):
        error = "End date must be in YYYY-MM-DD format."
    elif start and end and start > end:
        error = "Start date must be on or before end date."

    query_start, query_end = (None, None) if error else (start, end)
    return start, end, query_start, query_end, error


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)

    if user is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    start, end, query_start, query_end, filter_error = _parse_date_filter(request.args)

    summary = get_summary_stats(user_id, start_date=query_start, end_date=query_end)
    transactions = get_recent_transactions(user_id, start_date=query_start, end_date=query_end)
    categories = get_category_breakdown(user_id, start_date=query_start, end_date=query_end)

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        transactions=transactions,
        categories=categories,
        start=start,
        end=end,
        filter_error=filter_error,
        active_page="profile",
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("analytics.html", active_page="analytics")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    if get_user_by_id(user_id) is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    today = datetime.now().strftime("%Y-%m-%d")

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip()

        error = None
        amount = None

        if not amount_raw:
            error = "Amount is required."
        else:
            try:
                amount = float(amount_raw)
            except ValueError:
                error = "Amount must be a valid number."
            else:
                if not math.isfinite(amount):
                    error = "Amount must be a valid number."
                elif amount <= 0:
                    error = "Amount must be greater than zero."

        if not error and category not in CATEGORIES:
            error = "Please select a valid category."

        if not error:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Date must be in YYYY-MM-DD format."

        if error:
            return render_template(
                "add_expense.html",
                error=error,
                categories=CATEGORIES,
                amount=amount_raw,
                category=category,
                date=date_raw,
                description=description,
            ), 400

        create_expense(user_id, amount, category, date_raw, description or None)
        return redirect(url_for("profile"))

    return render_template(
        "add_expense.html",
        categories=CATEGORIES,
        amount="",
        category="",
        date=today,
        description="",
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    if get_user_by_id(user_id) is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip()

        error = None
        amount = None

        if not amount_raw:
            error = "Amount is required."
        else:
            try:
                amount = float(amount_raw)
            except ValueError:
                error = "Amount must be a valid number."
            else:
                if not math.isfinite(amount):
                    error = "Amount must be a valid number."
                elif amount <= 0:
                    error = "Amount must be greater than zero."

        if not error and category not in CATEGORIES:
            error = "Please select a valid category."

        if not error:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Date must be in YYYY-MM-DD format."

        if error:
            return render_template(
                "edit_expense.html",
                error=error,
                categories=CATEGORIES,
                expense={
                    "id": id,
                    "amount": amount_raw,
                    "category": category,
                    "date": date_raw,
                    "description": description,
                },
            ), 400

        update_expense(id, user_id, amount, category, date_raw, description or None)
        return redirect(url_for("profile"))

    return render_template(
        "edit_expense.html",
        categories=CATEGORIES,
        expense=expense,
    )


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
