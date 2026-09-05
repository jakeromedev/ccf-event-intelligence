import hmac
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path
from time import perf_counter

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .auth import (
    admin_required,
    can_edit_attestation_verification,
    can_edit_registrant_remarks,
    can_view_admin_tables,
    can_view_registrations,
    event_mutation_required,
    satellite_settings_management_required,
)
from .analytics import AnalyticsFilterError, compare_events, event_analytics, historical_trends
from .aggregation import (
    active_batch,
    canonical_satellite_metrics,
    curated_registrant_detail,
    curation_quality,
    data_quality,
    data_quality_issue_instances,
    event_dashboard_metrics,
    event_summaries,
    overview_registrants,
    satellite_curation_detail,
    satellite_registrants,
)
from .admin_tables import (
    AdminTableQueryError,
    DATASET_LABELS,
    admin_table_data,
    event_batches,
    registration_sources,
    resolve_batch_scope,
)
from .db import get_db
from .import_history import IMPORT_HISTORY_STATUSES, import_history
from .importer import activate_batch, process_batch, stage_upload_set, store_validation, validate_batch
from .registrations import (
    create_registrant_remark,
    list_registrant_remarks,
    registrations_data,
    resolve_registrant_remark,
    update_attestation_verification,
)
from .registrant_satellite_assignments import (
    RegistrantSatelliteAssignmentError,
    reset_manual_satellite_assignment,
    set_manual_satellite_assignment,
)
from .satellite_datasets import (
    create_satellite_dataset,
    delete_satellite_dataset,
    update_satellite_dataset,
    validate_satellite_dataset_form,
)
from .satellite_settings import (
    SatelliteSettingsValidationError,
    confirm_bulk_hubs,
    confirm_bulk_satellites,
    create_hub,
    create_satellite,
    review_bulk_hubs,
    review_bulk_satellites,
    satellite_settings_hierarchy,
    update_hub,
    update_satellite,
)
from .satellite_settings_registrants import event_settings_registrants
from .satellite_target_categories import (
    SatelliteTargetCategoryValidationError,
    ensure_event_satellite_target_categories,
    replace_satellite_target_memberships,
    satellite_target_settings,
    update_satellite_target_values,
    validate_satellite_target_memberships,
    validate_satellite_target_values,
)
from .satellite_sync import (
    ALREADY_SYNCED,
    MANUAL_PROTECTED,
    READY_TO_SYNC,
    SYNC_STATUSES,
    SatelliteSyncAnalysisError,
    analyze_event_satellite_sync,
    execute_event_satellite_sync,
)
from .time_utils import format_operational_datetime
from .url_safety import safe_internal_path


bp = Blueprint("dashboard", __name__)


def can_access_admin_tables():
    """Use the host application's authorization hook when one is configured."""
    if not current_app.config.get("ADMIN_TABLES_ENABLED", True):
        return False
    if not current_app.config.get("AUTHENTICATION_DISABLED", False):
        if not can_view_admin_tables():
            return False
    authorizer = current_app.config.get("ADMIN_TABLES_AUTHORIZER")
    return True if authorizer is None else bool(authorizer(request))


def admin_tables_access_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if not can_access_admin_tables():
            abort(403)
        return view(*args, **kwargs)

    return protected


def can_access_registrations():
    """Allow only explicitly authorized operational registration users."""
    return can_view_registrations()


def registrations_access_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if not can_access_registrations():
            abort(403)
        return view(*args, **kwargs)

    return protected


def get_event_or_404(event_id):
    event = get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        abort(404)
    return event


def get_satellite_dataset_or_404(event_id, dataset_id):
    dataset = get_db().execute(
        "SELECT * FROM satellite_datasets WHERE id = ? AND event_id = ?",
        (dataset_id, event_id),
    ).fetchone()
    if not dataset:
        abort(404)
    return dataset


def _satellite_dataset_redirect(event_id, dataset_id=None):
    parameters = {"satellite_targets": 1}
    if dataset_id is not None:
        parameters["edit_dataset"] = dataset_id
    return redirect(url_for("dashboard.event_overview", event_id=event_id, **parameters))


def _remove_staged_batch_files(staged_paths):
    """Remove only batch files contained by the configured staging directory."""
    staging_root = Path(current_app.config["STAGING_DIR"]).resolve()
    parent_directories = set()
    for stored_path in staged_paths:
        candidate = Path(stored_path).resolve()
        try:
            candidate.relative_to(staging_root)
        except ValueError:
            current_app.logger.warning(
                "staged_file_cleanup_refused",
                extra={"event": "staged_file_cleanup_refused", "reason": "outside_staging_root"},
            )
            continue
        try:
            candidate.unlink(missing_ok=True)
            parent_directories.add(candidate.parent)
        except OSError:
            current_app.logger.error(
                "staged_file_cleanup_failed",
                extra={"event": "staged_file_cleanup_failed", "error_type": "OSError"},
            )
    for directory in sorted(parent_directories, key=lambda path: len(path.parts), reverse=True):
        if directory == staging_root:
            continue
        try:
            directory.rmdir()
        except OSError:
            pass


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
    ensure_event_satellite_target_categories(db, cursor.lastrowid)
    db.commit()
    flash("Event created. Upload the three required exports to build its dashboard.", "success")
    return redirect(url_for("dashboard.event_overview", event_id=cursor.lastrowid))


