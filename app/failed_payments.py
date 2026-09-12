"""Failed-payment follow-up from the active Event export."""

import json
import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user

from .aggregation import active_batch
from .auth import CAPABILITY_VIEW_FAILED_PAYMENTS, has_capability
from .db import get_db
from .time_utils import format_operational_datetime, utc_now


bp = Blueprint("failed_payments", __name__)


def _text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _source(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _date(value):
    raw = _text(value)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        # Source exports use local Manila time when no offset is supplied.
        if result.tzinfo is not None:
            result = result.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
        return result
    except (TypeError, ValueError):
        for pattern in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p"):
            try:
                return datetime.strptime(raw, pattern)
            except ValueError:
                continue
        return None


def _contact(source, name):
    email = _text(source.get("Email Address")).casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        email = ""
    mobile = re.sub(r"\D", "", str(source.get("Mobile Number") or ""))
    if mobile.startswith("0063"):
        mobile = mobile[2:]
    if len(mobile) == 11 and mobile.startswith("09"):
        mobile = "63" + mobile[1:]
    elif len(mobile) == 10 and mobile.startswith("9"):
        mobile = "63" + mobile
    if not 10 <= len(mobile) <= 15:
        mobile = ""
    return {"name": _text(name).casefold(), "email": email, "mobile": mobile}


def _keys(identity):
    return [(kind, identity[kind]) for kind in ("email", "mobile") if identity[kind]]


def _same_person(left, right):
    # Never merge people on a shared household contact or a name alone.
    same_contact = any(left[key] and left[key] == right[key] for key in ("email", "mobile"))
    if left["name"] and right["name"]:
        return left["name"] == right["name"] and same_contact
    return bool(left["email"] and left["mobile"]
                and left["email"] == right["email"] and left["mobile"] == right["mobile"])


def failed_payment_report(db, batch_id):
    buyers = db.execute(
        "SELECT id, buyer_reference, payment_status, source_data_json FROM buyers WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    registrations = db.execute(
        """SELECT r.id, r.first_name, r.last_name, r.source_data_json, t.payment_status
           FROM registrants r
           LEFT JOIN tickets t ON t.batch_id = r.batch_id AND t.ticket_code = r.ticket_code
           WHERE r.batch_id = ?""", (batch_id,),
    ).fetchall()
    paid = []
    contact_index = defaultdict(set)
    for row in registrations:
        if _text(row["payment_status"]).casefold() != "payment validated":
            continue
        source = _source(row["source_data_json"])
        identity = _contact(source, "{} {}".format(row["first_name"] or "", row["last_name"] or ""))
        index = len(paid)
        paid.append({"identity": identity, "created": _date(source.get("Created At"))})
        for key in _keys(identity):
            contact_index[key].add(index)

    groups = {}
    failed_attempts = recovered_attempts = 0
    for buyer in buyers:
        if _text(buyer["payment_status"]).casefold() not in {"payment failed", "failed"}:
            continue
        failed_attempts += 1
        source = _source(buyer["source_data_json"])
        name = _text(source.get("Buyer Name"))
        identity = _contact(source, name)
        created = _date(source.get("Created At"))
        failed = _date(source.get("Failed At"))
        candidates = set()
        for key in _keys(identity):
            candidates.update(contact_index[key])
        matches = [paid[index] for index in candidates if _same_person(identity, paid[index]["identity"])]
        if created and any(match["created"] and match["created"] > created for match in matches):
            recovered_attempts += 1
            continue
        if not _keys(identity) or not identity["name"]:
            review = "Incomplete identity — review manually"
        elif matches and (not created or any(not match["created"] for match in matches)):
            review = "Matching paid registration — date unavailable"
        elif candidates and not matches:
            review = "Shared contact or different name — review manually"
        elif matches:
            review = "Paid registration exists before or at this attempt"
        else:
            review = "No later paid registration found"
        key = (identity["name"], identity["email"], identity["mobile"])
        if not identity["name"] or not _keys(identity):
            key = (buyer["id"],)
        entry = {
            "buyer_id": buyer["id"],
            "person_key": hashlib.sha256(json.dumps(key, ensure_ascii=True).encode()).hexdigest(),
            "name": name or "Name unavailable",
            "email": _text(source.get("Email Address")),
            "mobile": _text(source.get("Mobile Number")),
            "reference": buyer["buyer_reference"],
            "failed_at": failed,
            "created_at": created,
            "reason": _text(source.get("Failed Reason")) or "Not provided",
            "review": review,
            "needs_review": review != "No later paid registration found",
            "attempts": 1,
        }
        previous = groups.get(key)
        if previous:
            count = previous["attempts"] + 1
            if (failed or created or datetime.min) > (previous["failed_at"] or previous["created_at"] or datetime.min):
                groups[key] = entry
            groups[key]["attempts"] = count
        else:
            groups[key] = entry
    rows = sorted(groups.values(), key=lambda row: (
        row["failed_at"] or row["created_at"] or datetime.min, row["reference"] or ""
    ), reverse=True)
    return {"rows": rows, "failed_attempts": failed_attempts,
            "recovered_attempts": recovered_attempts,
            "review_count": sum(row["needs_review"] for row in rows)}


@bp.get("/events/<int:event_id>/failed-payments")
def event_failed_payments(event_id):
    if not has_capability(CAPABILITY_VIEW_FAILED_PAYMENTS):
        abort(403)
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        abort(404)
    batch = active_batch(db, event_id)
    report = failed_payment_report(db, batch["id"]) if batch else {
        "rows": [], "failed_attempts": 0, "recovered_attempts": 0, "review_count": 0,
    }
    query = _text(request.args.get("q"))[:100]
    rows = [row for row in report["rows"] if not row["needs_review"]]
    total_people = len(rows)
    if query:
        rows = [row for row in rows if query.casefold() in " ".join(
            str(row[key] or "") for key in ("name", "email", "mobile")
        ).casefold()]
    per_page = request.args.get("per_page", 25, type=int)
    if per_page not in (25, 50, 100):
        per_page = 25
    pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = min(pages, max(1, request.args.get("page", 1, type=int)))
    page_rows = rows[(page - 1) * per_page:page * per_page]
    if page_rows:
        keys = [row["person_key"] for row in page_rows]
        summaries = db.execute(
            "SELECT person_key, SUM(CASE WHEN kind = 'outreach' THEN 1 ELSE 0 END) AS outreach_count, "
            "COUNT(remark) AS remark_count, MAX(CASE WHEN remark IS NOT NULL THEN id END) AS latest_remark_id "
            "FROM failed_payment_followups WHERE event_id = ? AND person_key IN ({}) GROUP BY person_key".format(
                ",".join("?" for _ in keys)), [event_id] + keys,
        ).fetchall()
        summary_map = {row["person_key"]: dict(row) for row in summaries}
        latest_ids = [row["latest_remark_id"] for row in summaries if row["latest_remark_id"]]
        latest_remarks = {}
        if latest_ids:
            latest_remarks = {row["id"]: row["remark"] for row in db.execute(
                "SELECT id, remark FROM failed_payment_followups WHERE event_id = ? AND id IN ({})".format(
                    ",".join("?" for _ in latest_ids)), [event_id] + latest_ids,
            ).fetchall()}
        for row in page_rows:
            summary = summary_map.get(row["person_key"], {})
            row["outreach_count"] = int(summary.get("outreach_count", 0))
            row["remark_count"] = int(summary.get("remark_count", 0))
            row["latest_remark"] = latest_remarks.get(summary.get("latest_remark_id"), "")
    return render_template("failed_payments.html", event=event, active_batch=batch,
                           report=report, rows=page_rows, followup_edit_allowed=_can_edit_followups(),
                           total_people=total_people, total=len(rows), query=query,
                           page=page, pages=pages, per_page=per_page)


def _can_edit_followups():
    return (current_user.is_authenticated and current_user.status == "approved"
            and has_capability(CAPABILITY_VIEW_FAILED_PAYMENTS))


@bp.route("/events/<int:event_id>/failed-payments/<int:buyer_id>/followups", methods=["GET", "POST"])
def payment_followups(event_id, buyer_id):
    if not has_capability(CAPABILITY_VIEW_FAILED_PAYMENTS):
        abort(403)
    if request.method == "POST" and not _can_edit_followups():
        abort(403)
    db = get_db()
    batch = active_batch(db, event_id)
    if not batch:
        abort(404)
    person = next((row for row in failed_payment_report(db, batch["id"])["rows"]
                   if row["buyer_id"] == buyer_id and not row["needs_review"]), None)
    if person is None:
        abort(404)
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) - {"kind", "remark", "confirmed"}:
            return jsonify(error="Please choose a follow-up or add a remark."), 400
        kind = payload.get("kind")
        if kind not in ("outreach", "remark"):
            return jsonify(error="Please choose a follow-up or add a remark."), 400
        if kind == "outreach" and payload.get("confirmed") is not True:
            return jsonify(error="Please confirm that you reached out before saving."), 400
        remark = payload.get("remark", "")
        if not isinstance(remark, str) or len(remark.strip()) > 4000:
            return jsonify(error="Remarks must be text with at most 4,000 characters."), 400
        remark = remark.strip()
        if kind == "remark" and not remark:
            return jsonify(error="Please enter a remark."), 400
        db.execute(
            "INSERT INTO failed_payment_followups "
            "(event_id, person_key, kind, remark, created_by_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, person["person_key"], kind, remark or None, current_user.id, utc_now()),
        )
        db.commit()
    history = db.execute(
        "SELECT followup.id, followup.kind, followup.remark, followup.created_at, users.username AS created_by "
        "FROM failed_payment_followups followup LEFT JOIN users ON users.id = followup.created_by_user_id "
        "WHERE followup.event_id = ? AND followup.person_key = ? ORDER BY followup.created_at DESC, followup.id DESC",
        (event_id, person["person_key"]),
    ).fetchall()
    return jsonify(
        outreach_count=sum(row["kind"] == "outreach" for row in history),
        history=[{**dict(row), "created_at": format_operational_datetime(row["created_at"])} for row in history],
    )
