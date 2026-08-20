from datetime import datetime

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for

from .aggregation import (
    active_batch,
    data_quality,
    data_quality_issue_instances,
    event_summaries,
    overview_metrics,
    overview_registrants,
    participant_profile_metrics,
    satellite_metrics,
    satellite_registrants,
)
from .db import get_db
from .import_history import IMPORT_HISTORY_STATUSES, import_history
from .importer import process_batch, stage_upload_set, store_validation, validate_batch


bp = Blueprint("dashboard", __name__)


def get_event_or_404(event_id):
    event = get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        abort(404)
    return event


@bp.get("/")
def index():
    return redirect(url_for("dashboard.events"))


@bp.get("/events")
def events():
    db = get_db()
    return render_template(
        "events.html",
        event=None,
        active_batch=None,
        event_summaries=event_summaries(db),
    )


@bp.get("/events/new")
def new_event():
    return render_template("event_new.html", event=None, active_batch=None)


@bp.post("/events")
def create_event():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Event Name is required.", "error")
        return render_template("event_new.html", event=None, active_batch=None, entered_name=name), 400
    if len(name) > 160:
        flash("Event Name must be 160 characters or fewer.", "error")
        return render_template("event_new.html", event=None, active_batch=None, entered_name=name), 400

    db = get_db()
    cursor = db.execute("INSERT INTO events (name) VALUES (?)", (name,))
    db.commit()
    flash("Event created. Upload the three required exports to build its dashboard.", "success")
    return redirect(url_for("dashboard.event_overview", event_id=cursor.lastrowid))


