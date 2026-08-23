import hmac
import os

from flask import Blueprint, abort, jsonify, request

from .notifications import SLOTS, queue_daily_summary


notification_bp = Blueprint("notification_jobs", __name__, url_prefix="/internal/notifications")


@notification_bp.post("/daily-summary")
def daily_summary():
    configured = os.environ.get("NOTIFICATION_CRON_SECRET", "").strip()
    supplied = request.headers.get("X-Notification-Secret", "").strip()
    if len(configured) < 32 or not supplied or not hmac.compare_digest(configured, supplied):
        abort(404)

    payload = request.get_json(silent=True) or {}
    slot = str(payload.get("slot", "")).strip().lower()
    if slot not in SLOTS:
        return jsonify({"error": "invalid_slot"}), 400

    return jsonify(queue_daily_summary(slot))
