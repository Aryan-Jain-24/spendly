import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

DB_PATH = "expense_tracker.db"

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()

    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = date.today()
    sample_expenses = [
        (user_id, 24.50, "Food", today.replace(day=1).isoformat(), "Groceries"),
        (user_id, 12.00, "Transport", today.replace(day=2).isoformat(), "Bus pass"),
        (user_id, 89.99, "Bills", today.replace(day=3).isoformat(), "Electricity bill"),
        (user_id, 45.00, "Health", today.replace(day=5).isoformat(), "Pharmacy"),
        (user_id, 15.75, "Entertainment", today.replace(day=8).isoformat(), "Movie tickets"),
        (user_id, 60.20, "Shopping", today.replace(day=10).isoformat(), "New shoes"),
        (user_id, 9.99, "Other", today.replace(day=12).isoformat(), "Miscellaneous"),
        (user_id, 32.40, "Food", today.replace(day=14).isoformat(), "Restaurant"),
    ]

    conn.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_expenses,
    )

    conn.commit()
    conn.close()