@bp.get("/events/<int:event_id>")
def event_overview(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    metrics = overview_metrics(db, batch["id"], "registrants") if batch else None
    profile = participant_profile_metrics(db, batch["id"]) if batch else None
    return render_template(
        "overview.html",
        event=event,
        active_batch=batch,
        metrics=metrics,
        profile=profile,
    )


@bp.get("/events/<int:event_id>/overview/registrants")
def event_overview_registrants(event_id):
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    if not batch:
        return jsonify({"registrants": []})
    return jsonify({"registrants": overview_registrants(db, batch["id"])})


@bp.get("/events/<int:event_id>/satellites")
def event_satellites(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    scope = request.args.get("scope", "all")
    if scope not in ("all", "local", "international"):
        scope = "all"
    query = (request.args.get("q") or "").strip()[:100]
    page = request.args.get("page", default=1, type=int) or 1
    page = max(page, 1)
    per_page = request.args.get("per_page", default=10, type=int)
    if per_page not in (10, 25, 50):
        per_page = 10
    sort = request.args.get("sort", "registrants")
    if sort not in ("name", "scope", "registrants", "checked_in", "attendance_rate"):
        sort = "registrants"
    direction = request.args.get("direction", "desc")
    if direction not in ("asc", "desc"):
        direction = "desc"
    metrics = (
        satellite_metrics(
            db,
            batch["id"],
            scope=scope,
            query=query,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )
        if batch
        else None
    )
    return render_template(
        "satellites.html",
        event=event,
        active_batch=batch,
        metrics=metrics,
        scope=scope,
        query=query,
        sort=sort,
        direction=direction,
    )


@bp.get("/events/<int:event_id>/satellites/registrants")
def event_satellite_registrants(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    satellite_name = (request.args.get("name") or "").strip()[:200]
    scope = request.args.get("scope", "")
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = request.args.get("per_page", default=50, type=int)
    if per_page not in (25, 50, 100):
        per_page = 50

    participant_data = None
    if batch:
        if not satellite_name or scope not in ("local", "international"):
            abort(404)
        participant_data = satellite_registrants(
            db,
            batch["id"],
            satellite_name,
            scope,
            page=page,
            per_page=per_page,
        )
        if participant_data is None:
            abort(404)
    return render_template(
        "satellite_registrants.html",
        event=event,
        active_batch=batch,
        satellite=participant_data,
    )


@bp.get("/events/<int:event_id>/data-quality")
def event_quality(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    query = (request.args.get("q") or "").strip()[:100]
    severity = request.args.get("severity", "all")
    if severity not in ("all", "warning", "error"):
        severity = "all"
    category = (request.args.get("category") or "all").strip()[:100]
    entity = (request.args.get("entity") or "all").strip()[:100]
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = request.args.get("per_page", default=10, type=int)
    if per_page not in (10, 25, 50):
        per_page = 10
    sort = request.args.get("sort", "severity")
    if sort not in ("severity", "category", "entity", "count", "source_identifier", "row"):
        sort = "severity"
    direction = request.args.get("direction", "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"
    quality_data = (
        data_quality(
            db,
            batch["id"],
            query=query,
            severity=severity,
            category=category,
            entity=entity,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )
        if batch
        else None
    )
    return render_template(
        "data_quality.html",
        event=event,
        active_batch=batch,
        quality=quality_data,
    )


@bp.get("/events/<int:event_id>/data-quality/issues")
def event_quality_issues(event_id):
    """Return privacy-safe, event-scoped issue instances for a summary card."""
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    if not batch:
        return jsonify(
            {
                "category": "",
                "label": "Data Quality Issues",
                "entities": [],
                "filters": {"query": "", "severity": "all", "entity": "all"},
                "issues": [],
                "pagination": {
                    "page": 1,
                    "pages": 1,
                    "per_page": 10,
                    "total": 0,
                    "start": 0,
                    "end": 0,
                    "has_previous": False,
                    "has_next": False,
                },
            }
        )

    category = (request.args.get("category") or "").strip()[:100]
    query = (request.args.get("q") or "").strip()[:100]
    severity = request.args.get("severity", "all")
    entity = (request.args.get("entity") or "all").strip()[:100]
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = request.args.get("per_page", default=10, type=int)
    result = data_quality_issue_instances(
        db,
        batch["id"],
        category,
        query=query,
        severity=severity,
        entity=entity,
        page=page,
        per_page=per_page,
    )
    if result is None:
        abort(404)
    return jsonify(result)


@bp.get("/events/<int:event_id>/imports")
def event_imports(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    query = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "all")
    if status not in ("all",) + IMPORT_HISTORY_STATUSES:
        status = "all"
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = request.args.get("per_page", default=10, type=int)
    if per_page not in (10, 25, 50):
        per_page = 10
    sort = request.args.get("sort", "created_at")
    if sort not in ("batch_id", "created_at", "activated_at", "status"):
        sort = "created_at"
    direction = request.args.get("direction", "desc")
    if direction not in ("asc", "desc"):
        direction = "desc"
    history = import_history(
        db,
        event_id,
        query=query,
        status=status,
        page=page,
        per_page=per_page,
        sort=sort,
        direction=direction,
    )
    selected_id = request.args.get("batch", type=int)
    selected = None
    files = []
    issue_counts = []
    issue_totals = {"error": 0, "warning": 0}
    if selected_id:
        selected = db.execute(
            "SELECT * FROM import_batches WHERE id = ? AND event_id = ?",
            (selected_id, event_id),
        ).fetchone()
        if not selected:
            abort(404)
    else:
        selected = db.execute(
            """
            SELECT * FROM import_batches
            WHERE event_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (event_id,),
        ).fetchone()
    if selected:
        files = db.execute(
            """
            SELECT * FROM import_files WHERE batch_id = ?
            ORDER BY CASE export_type
                WHEN 'tickets' THEN 1 WHEN 'buyers' THEN 2 ELSE 3 END
            """,
            (selected["id"],),
        ).fetchall()
        issue_counts = db.execute(
            """
            SELECT severity, category, COUNT(*) count
            FROM validation_issues WHERE batch_id = ?
            GROUP BY severity, category ORDER BY severity, count DESC
            """,
            (selected["id"],),
        ).fetchall()
        for issue in issue_counts:
            issue_totals[issue["severity"]] += issue["count"]
    return render_template(
        "imports.html",
        event=event,
        active_batch=active_batch(db, event_id),
        history=history,
        history_statuses=IMPORT_HISTORY_STATUSES,
        selected=selected,
        files=files,
        issue_counts=issue_counts,
        issue_totals=issue_totals,
    )


@bp.post("/events/<int:event_id>/imports/validate")
def validate_import(event_id):
    get_event_or_404(event_id)
    required = ("tickets", "buyers", "registrants")
    uploads = {slot: request.files.get(slot) for slot in required}
    if any(not upload or not upload.filename for upload in uploads.values()):
        flash("All three required exports must be selected.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id))

    try:
        staged = stage_upload_set(uploads, current_app.config["STAGING_DIR"])
        validation = validate_batch(staged)
        batch_id = store_validation(get_db(), validation, event_id)
    except Exception:
        current_app.logger.exception("Import validation failed without logging CSV contents.")
        flash("The import could not be validated. This event's active dashboard was not changed.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id))

    if validation.valid:
        flash("All three exports are valid. Review the summary, then process the batch.", "success")
    else:
        flash("Validation found blocking errors. The batch cannot be processed.", "error")
    return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))


@bp.post("/events/<int:event_id>/imports/<int:batch_id>/process")
def process_import(event_id, batch_id):
    get_event_or_404(event_id)
    db = get_db()
    batch = db.execute(
        "SELECT id FROM import_batches WHERE id = ? AND event_id = ?", (batch_id, event_id)
    ).fetchone()
    if not batch:
        abort(404)
    try:
        process_batch(db, batch_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))
    except Exception:
        current_app.logger.exception("Import processing failed without logging CSV contents.")
        flash("Processing failed. This event's previous active dataset remains active.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))

    flash("Import processed successfully and is now this event's active dataset.", "success")
    return redirect(url_for("dashboard.event_overview", event_id=event_id))


@bp.get("/satellites")
@bp.get("/data-quality")
@bp.get("/imports")
def legacy_workspace_redirects():
    return redirect(url_for("dashboard.events"))


@bp.app_template_filter("number")
def number_filter(value):
    return "{:,.0f}".format(value or 0)


@bp.app_template_filter("percent")
def percent_filter(value):
    return "{:.1f}%".format(value or 0)


@bp.app_template_filter("datetime_short")
def datetime_short_filter(value):
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")
