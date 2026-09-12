"""Read-only failed-payment follow-up from the active Event export."""

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, render_template, request

from .aggregation import active_batch
from .auth import CAPABILITY_VIEW_FAILED_PAYMENTS, has_capability
from .db import get_db


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
            str(row[key] or "") for key in ("name", "email", "mobile", "reference", "reason")
        ).casefold()]
    per_page = request.args.get("per_page", 25, type=int)
    if per_page not in (25, 50, 100):
        per_page = 25
    pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = min(pages, max(1, request.args.get("page", 1, type=int)))
    return render_template("failed_payments.html", event=event, active_batch=batch,
                           report=report, rows=rows[(page - 1) * per_page:page * per_page],
                           total_people=total_people, total=len(rows), query=query,
                           page=page, pages=pages, per_page=per_page)
