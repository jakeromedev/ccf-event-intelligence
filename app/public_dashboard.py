"""Password-gated, presentation-only Event dashboards."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .aggregation import active_batch, event_dashboard_metrics
from .db import get_db
from .models import verify_password_hash


bp = Blueprint("public_dashboard", __name__)

ACCESS_DURATION_SECONDS = 7 * 24 * 60 * 60
ACCESS_TOKEN_SALT = "public-dashboard-access-v1"
PASSWORD_MAX_LENGTH = 128


def _event_or_404(event_id):
    event = get_db().execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if event is None or not event["public_dashboard_password_hash"]:
        abort(404)
    return event


def _cookie_name(event_id):
    return "public_dashboard_access_{}".format(event_id)


def _serializer():
    return URLSafeTimedSerializer(
        current_app.secret_key, salt=ACCESS_TOKEN_SALT
    )


def _has_access(event):
    token = request.cookies.get(_cookie_name(event["id"]))
    if not token:
        return False
    try:
        payload = _serializer().loads(token, max_age=ACCESS_DURATION_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and (
        payload.get("event_id") == event["id"]
        and payload.get("access_version")
        == event["public_dashboard_access_version"]
    )


def _private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.route("/public/events/<int:event_id>/dashboard", methods=("GET", "POST"))
def event_dashboard(event_id):
    event = _event_or_404(event_id)
    password_error = None

    if request.method == "POST":
        password = request.form.get("password") or ""
        if len(password) <= PASSWORD_MAX_LENGTH and verify_password_hash(
            event["public_dashboard_password_hash"], password
        ):
            token = _serializer().dumps(
                {
                    "event_id": event["id"],
                    "access_version": event["public_dashboard_access_version"],
                }
            )
            response = redirect(
                url_for("public_dashboard.event_dashboard", event_id=event["id"])
            )
            response.set_cookie(
                _cookie_name(event["id"]),
                token,
                max_age=ACCESS_DURATION_SECONDS,
                httponly=True,
                secure=current_app.config["SESSION_COOKIE_SECURE"],
                samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
                path=url_for(
                    "public_dashboard.event_dashboard", event_id=event["id"]
                ),
            )
            return _private_response(response)
        current_app.logger.warning(
            "public_dashboard_access_denied",
            extra={"event": "public_dashboard_access_denied", "event_id": event["id"]},
        )
        password_error = "The dashboard password is incorrect."

    if not _has_access(event):
        response = make_response(
            render_template(
                "public_dashboard_access.html",
                event=event,
                password_error=password_error,
            ),
            401 if password_error else 200,
        )
        return _private_response(response)

    db = get_db()
    dashboard = event_dashboard_metrics(
        db,
        event["id"],
        satellite_query=request.args.get("satellite_q", ""),
        satellite_page=request.args.get("satellite_page", 1),
    )
    response = make_response(
        render_template(
            "overview.html",
            event=event,
            active_batch=active_batch(db, event["id"]),
            dashboard=dashboard,
            metrics=dashboard["overview"],
            profile=dashboard["participant_profile"],
            public_dashboard=True,
        )
    )
    return _private_response(response)
