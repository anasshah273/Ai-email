import sqlite3

from flask import Flask, jsonify, render_template, request

from database import (
    DEFAULT_DATABASE_PATH,
    delete_history_record,
    get_dashboard_stats,
    get_history_record,
    get_recent_history,
    initialize_database,
    query_email_history,
    save_prediction,
)
from ml.predict import predict_email

app = Flask(__name__)
app.config["DATABASE"] = str(DEFAULT_DATABASE_PATH)

try:
    initialize_database(app.config["DATABASE"])
except sqlite3.Error:
    app.logger.exception("Could not initialize the email history database.")

ALLOWED_LABELS = {"Legitimate", "Spam", "Phishing"}
MAX_SUBJECT_LENGTH = 500
MAX_BODY_LENGTH = 10_000


@app.get("/")
def dashboard():
    try:
        dashboard_stats = get_dashboard_stats(app.config["DATABASE"])
        recent_history = get_recent_history(app.config["DATABASE"])
        database_available = True
    except sqlite3.Error:
        app.logger.exception("Could not read the email history database.")
        dashboard_stats = None
        recent_history = []
        database_available = False
    return render_template(
        "index.html",
        dashboard_stats=dashboard_stats,
        recent_history=recent_history,
        database_available=database_available,
    )


@app.get("/history")
def email_history():
    category = request.args.get("category", "all").strip().casefold()
    search = request.args.get("q", "")
    raw_page = request.args.get("page", "1")
    if category not in {"all", "legitimate", "spam", "phishing"}:
        return render_template(
            "history.html",
            history_error="Choose All, Legitimate, Spam, or Phishing to filter history.",
            category="all",
            search=search[:200],
            entries=[],
            total_count=0,
            page=1,
            total_pages=1,
            start_record=0,
            end_record=0,
        ), 400
    if len(search) > 200:
        return render_template(
            "history.html",
            history_error="Subject search must be 200 characters or fewer.",
            category=category,
            search=search[:200],
            entries=[],
            total_count=0,
            page=1,
            total_pages=1,
            start_record=0,
            end_record=0,
        ), 400
    try:
        page = int(raw_page)
        result = query_email_history(
            app.config["DATABASE"],
            category=category,
            search=search,
            page=page,
            per_page=10,
        )
        start_record = (result["page"] - 1) * result["per_page"] + 1 if result["total_count"] else 0
        end_record = start_record + len(result["items"]) - 1 if result["items"] else 0
        return render_template(
            "history.html",
            history_error=None,
            entries=result["items"],
            category=result["category"],
            search=result["search"],
            total_count=result["total_count"],
            page=result["page"],
            total_pages=result["total_pages"],
            start_record=start_record,
            end_record=end_record,
        )
    except ValueError:
        return render_template(
            "history.html",
            history_error="Page number must be a positive whole number.",
            category=category,
            search=search,
            entries=[],
            total_count=0,
            page=1,
            total_pages=1,
            start_record=0,
            end_record=0,
        ), 400
    except sqlite3.Error:
        app.logger.exception("Could not load email history.")
        return render_template(
            "history.html",
            history_error="Email history is temporarily unavailable. Please try again.",
            category=category,
            search=search,
            entries=[],
            total_count=0,
            page=1,
            total_pages=1,
            start_record=0,
            end_record=0,
        ), 503


@app.get("/api/statistics")
def email_statistics():
    """Return live counts and percentages from the existing SQLite database."""
    try:
        return jsonify(get_dashboard_stats(app.config["DATABASE"]))
    except sqlite3.Error:
        app.logger.exception("Could not read dashboard statistics.")
        return jsonify({"error": "Dashboard statistics are temporarily unavailable."}), 503


@app.get("/api/history/<int:record_id>")
def email_history_detail(record_id: int):
    try:
        record = get_history_record(app.config["DATABASE"], record_id)
    except sqlite3.Error:
        app.logger.exception("Could not load email history record %s.", record_id)
        return jsonify({"error": "Email details are temporarily unavailable."}), 500
    if record is None:
        return jsonify({"error": "Email history record not found."}), 404
    return jsonify(record)


@app.delete("/api/history/<int:record_id>")
def delete_email_history(record_id: int):
    try:
        deleted = delete_history_record(app.config["DATABASE"], record_id)
    except sqlite3.Error:
        app.logger.exception("Could not delete email history record %s.", record_id)
        return jsonify({"error": "The email history record could not be deleted."}), 500
    if not deleted:
        return jsonify({"error": "Email history record not found."}), 404
    return jsonify({"deleted": True, "id": record_id})


@app.post("/predict")
def predict():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    subject = payload.get("subject", "")
    body = payload.get("body", "")
    if not isinstance(subject, str) or not isinstance(body, str):
        return jsonify({"error": "Subject and body must be text values."}), 400

    subject = subject.strip()
    body = body.strip()
    if not subject and not body:
        return jsonify({"error": "Enter an email subject, body, or both."}), 400
    if len(subject) > MAX_SUBJECT_LENGTH:
        return jsonify({"error": f"Subject must be {MAX_SUBJECT_LENGTH} characters or fewer."}), 400
    if len(body) > MAX_BODY_LENGTH:
        return jsonify({"error": f"Email body must be {MAX_BODY_LENGTH} characters or fewer."}), 400

    email_text = f"Subject: {subject}\nBody: {body}"
    try:
        result = predict_email(email_text)
        label = result.get("label")
        if label not in ALLOWED_LABELS:
            app.logger.error("Classifier returned an unsupported label: %r", label)
            return jsonify({"error": "The classifier returned an unsupported result."}), 500

        probabilities = {
            str(category): float(probability)
            for category, probability in result["probabilities"].items()
            if category in ALLOWED_LABELS
        }
        if set(probabilities) != ALLOWED_LABELS:
            app.logger.error("Classifier probability classes did not match the supported labels.")
            return jsonify({"error": "The classifier returned incomplete probability estimates."}), 500

        try:
            history_entry = save_prediction(
                app.config["DATABASE"],
                subject=subject,
                email_body=body,
                predicted_category=label,
                confidence_estimate=float(result["confidence"]),
            )
        except sqlite3.Error:
            app.logger.exception("Could not save the email classification.")
            return jsonify({"error": "The prediction was generated but could not be saved to history."}), 500

        try:
            dashboard_stats = get_dashboard_stats(app.config["DATABASE"])
        except sqlite3.Error:
            app.logger.exception("Could not refresh dashboard statistics after saving a prediction.")
            dashboard_stats = None

        return jsonify(
            {
                "prediction": label,
                "confidence": float(result["confidence"]),
                "probabilities": probabilities,
                "warning": (
                    "These are uncalibrated model probability estimates, not guarantees "
                    "of correctness. Review the email carefully."
                ),
                "history_entry": history_entry,
                "statistics": dashboard_stats,
            }
        )
    except FileNotFoundError:
        app.logger.exception("Trained email classifier artifacts are unavailable.")
        return jsonify({"error": "The trained classifier is unavailable. Check the model files."}), 503
    except Exception:
        app.logger.exception("Email classification failed.")
        return jsonify({"error": "The email could not be classified due to a model error."}), 500


if __name__ == "__main__":
    app.run(debug=True)
