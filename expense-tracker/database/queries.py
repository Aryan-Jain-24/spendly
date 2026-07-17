from datetime import datetime

from database.db import get_db


def _apply_date_filter(query, params, start_date, end_date):
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    return query


def get_user_by_id(user_id):
    db = get_db()
    user = db.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    db.close()

    if user is None:
        return None

    member_since = datetime.strptime(
        user["created_at"], "%Y-%m-%d %H:%M:%S"
    ).strftime("%B %Y")

    return {"name": user["name"], "email": user["email"], "member_since": member_since}


def get_summary_stats(user_id, start_date=None, end_date=None):
    db = get_db()

    total_query = (
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
        "FROM expenses WHERE user_id = ?"
    )
    total_params = [user_id]
    total_query = _apply_date_filter(total_query, total_params, start_date, end_date)
    total_row = db.execute(total_query, total_params).fetchone()

    top_query = "SELECT category FROM expenses WHERE user_id = ?"
    top_params = [user_id]
    top_query = _apply_date_filter(top_query, top_params, start_date, end_date)
    top_query += " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1"
    top_row = db.execute(top_query, top_params).fetchone()

    db.close()

    return {
        "total_spent": total_row["total"],
        "transaction_count": total_row["count"],
        "top_category": top_row["category"] if top_row else "—",
    }


def get_recent_transactions(user_id, start_date=None, end_date=None, limit=10):
    db = get_db()

    query = "SELECT date, description, category, amount FROM expenses WHERE user_id = ?"
    params = [user_id]
    query = _apply_date_filter(query, params, start_date, end_date)
    query += " ORDER BY date DESC, id DESC"

    if not (start_date or end_date):
        query += " LIMIT ?"
        params.append(limit)

    rows = db.execute(query, params).fetchall()
    db.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id, start_date=None, end_date=None):
    db = get_db()

    query = "SELECT category, SUM(amount) AS amount FROM expenses WHERE user_id = ?"
    params = [user_id]
    query = _apply_date_filter(query, params, start_date, end_date)
    query += " GROUP BY category ORDER BY amount DESC"

    rows = db.execute(query, params).fetchall()
    db.close()

    if not rows:
        return []

    total = sum(row["amount"] for row in rows)
    breakdown = [
        {"name": row["category"], "amount": row["amount"], "pct": 0}
        for row in rows
    ]

    raw_pcts = [(row["amount"] / total) * 100 for row in rows]
    rounded_pcts = [round(p) for p in raw_pcts]
    remainder = 100 - sum(rounded_pcts)
    largest_index = max(range(len(breakdown)), key=lambda i: breakdown[i]["amount"])
    rounded_pcts[largest_index] += remainder

    for item, pct in zip(breakdown, rounded_pcts):
        item["pct"] = pct

    return breakdown


def create_expense(user_id, amount, category, date, description=None):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    db.commit()
    expense_id = cursor.lastrowid
    db.close()
    return expense_id