@bp.get("/events/<int:event_id>")
def event_overview(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    dashboard = event_dashboard_metrics(db, event_id)
    return render_template(
        "overview.html",
        event=event,
        active_batch=batch,
        dashboard=dashboard,
        metrics=dashboard["overview"],
        profile=dashboard["participant_profile"],
    )


@bp.get("/events/<int:event_id>/dashboard")
def event_dashboard_api(event_id):
    dashboard = event_dashboard_metrics(get_db(), event_id)
    if dashboard is None:
        abort(404)
    return jsonify(dashboard)


def _analytics_threshold():
    return current_app.config["ANALYTICS_MIN_GROUP_SIZE"]


def _analytics_filters():
    return {
        key: request.args.get(key, "")
        for key in (
            "gender",
            "life_stage",
            "age_group",
            "payment_status",
            "payment_method",
            "occupation",
            "dgroup",
            "home_area",
            "check_in",
            "satellite",
            "satellite_dataset",
        )
        if request.args.get(key)
    }


@bp.get("/events/<int:event_id>/analytics")
def event_analytics_page(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    try:
        analytics = event_analytics(
            db, event_id, _analytics_filters(), _analytics_threshold()
        )
    except AnalyticsFilterError as error:
        abort(400, str(error))
    removal_urls = {}
    for dimension in analytics["filters"]:
        remaining = dict(analytics["filters"])
        remaining.pop(dimension)
        removal_urls[dimension] = url_for(
            "dashboard.event_analytics_page", event_id=event_id, **remaining
        )
    return render_template(
        "analytics.html",
        event=event,
        active_batch=active_batch(db, event_id),
        analytics=analytics,
        trends=historical_trends(db, event_id, _analytics_threshold()),
        removal_urls=removal_urls,
    )


@bp.get("/api/events/<int:event_id>/analytics")
def event_analytics_api(event_id):
    try:
        analytics = event_analytics(
            get_db(), event_id, _analytics_filters(), _analytics_threshold()
        )
    except AnalyticsFilterError as error:
        return jsonify({"status": "error", "message": str(error)}), 400
    if analytics is None:
        abort(404)
    return jsonify(analytics)


@bp.get("/api/events/<int:event_id>/analytics/trends")
def event_analytics_trends_api(event_id):
    trends = historical_trends(get_db(), event_id, _analytics_threshold())
    if trends is None:
        abort(404)
    return jsonify(trends)


def _comparison_event_ids():
    raw = request.args.get("events", "")
    try:
        return [int(value) for value in raw.split(",") if value.strip()]
    except ValueError as error:
        raise AnalyticsFilterError("Event selections must be numeric IDs.") from error


@bp.get("/analytics/compare")
def analytics_compare_page():
    db = get_db()
    try:
        selected = _comparison_event_ids()
    except AnalyticsFilterError as exception:
        selected = []
        comparison_error = str(exception)
    else:
        comparison_error = None
    comparison = None
    if selected:
        try:
            comparison = compare_events(db, selected, _analytics_threshold())
        except AnalyticsFilterError as exception:
            comparison_error = str(exception)
    events_list = db.execute("SELECT id, name FROM events ORDER BY LOWER(name), id").fetchall()
    return render_template(
        "analytics_compare.html",
        event=None,
        active_batch=None,
        events=events_list,
        selected=selected,
        comparison=comparison,
        comparison_error=comparison_error,
    ), 400 if comparison_error else 200


@bp.get("/api/analytics/compare")
def analytics_compare_api():
    try:
        comparison = compare_events(
            get_db(), _comparison_event_ids(), _analytics_threshold()
        )
    except AnalyticsFilterError as error:
        return jsonify({"status": "error", "message": str(error)}), 400
    return jsonify(comparison)


@bp.post("/events/<int:event_id>/settings")
@event_mutation_required
def update_event_settings(event_id):
    event = get_event_or_404(event_id)
    event_date = (request.form.get("event_date") or "").strip()
    target_raw = (request.form.get("participant_target") or "").strip()

    if event_date:
        try:
            parsed_date = datetime.strptime(event_date, "%Y-%m-%d").date()
            if parsed_date.isoformat() != event_date:
                raise ValueError
        except ValueError:
            flash("Event Date must be a valid date.", "error")
            return redirect(url_for("dashboard.event_overview", event_id=event_id) + "#event-settings")

    participant_target = None
    if target_raw:
        try:
            participant_target = int(target_raw)
        except ValueError:
            participant_target = -1
        if participant_target < 0:
            flash("Participant Target must be a non-negative whole number.", "error")
            return redirect(url_for("dashboard.event_overview", event_id=event_id) + "#event-settings")
        if participant_target > 1_000_000_000:
            flash("Participant Target must be 1,000,000,000 or fewer.", "error")
            return redirect(url_for("dashboard.event_overview", event_id=event_id) + "#event-settings")

    db = get_db()
    db.execute(
        """
        UPDATE events
        SET event_date = ?, participant_target = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (parsed_date if event_date else None, participant_target, event["id"]),
    )
    db.commit()
    flash("Event settings saved. Dashboard metrics have been refreshed.", "success")
    return redirect(url_for("dashboard.event_overview", event_id=event_id) + "#event-settings")


@bp.post("/events/<int:event_id>/satellite-datasets")
@event_mutation_required
def create_event_satellite_dataset(event_id):
    get_event_or_404(event_id)
    db = get_db()
    values, errors = validate_satellite_dataset_form(db, event_id, request.form)
    if errors:
        flash(" ".join(errors), "error")
        return _satellite_dataset_redirect(event_id)
    try:
        dataset_id = create_satellite_dataset(db, event_id, values)
        db.commit()
    except IntegrityError:
        db.rollback()
        flash("A Satellite Dataset with that name already exists for this Event.", "error")
        return _satellite_dataset_redirect(event_id)
    flash("Satellite Dataset created.", "success")
    return _satellite_dataset_redirect(event_id, dataset_id)


@bp.post("/events/<int:event_id>/satellite-datasets/<int:dataset_id>")
@event_mutation_required
def update_event_satellite_dataset(event_id, dataset_id):
    get_event_or_404(event_id)
    get_satellite_dataset_or_404(event_id, dataset_id)
    db = get_db()
    values, errors = validate_satellite_dataset_form(
        db, event_id, request.form, dataset_id=dataset_id
    )
    if errors:
        flash(" ".join(errors), "error")
        return _satellite_dataset_redirect(event_id, dataset_id)
    try:
        update_satellite_dataset(db, event_id, dataset_id, values)
        db.commit()
    except IntegrityError:
        db.rollback()
        flash("A Satellite Dataset with that name already exists for this Event.", "error")
        return _satellite_dataset_redirect(event_id, dataset_id)
    flash("Satellite Dataset updated.", "success")
    return _satellite_dataset_redirect(event_id, dataset_id)


@bp.post("/events/<int:event_id>/satellite-datasets/<int:dataset_id>/delete")
@event_mutation_required
def delete_event_satellite_dataset(event_id, dataset_id):
    get_event_or_404(event_id)
    dataset = get_satellite_dataset_or_404(event_id, dataset_id)
    if request.form.get("confirm_delete") != "yes":
        flash("Confirm deletion before removing the Satellite Dataset.", "error")
        return _satellite_dataset_redirect(event_id, dataset_id)
    db = get_db()
    delete_satellite_dataset(db, event_id, dataset_id)
    db.commit()
    flash("Satellite Dataset ‘{}’ deleted.".format(dataset["name"]), "success")
    return _satellite_dataset_redirect(event_id)


@bp.get("/events/<int:event_id>/overview/registrants")
def event_overview_registrants(event_id):
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    if not batch:
        return jsonify({"registrants": []})
    return jsonify({"registrants": overview_registrants(db, batch["id"])})


@bp.get("/events/<int:event_id>/registrations")
@registrations_access_required
def event_registrations(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    try:
        selected_batch = resolve_batch_scope(
            db, event_id, request.args.get("batch"), batch["id"] if batch else None
        )
    except AdminTableQueryError:
        abort(404)
    return render_template(
        "registrations.html",
        event=event,
        active_batch=batch,
        selected_batch=selected_batch,
        batches=event_batches(db, event_id),
        attestation_edit_allowed=can_edit_attestation_verification(),
        remarks_edit_allowed=can_edit_registrant_remarks(),
    )


@bp.get("/events/<int:event_id>/registrations/data")
@registrations_access_required
def event_registrations_data(event_id):
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    try:
        result = registrations_data(
            db, event_id, batch["id"] if batch else None, request.args
        )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@bp.patch(
    "/events/<int:event_id>/registrations/<int:registrant_id>/attestation"
)
@registrations_access_required
def update_registration_attestation(event_id, registrant_id):
    if not can_edit_attestation_verification():
        abort(403)
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON request body is required."}), 400
    try:
        result = update_attestation_verification(
            db,
            event_id,
            batch["id"] if batch else None,
            registrant_id,
            request.args.get("batch"),
            payload.get("status"),
            current_user.id,
        )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        abort(404)
    current_app.logger.info(
        "attestation_verification_updated",
        extra={
            "event": "attestation_verification_updated",
            "event_id": event_id,
            "batch_id": result["batch_id"],
            "registrant_id": registrant_id,
            "user_id": current_user.id,
            "status": result["status"],
        },
    )
    return jsonify(result)


@bp.route(
    "/events/<int:event_id>/registrations/<int:registrant_id>/remarks",
    methods=("GET", "POST"),
)
@registrations_access_required
def registration_remarks(event_id, registrant_id):
    if request.method == "POST" and not can_edit_registrant_remarks():
        abort(403)
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    try:
        if request.method == "GET":
            result = list_registrant_remarks(
                db,
                event_id,
                batch["id"] if batch else None,
                registrant_id,
                request.args.get("batch"),
            )
        else:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "A JSON request body is required."}), 400
            if set(payload) != {"remark"}:
                return jsonify({"error": "Only remark text may be supplied."}), 400
            result = create_registrant_remark(
                db,
                event_id,
                batch["id"] if batch else None,
                registrant_id,
                request.args.get("batch"),
                payload.get("remark"),
                current_user.id,
            )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        abort(404)
    if request.method == "POST":
        current_app.logger.info(
            "registrant_remark_created",
            extra={
                "event": "registrant_remark_created",
                "event_id": event_id,
                "batch_id": result["batch_id"],
                "registrant_id": registrant_id,
                "remark_id": result["remark"]["id"],
                "user_id": current_user.id,
            },
        )
        return jsonify(result), 201
    return jsonify(result)


@bp.patch(
    "/events/<int:event_id>/registrations/<int:registrant_id>/remarks/"
    "<int:remark_id>"
)
@registrations_access_required
def resolve_registration_remark(event_id, registrant_id, remark_id):
    if not can_edit_registrant_remarks():
        abort(403)
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON request body is required."}), 400
    if set(payload) != {"status"}:
        return jsonify({"error": "Only remark status may be supplied."}), 400
    try:
        result = resolve_registrant_remark(
            db,
            event_id,
            batch["id"] if batch else None,
            registrant_id,
            request.args.get("batch"),
            remark_id,
            payload.get("status"),
            current_user.id,
        )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        abort(404)
    current_app.logger.info(
        "registrant_remark_resolved",
        extra={
            "event": "registrant_remark_resolved",
            "event_id": event_id,
            "batch_id": result["batch_id"],
            "registrant_id": registrant_id,
            "remark_id": remark_id,
            "user_id": current_user.id,
        },
    )
    return jsonify(result)


@bp.get("/events/<int:event_id>/admin-tables/<dataset>")
@admin_tables_access_required
def event_admin_table(event_id, dataset):
    if dataset not in ("registrants", "tickets", "buyers"):
        abort(404)
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    view = request.args.get("view", "all")
    if dataset != "registrants" or view not in ("all", "curated"):
        view = "all"
    selected_dataset = "curated" if dataset == "registrants" and view == "curated" else dataset
    try:
        selected_batch = resolve_batch_scope(
            db, event_id, request.args.get("batch"), batch["id"] if batch else None
        )
    except AdminTableQueryError:
        abort(404)
    return render_template(
        "admin_table.html",
        event=event,
        active_batch=batch,
        dataset=dataset,
        dataset_label=DATASET_LABELS[dataset],
        selected_dataset=selected_dataset,
        selected_view=view,
        selected_batch=selected_batch,
        batches=event_batches(db, event_id),
    )


@bp.get("/events/<int:event_id>/admin-tables/<dataset>/data")
@admin_tables_access_required
def event_admin_table_data(event_id, dataset):
    if dataset not in ("registrants", "tickets", "buyers", "curated"):
        abort(404)
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    try:
        result = admin_table_data(
            db, dataset, event_id, batch["id"] if batch else None, request.args
        )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@bp.get("/events/<int:event_id>/admin-tables/registrants/curated/<int:curated_id>/sources")
@admin_tables_access_required
def event_admin_registration_sources(event_id, curated_id):
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    try:
        batch_scope = resolve_batch_scope(
            db, event_id, request.args.get("batch"), batch["id"] if batch else None
        )
    except AdminTableQueryError as exc:
        return jsonify({"error": str(exc)}), 400
    result = registration_sources(db, event_id, curated_id, batch_scope)
    if result is None:
        abort(404)
    return jsonify(result)


@bp.get("/events/<int:event_id>/satellites")
def event_satellites(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    query = (request.args.get("q") or "").strip()[:100]
    group_id = request.args.get("group", type=int)
    hub_id = request.args.get("hub", type=int)
    satellite_id = request.args.get("satellite", type=int)
    link_status = request.args.get("link_status", "all")
    sort = request.args.get("sort", "registrants")
    direction = request.args.get("direction", "desc")
    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=10, type=int) or 10
    metrics = (
        canonical_satellite_metrics(
            db,
            batch["id"],
            query=query,
            group_id=group_id,
            hub_id=hub_id,
            satellite_id=satellite_id,
            link_status=link_status,
            sort=sort,
            direction=direction,
            page=page,
            per_page=per_page,
        )
        if batch
        else None
    )
    return render_template(
        "satellites.html",
        event=event,
        active_batch=batch,
        metrics=metrics,
        query=query,
        satellite_return_url=request.full_path.rstrip("?") + "#satellite-ranking-table",
    )


def _render_satellite_settings(
    event_id=None, bulk_review=None, sync_review=None, status=200
):
    db = get_db()
    event = get_event_or_404(event_id) if event_id is not None else None
    batch = active_batch(db, event_id) if event is not None else None
    search_scope = _satellite_settings_search_scope()
    filters = _satellite_settings_filters() if event is not None else {}
    registrants = (
        event_settings_registrants(
            db, event_id, search_scope=search_scope, **filters
        )
        if event is not None
        else None
    )
    return render_template(
        "satellite_settings.html",
        event=event,
        active_batch=batch,
        hierarchy=satellite_settings_hierarchy(db),
        registrants=registrants,
        target_settings=(
            satellite_target_settings(db, event_id) if event is not None else None
        ),
        settings_filters=filters,
        settings_search_scope=search_scope,
        settings_view=(request.args.get("view") if event is not None else "directory")
        if request.args.get("view") in ("directory", "registrants", "targets")
        else "directory",
        bulk_review=bulk_review,
        sync_review=sync_review,
    ), status


def _satellite_settings_search_scope():
    default_scope = (
        "registrant" if request.args.get("view") == "registrants" else "directory"
    )
    search_scope = request.args.get("search_scope", default_scope)
    return search_scope if search_scope in ("directory", "registrant") else "directory"


def _satellite_settings_filters():
    return {
        "query": (request.args.get("q") or "").strip()[:200],
        "group_code": (request.args.get("group") or "").strip()[:80],
        "hub_id": request.args.get("hub_id", type=int),
        "satellite_id": request.args.get("satellite_id", type=int),
        "sync_status": (request.args.get("sync_status") or "all").strip()[:80],
        "sort": (request.args.get("sort") or "participant").strip()[:40],
        "direction": (request.args.get("direction") or "asc").strip()[:8],
        "page": request.args.get("page", default=1, type=int),
        "per_page": request.args.get("per_page", default=25, type=int),
    }


@bp.get("/satellites/settings")
@satellite_settings_management_required
def satellite_settings():
    event_id = request.args.get("event_id", type=int)
    sync_review = None
    if event_id is not None and request.args.get("sync_complete") == "1":
        completion = session.pop("satellite_sync_result", None)
        if completion and completion.get("event_id") == event_id:
            plan = analyze_event_satellite_sync(get_db(), event_id)
            sync_review = _prepare_sync_review(plan, completion=completion)
    return _render_satellite_settings(event_id, sync_review=sync_review)


@bp.get("/satellites/settings/registrants")
@satellite_settings_management_required
def satellite_settings_registrants():
    event_id = request.args.get("event_id", type=int)
    if event_id is None:
        abort(400)
    get_event_or_404(event_id)
    payload = event_settings_registrants(
        get_db(),
        event_id,
        search_scope=_satellite_settings_search_scope(),
        **_satellite_settings_filters(),
    )
    requested_satellite = request.args.get("satellite_id", type=int)
    if requested_satellite is not None and not any(
        option["id"] == requested_satellite
        for option in payload["options"]["satellites"]
    ):
        abort(404)
    return jsonify(payload)


@bp.post("/events/<int:event_id>/satellite-target-categories/memberships")
@satellite_settings_management_required
@event_mutation_required
def update_satellite_target_category_memberships(event_id):
    get_event_or_404(event_id)
    db = get_db()
    try:
        memberships = validate_satellite_target_memberships(
            db, event_id, request.form.getlist("category_assignments")
        )
        replace_satellite_target_memberships(db, event_id, memberships)
        db.commit()
    except SatelliteTargetCategoryValidationError as exc:
        db.rollback()
        flash("{} No changes were made.".format(exc), "error")
        return redirect(
            url_for("dashboard.satellite_settings", event_id=event_id, view="targets")
            + "#dashboard-target-satellites"
        )
    except (IntegrityError, SQLAlchemyError):
        db.rollback()
        current_app.logger.exception(
            "Dashboard Target Satellite membership update failed."
        )
        flash(
            "Dashboard Target Satellites could not be saved. No changes were made.",
            "error",
        )
        return redirect(
            url_for("dashboard.satellite_settings", event_id=event_id, view="targets")
            + "#dashboard-target-satellites"
        )

    current_app.logger.info(
        "satellite_target_category_memberships_updated",
        extra={
            "event": "satellite_target_category_memberships_updated",
            "event_id": event_id,
            "membership_count": len(memberships),
            "user_id": getattr(current_user, "id", None),
        },
    )
    flash("Dashboard Target Satellites saved.", "success")
    return redirect(
        url_for("dashboard.satellite_settings", event_id=event_id, view="targets")
        + "#dashboard-target-satellites"
    )


@bp.post("/events/<int:event_id>/satellite-target-categories/targets")
@event_mutation_required
def update_satellite_target_category_targets(event_id):
    get_event_or_404(event_id)
    db = get_db()
    try:
        values = validate_satellite_target_values(request.form)
        update_satellite_target_values(db, event_id, values)
        db.commit()
    except SatelliteTargetCategoryValidationError as exc:
        db.rollback()
        flash("{} No changes were made.".format(exc), "error")
        return redirect(
            url_for("dashboard.event_overview", event_id=event_id)
            + "#satellite-targets"
        )
    except SQLAlchemyError:
        db.rollback()
        current_app.logger.exception("Dashboard Satellite Targets update failed.")
        flash(
            "Dashboard Satellite Targets could not be saved. No changes were made.",
            "error",
        )
        return redirect(
            url_for("dashboard.event_overview", event_id=event_id)
            + "#satellite-targets"
        )

    current_app.logger.info(
        "satellite_target_category_targets_updated",
        extra={
            "event": "satellite_target_category_targets_updated",
            "event_id": event_id,
            "user_id": getattr(current_user, "id", None),
        },
    )
    flash("Dashboard Satellite Targets saved.", "success")
    return redirect(
        url_for("dashboard.event_overview", event_id=event_id)
        + "#satellite-targets"
    )


@bp.post(
    "/satellites/settings/registrants/"
    "<int:attestation_participant_id>/satellite"
)
@satellite_settings_management_required
def update_registrant_satellite_assignment(attestation_participant_id):
    event_id = request.form.get("event_id", type=int)
    if event_id is None:
        abort(400)
    get_event_or_404(event_id)
    db = get_db()
    try:
        result = set_manual_satellite_assignment(
            db,
            event_id,
            attestation_participant_id,
            request.form.get("directory_id"),
            updated_by_user_id=getattr(current_user, "id", None),
        )
        db.commit()
    except RegistrantSatelliteAssignmentError as exc:
        db.rollback()
        flash(str(exc), "error")
        return redirect(
            safe_internal_path(request.form.get("return_to"))
            or url_for(
                "dashboard.satellite_settings",
                event_id=event_id,
                view="registrants",
            )
        )
    except IntegrityError:
        db.rollback()
        flash(
            "The registrant or Satellite changed while this assignment was being saved.",
            "error",
        )
        return redirect(
            safe_internal_path(request.form.get("return_to"))
            or url_for(
                "dashboard.satellite_settings",
                event_id=event_id,
                view="registrants",
            )
        )

    current_app.logger.info(
        "registrant_satellite_manually_assigned",
        extra={
            "event": "registrant_satellite_manually_assigned",
            "event_id": event_id,
            "attestation_participant_id": attestation_participant_id,
            "directory_id": result["directory_id"],
            "user_id": getattr(current_user, "id", None),
        },
    )
    flash(
        "{} is now the manually assigned Satellite.".format(
            result["satellite_name"]
        ),
        "success",
    )
    return redirect(
        safe_internal_path(request.form.get("return_to"))
        or url_for(
            "dashboard.satellite_settings",
            event_id=event_id,
            view="registrants",
        )
    )


@bp.post(
    "/satellites/settings/registrants/"
    "<int:attestation_participant_id>/satellite/reset"
)
@satellite_settings_management_required
def reset_registrant_satellite_assignment(attestation_participant_id):
    event_id = request.form.get("event_id", type=int)
    if event_id is None:
        abort(400)
    get_event_or_404(event_id)
    db = get_db()
    try:
        result = reset_manual_satellite_assignment(
            db,
            event_id,
            attestation_participant_id,
            updated_by_user_id=getattr(current_user, "id", None),
        )
        db.commit()
    except RegistrantSatelliteAssignmentError as exc:
        db.rollback()
        flash(str(exc), "error")
        return redirect(
            safe_internal_path(request.form.get("return_to"))
            or url_for(
                "dashboard.satellite_settings",
                event_id=event_id,
                view="registrants",
            )
        )
    except IntegrityError:
        db.rollback()
        flash("The assignment changed while the reset was being saved.", "error")
        return redirect(
            safe_internal_path(request.form.get("return_to"))
            or url_for(
                "dashboard.satellite_settings",
                event_id=event_id,
                view="registrants",
            )
        )

    current_app.logger.info(
        "registrant_satellite_manual_assignment_reset",
        extra={
            "event": "registrant_satellite_manual_assignment_reset",
            "event_id": event_id,
            "attestation_participant_id": attestation_participant_id,
            "directory_id": result["directory_id"],
            "user_id": getattr(current_user, "id", None),
            "changed": result["changed"],
        },
    )
    if result["changed"]:
        flash("The manual Satellite override was reset.", "success")
    else:
        flash("The manual Satellite override was already reset.", "success")
    return redirect(
        safe_internal_path(request.form.get("return_to"))
        or url_for(
            "dashboard.satellite_settings",
            event_id=event_id,
            view="registrants",
        )
    )


def _prepare_sync_review(plan, confirmation_token=None, completion=None):
    failure_statuses = set(SYNC_STATUSES) - {
        READY_TO_SYNC,
        ALREADY_SYNCED,
        MANUAL_PROTECTED,
    }
    failures = [
        registration
        for registration in plan["registrations"]
        if registration["status"] in failure_statuses
    ]
    plan["ready_count"] = plan["counts"][READY_TO_SYNC]
    plan["already_synced_count"] = plan["counts"][ALREADY_SYNCED]
    plan["manual_protected_count"] = sum(
        registration["status"] == MANUAL_PROTECTED
        for registration in plan["registrations"]
    )
    plan["not_synced_count"] = sum(
        count
        for status, count in plan["counts"].items()
        if status in failure_statuses
    )
    plan["failures"] = failures
    plan["reason_counts"] = [
        {
            "reason": status,
            "count": sum(1 for item in failures if item["status"] == status),
        }
        for status in SYNC_STATUSES
        if status in failure_statuses
        and any(item["status"] == status for item in failures)
    ]
    plan["confirmation_token"] = confirmation_token
    plan["completion"] = completion
    return plan


@bp.post("/satellites/settings/sync/review")
@satellite_settings_management_required
def review_registration_satellites():
    event_id = request.form.get("event_id", type=int)
    if event_id is None:
        abort(400)
    get_event_or_404(event_id)
    plan = analyze_event_satellite_sync(get_db(), event_id)
    confirmation_token = secrets.token_urlsafe(32)
    session["satellite_sync_confirmation"] = {
        "event_id": event_id,
        "token": confirmation_token,
    }
    return _render_satellite_settings(
        event_id,
        sync_review=_prepare_sync_review(
            plan, confirmation_token=confirmation_token
        ),
    )


@bp.post("/satellites/settings/sync/confirm")
@satellite_settings_management_required
def confirm_registration_satellites():
    event_id = request.form.get("event_id", type=int)
    if event_id is None:
        abort(400)
    get_event_or_404(event_id)
    pending = session.pop("satellite_sync_confirmation", None)
    supplied_token = request.form.get("confirmation_token", "")
    valid_confirmation = (
        pending
        and pending.get("event_id") == event_id
        and supplied_token
        and hmac.compare_digest(str(pending.get("token", "")), supplied_token)
    )
    if not valid_confirmation:
        flash(
            "This synchronization review is missing, expired, or was already used. Review the registrations again.",
            "error",
        )
        return _satellite_settings_redirect()
    db = get_db()
    try:
        result = execute_event_satellite_sync(db, event_id)
        db.commit()
    except SatelliteSyncAnalysisError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect()
    except SQLAlchemyError:
        db.rollback()
        current_app.logger.exception("Registration Satellite synchronization failed.")
        flash(
            "Registration Satellites could not be synchronized. No changes were saved.",
            "error",
        )
        return _satellite_settings_redirect()

    synchronized = result["synchronized_count"]
    already_synced = result["already_synced_count"]
    not_synced = result["not_synced_count"]
    session["satellite_sync_result"] = {
        "event_id": event_id,
        "synchronized_count": synchronized,
        "synchronized_registration_count": result["synchronized_registration_count"],
        "already_synced_count": already_synced,
        "not_synced_count": not_synced,
    }
    current_app.logger.info(
        "registration_satellite_sync_completed",
        extra={
            "event": "registration_satellite_sync_completed",
            "event_id": event_id,
            "user_id": getattr(current_user, "id", None),
            "matched_count": synchronized,
            "skipped_count": already_synced,
            "failed_count": not_synced,
        },
    )
    return _satellite_settings_redirect(sync_complete=1)


def _satellite_settings_redirect(anchor="", **parameters):
    event_id = request.form.get("event_id", type=int)
    location = url_for(
        "dashboard.satellite_settings", event_id=event_id, **parameters
    )
    return redirect(location + anchor)


@bp.post("/satellites/settings/hubs")
@satellite_settings_management_required
def create_satellite_hub():
    db = get_db()
    try:
        hub_id, name = create_hub(
            db, request.form.get("hub_group_id"), request.form.get("name")
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect("#hub-groups")
    except IntegrityError:
        db.rollback()
        flash("That Hub already exists in the selected Hub Group.", "error")
        return _satellite_settings_redirect("#hub-groups")
    flash("Hub ‘{}’ created.".format(name), "success")
    return _satellite_settings_redirect("#hub-{}".format(hub_id))


@bp.post("/satellites/settings/hubs/<int:hub_id>")
@satellite_settings_management_required
def update_satellite_hub(hub_id):
    db = get_db()
    try:
        name = update_hub(
            db,
            hub_id,
            request.form.get("hub_group_id"),
            request.form.get("name"),
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect("#hub-{}".format(hub_id))
    except IntegrityError:
        db.rollback()
        flash("That Hub already exists in the selected Hub Group.", "error")
        return _satellite_settings_redirect("#hub-{}".format(hub_id))
    flash("Hub ‘{}’ updated.".format(name), "success")
    return _satellite_settings_redirect("#hub-{}".format(hub_id))


@bp.post("/satellites/settings/satellites")
@satellite_settings_management_required
def create_satellite_directory_entry():
    db = get_db()
    hub_id = request.form.get("hub_id", type=int)
    try:
        satellite_id, name = create_satellite(
            db, hub_id, request.form.get("name")
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect(
            "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
        )
    except IntegrityError:
        db.rollback()
        flash("That Satellite already exists in the selected Hub.", "error")
        return _satellite_settings_redirect(
            "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
        )
    flash("Satellite ‘{}’ created.".format(name), "success")
    return _satellite_settings_redirect("#satellite-{}".format(satellite_id))


@bp.post("/satellites/settings/satellites/<int:satellite_id>")
@satellite_settings_management_required
def update_satellite_directory_entry(satellite_id):
    db = get_db()
    try:
        name = update_satellite(
            db,
            satellite_id,
            request.form.get("hub_id"),
            request.form.get("name"),
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect("#satellite-{}".format(satellite_id))
    except IntegrityError:
        db.rollback()
        flash("That Satellite already exists in the selected Hub.", "error")
        return _satellite_settings_redirect("#satellite-{}".format(satellite_id))
    flash("Satellite ‘{}’ updated.".format(name), "success")
    return _satellite_settings_redirect("#satellite-{}".format(satellite_id))


@bp.post("/satellites/settings/bulk/hubs/review")
@satellite_settings_management_required
def review_bulk_satellite_hubs():
    try:
        review = review_bulk_hubs(
            get_db(), request.form.get("hub_group_id"), request.form.get("values")
        )
    except SatelliteSettingsValidationError as exc:
        flash(str(exc), "error")
        return _satellite_settings_redirect("#hub-groups")
    return _render_satellite_settings(
        request.form.get("event_id", type=int), review
    )


@bp.post("/satellites/settings/bulk/hubs/confirm")
@satellite_settings_management_required
def confirm_bulk_satellite_hubs():
    db = get_db()
    try:
        created, duplicates, target_name = confirm_bulk_hubs(
            db,
            request.form.get("hub_group_id"),
            request.form.getlist("values"),
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect("#hub-groups")
    except IntegrityError:
        db.rollback()
        flash("Hubs changed during review. Review the pasted values again.", "error")
        return _satellite_settings_redirect("#hub-groups")
    flash(
        "Created {} {} in {}. Skipped {} {}.".format(
            created,
            "Hub" if created == 1 else "Hubs",
            target_name,
            duplicates,
            "duplicate" if duplicates == 1 else "duplicates",
        ),
        "success",
    )
    return _satellite_settings_redirect("#hub-groups")


@bp.post("/satellites/settings/bulk/satellites/review")
@satellite_settings_management_required
def review_bulk_satellite_entries():
    hub_id = request.form.get("hub_id", type=int)
    try:
        review = review_bulk_satellites(
            get_db(), hub_id, request.form.get("values")
        )
    except SatelliteSettingsValidationError as exc:
        flash(str(exc), "error")
        return _satellite_settings_redirect(
            "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
        )
    return _render_satellite_settings(
        request.form.get("event_id", type=int), review
    )


@bp.post("/satellites/settings/bulk/satellites/confirm")
@satellite_settings_management_required
def confirm_bulk_satellite_entries():
    db = get_db()
    hub_id = request.form.get("hub_id", type=int)
    try:
        created, duplicates, target_name = confirm_bulk_satellites(
            db, hub_id, request.form.getlist("values")
        )
        db.commit()
    except SatelliteSettingsValidationError as exc:
        db.rollback()
        flash(str(exc), "error")
        return _satellite_settings_redirect(
            "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
        )
    except IntegrityError:
        db.rollback()
        flash(
            "Satellites changed during review. Review the pasted values again.",
            "error",
        )
        return _satellite_settings_redirect(
            "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
        )
    flash(
        "Created {} {} in {}. Skipped {} {}.".format(
            created,
            "Satellite" if created == 1 else "Satellites",
            target_name,
            duplicates,
            "duplicate" if duplicates == 1 else "duplicates",
        ),
        "success",
    )
    return _satellite_settings_redirect(
        "#hub-{}".format(hub_id) if hub_id else "#hub-groups"
    )


@bp.get("/events/<int:event_id>/satellites/registrants")
def event_satellite_registrants(event_id):
    db = get_db()
    event = get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    satellite_id = request.args.get("satellite", type=int)
    satellite_name = (request.args.get("name") or "").strip()[:200]
    scope = request.args.get("scope", "")
    query = (request.args.get("q") or "").strip()[:100]
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = request.args.get("per_page", default=50, type=int)
    if per_page not in (25, 50, 100):
        per_page = 50
    return_to = safe_internal_path(request.args.get("return_to"))

    participant_data = None
    if batch:
        target = satellite_id or satellite_name
        if not target:
            abort(404)
        participant_data = satellite_registrants(
            db,
            batch["id"],
            target,
            scope,
            page=page,
            per_page=per_page,
            query=query,
        )
        if participant_data is None:
            abort(404)
    return render_template(
        "satellite_registrants.html",
        event=event,
        active_batch=batch,
        satellite=participant_data,
        satellite_return_url=return_to
        or url_for("dashboard.event_satellites", event_id=event_id)
        + "#satellite-ranking-table",
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
    curation_pages = {
        "duplicate_groups": max(
            request.args.get("duplicate_page", default=1, type=int) or 1, 1
        ),
        "incomplete_identity": max(
            request.args.get("incomplete_page", default=1, type=int) or 1, 1
        ),
        "satellites": max(
            request.args.get("satellite_page", default=1, type=int) or 1, 1
        ),
        "multi_satellite": max(
            request.args.get("multiple_page", default=1, type=int) or 1, 1
        ),
    }
    curation_data = (
        curation_quality(db, batch["id"], pages=curation_pages, per_page=10)
        if batch
        else None
    )
    return render_template(
        "data_quality.html",
        event=event,
        active_batch=batch,
        quality=quality_data,
        curation=curation_data,
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


@bp.get("/events/<int:event_id>/data-quality/curation/registrants/<int:curated_id>")
def event_curated_registrant_detail(event_id, curated_id):
    """Return one active-batch person's deduplication audit trail."""
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    if not batch:
        abort(404)
    result = curated_registrant_detail(db, batch["id"], curated_id)
    if result is None:
        abort(404)
    return jsonify(result)


@bp.get("/events/<int:event_id>/data-quality/curation/satellites/<int:satellite_id>")
def event_satellite_curation_detail(event_id, satellite_id):
    """Return normalized and source values for one active-batch satellite."""
    db = get_db()
    get_event_or_404(event_id)
    batch = active_batch(db, event_id)
    if not batch:
        abort(404)
    result = satellite_curation_detail(db, batch["id"], satellite_id)
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
        can_manage_import_batches=(
            current_user.is_authenticated and current_user.is_admin
        ),
    )


@bp.post("/events/<int:event_id>/imports/validate")
@event_mutation_required
def validate_import(event_id):
    get_event_or_404(event_id)
    required = ("tickets", "buyers", "registrants")
    uploads = {slot: request.files.get(slot) for slot in required}
    if any(not upload or not upload.filename for upload in uploads.values()):
        current_app.logger.warning(
            "import_validation_rejected",
            extra={
                "event": "import_validation_rejected",
                "event_id": event_id,
                "reason": "incomplete_export_set",
            },
        )
        flash("All three required exports must be selected.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id))

    started_at = perf_counter()
    try:
        staged = stage_upload_set(uploads, current_app.config["STAGING_DIR"])
        validation = validate_batch(staged)
        batch_id = store_validation(get_db(), validation, event_id)
    except Exception as error:
        current_app.logger.error(
            "import_validation_failed",
            extra={
                "event": "import_validation_failed",
                "event_id": event_id,
                "error_type": type(error).__name__,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        flash("The import could not be validated. This event's active dashboard was not changed.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id))

    current_app.logger.info(
        "import_validation_completed",
        extra={
            "event": "import_validation_completed",
            "event_id": event_id,
            "batch_id": batch_id,
            "valid": validation.valid,
            "row_count": sum(item.total_rows for item in validation.files.values()),
            "validation_error_count": sum(issue.severity == "error" for issue in validation.issues),
            "validation_warning_count": sum(issue.severity == "warning" for issue in validation.issues),
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )

    if validation.valid:
        flash("All three exports are valid. Review the summary, then process the batch.", "success")
    else:
        flash("Validation found blocking errors. The batch cannot be processed.", "error")
    return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))


@bp.post("/events/<int:event_id>/imports/<int:batch_id>/process")
@event_mutation_required
def process_import(event_id, batch_id):
    get_event_or_404(event_id)
    db = get_db()
    batch = db.execute(
        "SELECT id FROM import_batches WHERE id = ? AND event_id = ?", (batch_id, event_id)
    ).fetchone()
    if not batch:
        abort(404)
    started_at = perf_counter()
    try:
        process_batch(db, batch_id)
    except ValueError as exc:
        current_app.logger.warning(
            "import_processing_rejected",
            extra={
                "event": "import_processing_rejected",
                "event_id": event_id,
                "batch_id": batch_id,
                "reason": "invalid_batch_state",
            },
        )
        flash(str(exc), "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))
    except Exception as error:
        current_app.logger.error(
            "import_processing_failed",
            extra={
                "event": "import_processing_failed",
                "event_id": event_id,
                "batch_id": batch_id,
                "error_type": type(error).__name__,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        flash("Processing failed. This event's previous active dataset remains active.", "error")
        return redirect(url_for("dashboard.event_imports", event_id=event_id, batch=batch_id))

    counts = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM tickets WHERE batch_id = ?) tickets,
            (SELECT COUNT(*) FROM buyers WHERE batch_id = ?) buyers,
            (SELECT COUNT(*) FROM registrants WHERE batch_id = ?) registrants
        """,
        (batch_id, batch_id, batch_id),
    ).fetchone()
    current_app.logger.info(
        "import_processing_completed",
        extra={
            "event": "import_processing_completed",
            "event_id": event_id,
            "batch_id": batch_id,
            "ticket_rows": counts["tickets"],
            "buyer_rows": counts["buyers"],
            "registrant_rows": counts["registrants"],
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )

    flash("Import processed successfully and is now this event's active dataset.", "success")
    return redirect(url_for("dashboard.event_overview", event_id=event_id))


@bp.post("/events/<int:event_id>/imports/<int:batch_id>/activate")
@event_mutation_required
def activate_import(event_id, batch_id):
    get_event_or_404(event_id)
    db = get_db()
    batch = db.execute(
        "SELECT id FROM import_batches WHERE id = ? AND event_id = ?",
        (batch_id, event_id),
    ).fetchone()
    if not batch:
        abort(404)
    started_at = perf_counter()
    try:
        changed = activate_batch(db, event_id, batch_id)
    except ValueError as exc:
        current_app.logger.warning(
            "import_activation_rejected",
            extra={
                "event": "import_activation_rejected",
                "event_id": event_id,
                "batch_id": batch_id,
                "reason": "invalid_batch_state",
            },
        )
        flash(str(exc), "error")
    except Exception as error:
        current_app.logger.error(
            "import_activation_failed",
            extra={
                "event": "import_activation_failed",
                "event_id": event_id,
                "batch_id": batch_id,
                "error_type": type(error).__name__,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        flash("The import batch could not be activated. The current dataset was preserved.", "error")
    else:
        current_app.logger.info(
            "import_activation_completed",
            extra={
                "event": "import_activation_completed",
                "event_id": event_id,
                "batch_id": batch_id,
                "changed": changed,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        flash(
            "Batch #{} is already active.".format(batch_id)
            if not changed
            else "Batch #{} is now this Event's active dataset.".format(batch_id),
            "success",
        )
    return redirect(
        url_for("dashboard.event_imports", event_id=event_id, batch=batch_id)
        + "#import-history"
    )


@bp.post("/events/<int:event_id>/imports/<int:batch_id>/delete")
@admin_required
def delete_import(event_id, batch_id):
    get_event_or_404(event_id)
    db = get_db()
    batch = db.execute(
        "SELECT * FROM import_batches WHERE id = ? AND event_id = ?",
        (batch_id, event_id),
    ).fetchone()
    if not batch:
        abort(404)
    if batch["status"] == "active":
        flash("Activate another batch before deleting the active dataset.", "error")
        return redirect(
            url_for("dashboard.event_imports", event_id=event_id, batch=batch_id)
            + "#import-history"
        )
    if batch["status"] in ("processing", "validating"):
        flash("A batch cannot be deleted while it is being processed or validated.", "error")
        return redirect(
            url_for("dashboard.event_imports", event_id=event_id, batch=batch_id)
            + "#import-history"
        )

    staged_paths = [
        row["staged_path"]
        for row in db.execute(
            "SELECT staged_path FROM import_files WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        if row["staged_path"]
    ]
    try:
        db.execute(
            "DELETE FROM import_batches WHERE id = ? AND event_id = ?",
            (batch_id, event_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        current_app.logger.exception("Import batch deletion failed.")
        flash("Batch #{} could not be deleted.".format(batch_id), "error")
        return redirect(
            url_for("dashboard.event_imports", event_id=event_id, batch=batch_id)
            + "#import-history"
        )

    _remove_staged_batch_files(staged_paths)
    flash("Batch #{} and its stored data were deleted.".format(batch_id), "success")
    return redirect(url_for("dashboard.event_imports", event_id=event_id) + "#import-history")


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
    return format_operational_datetime(value)
