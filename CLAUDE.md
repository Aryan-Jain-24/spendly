# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spendly is a Flask-based expense tracker built as a step-by-step learning project. The codebase currently contains scaffolding with placeholder routes; most functionality (database layer, auth, expense CRUD) is intentionally unimplemented and marked with comments like `# Students will write this file in Step 1` and `return "Add expense — coming in Step 7"`. When asked to implement a feature, check `app.py` and `database/db.py` for these step markers to understand what's expected at that stage, and don't jump ahead to build unrelated future steps.

## Commands

Run all commands from `expense-tracker/` (the Flask app root), with the `venv` at the repo root activated.

```bash
# Activate the virtualenv (from repo root)
source venv/Scripts/activate      # Git Bash
# or: venv\Scripts\Activate.ps1   # PowerShell

# Install dependencies
pip install -r expense-tracker/requirements.txt

# Run the dev server (from expense-tracker/)
python app.py                     # serves on http://localhost:5001, debug=True

# Run tests
pytest                            # all tests
pytest path/to/test_file.py::test_name   # single test
```

There is no configured lint/format command in this repo yet.

## Architecture

- **`app.py`** — single Flask application entry point; all routes are defined here (no blueprints). App runs on port 5001.
- **`database/db.py`** — intended to hold the SQLite data-access layer: `get_db()` (SQLite connection with `row_factory` and foreign keys enabled), `init_db()` (creates tables with `CREATE TABLE IF NOT EXISTS`), and `seed_db()` (dev sample data). The SQLite file (`expense_tracker.db`) is gitignored and created locally.
- **`templates/`** — Jinja2 templates. `base.html` is the shared layout (nav, footer, font/CSS includes) that other templates extend via `{% block content %}`.
- **`static/css/style.css`** and **`static/js/main.js`** — shared frontend assets referenced from `base.html` via `url_for('static', ...)`.

No ORM is used — expect raw SQL via `sqlite3` once `database/db.py` is implemented.
