"""SQLite persistence for successful email classifications."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "email_classifier.db"
ALLOWED_CATEGORIES = {"Legitimate", "Spam", "Phishing"}


def initialize_database(database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Create the database and history table if they do not already exist."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS email_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL DEFAULT '',
                    email_body TEXT NOT NULL DEFAULT '',
                    predicted_category TEXT NOT NULL
                        CHECK (predicted_category IN ('Legitimate', 'Spam', 'Phishing')),
                    confidence_estimate REAL NOT NULL
                        CHECK (confidence_estimate >= 0.0 AND confidence_estimate <= 1.0),
                    predicted_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_history_predicted_at "
                "ON email_history(predicted_at DESC)"
            )
    finally:
        connection.close()


def save_prediction(
    database_path: str | Path,
    *,
    subject: str,
    email_body: str,
    predicted_category: str,
    confidence_estimate: float,
) -> dict[str, Any]:
    """Validate and save one successful classifier result using SQL parameters."""
    if not isinstance(subject, str) or not isinstance(email_body, str):
        raise ValueError("Subject and email body must be text.")
    if not subject.strip() and not email_body.strip():
        raise ValueError("An empty email cannot be saved.")
    if predicted_category not in ALLOWED_CATEGORIES:
        raise ValueError("Unsupported prediction category.")
    if not isinstance(confidence_estimate, (int, float)) or not math.isfinite(confidence_estimate):
        raise ValueError("Confidence estimate must be a finite number.")
    if not 0.0 <= confidence_estimate <= 1.0:
        raise ValueError("Confidence estimate must be between 0 and 1.")

    predicted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO email_history
                    (subject, email_body, predicted_category, confidence_estimate, predicted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (subject.strip(), email_body.strip(), predicted_category,
                 float(confidence_estimate), predicted_at),
            )
            return {
                "id": int(cursor.lastrowid),
                "subject": subject.strip(),
                "email_body": email_body.strip(),
                "predicted_category": predicted_category,
                "confidence_estimate": float(confidence_estimate),
                "predicted_at": predicted_at,
            }
    finally:
        connection.close()


def get_dashboard_stats(database_path: str | Path) -> dict[str, int | float]:
    """Return record counts and percentages for the saved email history."""
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        counts = {
            category: int(count)
            for category, count in connection.execute(
                "SELECT predicted_category, COUNT(*) FROM email_history GROUP BY predicted_category"
            )
        }
        total = sum(counts.values())
        statistics = {
            "total": sum(counts.values()),
            "legitimate": counts.get("Legitimate", 0),
            "spam": counts.get("Spam", 0),
            "phishing": counts.get("Phishing", 0),
        }
        statistics["legitimate_percentage"] = (
            round(statistics["legitimate"] * 100 / total, 1) if total else 0.0
        )
        statistics["spam_percentage"] = (
            round(statistics["spam"] * 100 / total, 1) if total else 0.0
        )
        statistics["phishing_percentage"] = (
            round(statistics["phishing"] * 100 / total, 1) if total else 0.0
        )
        return statistics
    finally:
        connection.close()


def get_recent_history(database_path: str | Path, limit: int = 5) -> list[dict[str, Any]]:
    """Return the newest saved classifications."""
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("History limit must be a positive integer.")
    connection = sqlite3.connect(database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, subject, email_body, predicted_category,
                   confidence_estimate, predicted_at
            FROM email_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def query_email_history(
    database_path: str | Path,
    *,
    category: str = "all",
    search: str = "",
    page: int = 1,
    per_page: int = 10,
) -> dict[str, Any]:
    """Search and paginate history, using bound parameters for all user input."""
    normalized_category = category.strip().casefold()
    category_values = {
        "all": None,
        "legitimate": "Legitimate",
        "spam": "Spam",
        "phishing": "Phishing",
    }
    if normalized_category not in category_values:
        raise ValueError("Unsupported history category.")
    if not isinstance(search, str) or len(search) > 200:
        raise ValueError("Subject search must be 200 characters or fewer.")
    if not isinstance(page, int) or page < 1:
        raise ValueError("Page number must be a positive integer.")
    if not isinstance(per_page, int) or per_page < 1 or per_page > 100:
        raise ValueError("Page size must be between 1 and 100.")

    conditions: list[str] = []
    parameters: list[Any] = []
    selected_category = category_values[normalized_category]
    if selected_category:
        conditions.append("predicted_category = ?")
        parameters.append(selected_category)
    if search.strip():
        conditions.append("instr(lower(subject), lower(?)) > 0")
        parameters.append(search.strip())
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    connection = sqlite3.connect(database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        total_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM email_history" + where_clause,
                parameters,
            ).fetchone()[0]
        )
        total_pages = max(1, math.ceil(total_count / per_page))
        selected_page = min(page, total_pages)
        offset = (selected_page - 1) * per_page
        rows = connection.execute(
            """
            SELECT id, subject, email_body, predicted_category,
                   confidence_estimate, predicted_at
            FROM email_history
            """
            + where_clause
            + " ORDER BY id DESC LIMIT ? OFFSET ?",
            [*parameters, per_page, offset],
        ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total_count": total_count,
            "page": selected_page,
            "per_page": per_page,
            "total_pages": total_pages,
            "category": normalized_category,
            "search": search.strip(),
        }
    finally:
        connection.close()


def get_history_record(database_path: str | Path, record_id: int) -> dict[str, Any] | None:
    """Fetch one complete history row by primary key."""
    connection = sqlite3.connect(database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT id, subject, email_body, predicted_category,
                   confidence_estimate, predicted_at
            FROM email_history WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def delete_history_record(database_path: str | Path, record_id: int) -> bool:
    """Delete one history row; return False when the id does not exist."""
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM email_history WHERE id = ?",
                (record_id,),
            )
            return cursor.rowcount == 1
    finally:
        connection.close()
