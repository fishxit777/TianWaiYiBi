"""Paid image access. Filesystem identifiers are never public asset URLs."""

import re
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from .access import current_customer_session
from .concept_guides import get_concept_guide
from .db import get_db


private_content_bp = Blueprint("private_content", __name__)
ASSET_FIELDS = {"hero": "hero_image", "diagram": "diagram_image", "scene": "scene_image"}


def resolve_private_asset(identifier):
    """Resolve a stored identifier, never a request-supplied filesystem path."""
    value = str(identifier or "")
    if not re.fullmatch(r"brand/[a-zA-Z0-9_/-]+(?:\.[a-zA-Z0-9_-]+)*\.(?:webp|png|jpe?g)", value):
        return None
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return None
    root = Path(current_app.config["PRIVATE_ASSET_ROOT"]).resolve()
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def _not_found():
    response = jsonify({"error": "找不到此頁"})
    response.status_code = 404
    response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def deny_public_paid_assets():
    """Defend retired URLs even if a build accidentally recreates static files."""
    if request.endpoint != "static":
        return None
    identifier = str((request.view_args or {}).get("filename", ""))
    normalized = identifier.replace("\\", "/")
    if normalized.startswith(("brand/concepts/", "brand/blindbox-twin-tire-")):
        return _not_found()
    if normalized.startswith("brand/"):
        referenced = get_db().execute(
            "SELECT 1 FROM ideas WHERE hero_image = ? OR diagram_image = ? OR scene_image = ? LIMIT 1",
            (identifier, identifier, identifier),
        ).fetchone()
        if referenced is not None:
            return _not_found()
    return None


@private_content_bp.get("/library/assets/<int:idea_id>/<slot>")
def paid_asset(idea_id, slot):
    field = ASSET_FIELDS.get(slot)
    if field is None and slot != "introduction":
        return _not_found()
    customer = current_customer_session()
    if customer is None:
        return _not_found()
    row = get_db().execute(
        """
        SELECT ideas.slug, ideas.hero_image, ideas.diagram_image, ideas.scene_image
        FROM ideas
        WHERE ideas.id = ? AND EXISTS (
            SELECT 1 FROM orders
            WHERE orders.idea_id = ideas.id AND orders.customer_email = ? AND orders.status = 'paid'
        )
        """,
        (idea_id, customer["customer_email"]),
    ).fetchone()
    if row is None:
        return _not_found()
    if slot == "introduction":
        guide = get_concept_guide(row["slug"])
        identifier = guide["asset"] if guide else None
    else:
        identifier = row[field]
    path = resolve_private_asset(identifier)
    if path is None:
        return _not_found()
    # Authorize before every response, including HEAD / conditional / Range requests.
    # Images are small: no partial or 304 responses, no reusable validators.
    response = send_file(path, conditional=False, etag=False, max_age=0)
    response.headers.pop("Last-Modified", None)
    response.headers.pop("ETag", None)
    response.headers["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Vary"] = "Cookie"
    return response
