from datetime import datetime

from database.db import get_db


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


def get_summary_stats(user_id):
    db = get_db()
    total_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
        "FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    top_row = db.execute(
        "SELECT category FROM expenses WHERE user_id = ? "
        "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    db.close()

    return {
        "total_spent": total_row["total"],
        "transaction_count": total_row["count"],
        "top_category": top_row["category"] if top_row else "—",
    }


def get_recent_transactions(user_id, limit=10):
    db = get_db()
    rows = db.execute(
        "SELECT date, description, category, amount FROM expenses "
        "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
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


def get_category_breakdown(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT category, SUM(amount) AS amount FROM expenses "
        "WHERE user_id = ? GROUP BY category ORDER BY amount DESC",
        (user_id,),
    ).fetchall()
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
