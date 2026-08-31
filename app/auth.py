"""Authentication, registration, approval, and terminal-only admin initialization."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlsplit

import click
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from .db import get_db
from .extensions import login_manager
from .models import User, hash_password, verify_password_hash


bp = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15

CAPABILITY_VIEW_DASHBOARD = "dashboard.view"
CAPABILITY_VIEW_REGISTRATIONS = "registrations.view"
CAPABILITY_EDIT_ATTESTATION = "registrations.attestation.edit"
CAPABILITY_EDIT_REMARKS = "registrations.remarks.edit"
CAPABILITY_VIEW_ANALYTICS = "analytics.view"
CAPABILITY_VIEW_SATELLITES = "satellites.view"
CAPABILITY_VIEW_DATA_QUALITY = "data_quality.view"
CAPABILITY_VIEW_IMPORTS = "imports.view"
CAPABILITY_CREATE_EVENTS = "events.create"
CAPABILITY_VIEW_EVENT_SETTINGS = "events.settings.view"
CAPABILITY_VIEW_ADMIN_TABLES = "admin_tables.view"
CAPABILITY_MANAGE_USERS = "users.manage"

REGISTRATION_CAPABILITIES = frozenset(
    {
        CAPABILITY_VIEW_DASHBOARD,
        CAPABILITY_VIEW_REGISTRATIONS,
        CAPABILITY_EDIT_ATTESTATION,
        CAPABILITY_EDIT_REMARKS,
    }
)
STANDARD_USER_CAPABILITIES = frozenset(
    {
        CAPABILITY_VIEW_DASHBOARD,
        CAPABILITY_VIEW_ANALYTICS,
        CAPABILITY_VIEW_SATELLITES,
        CAPABILITY_VIEW_DATA_QUALITY,
        CAPABILITY_VIEW_IMPORTS,
        CAPABILITY_CREATE_EVENTS,
        CAPABILITY_VIEW_EVENT_SETTINGS,
    }
)

# A Registration operator is intentionally deny-by-default. Every endpoint in
# this set still performs its own Event/batch ownership validation.
REGISTRATION_ENDPOINT_CAPABILITIES = {
    "auth.logout": CAPABILITY_VIEW_DASHBOARD,
    "dashboard.index": CAPABILITY_VIEW_DASHBOARD,
    "dashboard.events": CAPABILITY_VIEW_DASHBOARD,
    "dashboard.event_overview": CAPABILITY_VIEW_DASHBOARD,
    "dashboard.event_dashboard_api": CAPABILITY_VIEW_DASHBOARD,
    "dashboard.event_registrations": CAPABILITY_VIEW_REGISTRATIONS,
    "dashboard.event_registrations_data": CAPABILITY_VIEW_REGISTRATIONS,
    "dashboard.update_registration_attestation": CAPABILITY_EDIT_ATTESTATION,
    "dashboard.registration_remarks": CAPABILITY_VIEW_REGISTRATIONS,
    "dashboard.resolve_registration_remark": CAPABILITY_EDIT_REMARKS,
}

# Checking this when a username does not exist reduces timing differences
# without creating or retaining any account-specific plaintext.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(24))


def normalize_username(value: str | None) -> str:
    return (value or "").strip().casefold()


def validate_public_username(_form, field) -> None:
    username = normalize_username(field.data)
    if len(username) < 3 or len(username) > 64:
        raise ValidationError("Username must be between 3 and 64 characters.")
    if username == "admin":
        raise ValidationError("That username is reserved.")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError(
            "Use lowercase letters, numbers, periods, underscores, or hyphens."
        )


def validate_strong_password(_form, field) -> None:
    password = field.data or ""
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationError("Password must be between 12 and 128 characters.")
    categories = (
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() for character in password),
    )
    if sum(categories) < 3:
        raise ValidationError(
            "Password must use at least three of: lowercase, uppercase, numbers, symbols."
        )


class LoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=64)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    next_url = HiddenField()
    submit = SubmitField("Login")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), validate_public_username]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), validate_strong_password]
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")


def _safe_next_url(candidate: str | None) -> str | None:
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return candidate


def admin_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return protected


def has_capability(capability: str) -> bool:
    """Resolve one application capability without granting implicit privileges."""
    if current_app.config.get("AUTHENTICATION_DISABLED", False):
        return True
    if not current_user.is_authenticated or current_user.status != "approved":
        return False
    if current_user.is_admin:
        return True
    if current_user.role == "registration":
        return capability in REGISTRATION_CAPABILITIES
    if current_user.role == "user":
        return capability in STANDARD_USER_CAPABILITIES
    return False


def can_view_dashboard() -> bool:
    return has_capability(CAPABILITY_VIEW_DASHBOARD)


def can_view_registrations() -> bool:
    return has_capability(CAPABILITY_VIEW_REGISTRATIONS)


def can_edit_attestation_verification() -> bool:
    # Status changes always require an attributable authenticated operator,
    # including in local deployments where read authentication is disabled.
    return bool(
        current_user.is_authenticated
        and current_user.status == "approved"
        and (
            current_user.is_admin
            or (
                current_user.role == "registration"
                and CAPABILITY_EDIT_ATTESTATION in REGISTRATION_CAPABILITIES
            )
        )
    )


def can_edit_registrant_remarks() -> bool:
    """Require an attributable administrator or Registration operator."""
    return bool(
        current_user.is_authenticated
        and current_user.status == "approved"
        and (
            current_user.is_admin
            or (
                current_user.role == "registration"
                and CAPABILITY_EDIT_REMARKS in REGISTRATION_CAPABILITIES
            )
        )
    )


def can_view_analytics() -> bool:
    return has_capability(CAPABILITY_VIEW_ANALYTICS)


def can_view_satellites() -> bool:
    return has_capability(CAPABILITY_VIEW_SATELLITES)


def can_view_data_quality() -> bool:
    return has_capability(CAPABILITY_VIEW_DATA_QUALITY)


def can_view_imports() -> bool:
    return has_capability(CAPABILITY_VIEW_IMPORTS)


def can_view_admin_tables() -> bool:
    return has_capability(CAPABILITY_VIEW_ADMIN_TABLES)


def can_manage_users() -> bool:
    return has_capability(CAPABILITY_MANAGE_USERS)


def can_create_events() -> bool:
    return has_capability(CAPABILITY_CREATE_EVENTS)


def can_view_event_settings() -> bool:
    return has_capability(CAPABILITY_VIEW_EVENT_SETTINGS)


def event_mutations_allowed() -> bool:
    """Return whether the current operator may change Event/import state."""
    if current_app.config.get("AUTHENTICATION_DISABLED", False):
        return True
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return True
    # Registration operators are never covered by the optional standard-user
    # mutation switch.
    return bool(
        current_user.role == "user"
        and current_app.config.get("STANDARD_USER_MUTATIONS_ALLOWED", False)
    )


def event_mutation_required(view):
    """Keep undecided production mutation privileges administrator-only."""

    @wraps(view)
    def protected(*args, **kwargs):
        if not event_mutations_allowed():
            abort(403)
        return view(*args, **kwargs)

    return protected


@bp.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.events"))

    form = LoginForm()
    if request.method == "GET":
        form.next_url.data = _safe_next_url(request.args.get("next")) or ""
    if form.validate_on_submit():
        username = normalize_username(form.username.data)
        db = get_db()
        user = db.session.scalar(
            select(User).where(func.lower(User.username) == username)
        )
        now = datetime.now()
        if user is None:
            verify_password_hash(DUMMY_PASSWORD_HASH, form.password.data)
            current_app.logger.warning(
                "authentication_failed", extra={"event": "authentication_failed", "reason": "invalid_credentials"}
            )
            flash("Invalid username or password.", "error")
        elif user.locked_until and user.locked_until > now:
            current_app.logger.warning(
                "authentication_failed",
                extra={"event": "authentication_failed", "reason": "account_locked", "user_id": user.id},
            )
            flash("Too many login attempts. Please try again later.", "error")
        elif not user.check_password(form.password.data):
            user.failed_login_count += 1
            if user.failed_login_count >= LOGIN_FAILURE_LIMIT:
                user.failed_login_count = 0
                user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
            user.updated_at = now
            db.commit()
            current_app.logger.warning(
                "authentication_failed",
                extra={"event": "authentication_failed", "reason": "invalid_credentials", "user_id": user.id},
            )
            flash("Invalid username or password.", "error")
        else:
            user.failed_login_count = 0
            user.locked_until = None
            user.updated_at = now
            db.commit()
            if user.status != "approved":
                current_app.logger.warning(
                    "authentication_failed",
                    extra={"event": "authentication_failed", "reason": "account_not_approved", "user_id": user.id},
                )
                flash("Your account is awaiting administrator approval.", "error")
            else:
                # Flask's signed-cookie session has no server-side session id;
                # clearing it before login prevents fixation of pre-login state.
                session.clear()
                login_user(user, remember=False, fresh=True)
                session["auth_version"] = user.auth_version
                session.permanent = True
                current_app.logger.info(
                    "authentication_succeeded",
                    extra={"event": "authentication_succeeded", "user_id": user.id, "role": user.role},
                )
                destination = _safe_next_url(form.next_url.data)
                if user.role == "registration":
                    destination = None
                return redirect(destination or url_for("dashboard.events"))

    return render_template("login.html", form=form)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.events"))

    form = RegistrationForm()
    if form.validate_on_submit():
        username = normalize_username(form.username.data)
        db = get_db()
        exists = db.session.scalar(
            select(User.id).where(func.lower(User.username) == username)
        )
        if exists is not None:
            form.username.errors.append("That username is already registered.")
        else:
            user = User(username=username, role="user", status="pending")
            user.set_password(form.password.data)
            db.session.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                form.username.errors.append("That username is already registered.")
            else:
                flash(
                    "Registration successful. Your account is awaiting administrator "
                    "approval. You will be able to access the system once approved.",
                    "success",
                )
                return redirect(url_for("auth.login"))

    return render_template("register.html", form=form)


@bp.post("/logout")
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


@bp.get("/admin/users")
@admin_required
def users():
    registered_users = get_db().session.scalars(
        select(User)
        .where(User.role.in_(("user", "registration")))
        .order_by(User.status.asc(), User.created_at.asc(), User.id.asc())
    ).all()
    return render_template(
        "users.html", event=None, active_batch=None, users=registered_users
    )


@bp.post("/admin/users/<int:user_id>/approve")
@admin_required
def approve_user(user_id):
    db = get_db()
    user = db.session.get(User, user_id)
    if user is None or user.role not in ("user", "registration"):
        abort(404)
    if user.status == "pending":
        role = request.form.get("role", "user")
        if role not in ("user", "registration"):
            abort(400)
        now = datetime.now()
        user.role = role
        user.status = "approved"
        user.approved_at = now
        user.approved_by = current_user.id
        user.updated_at = now
        db.commit()
        current_app.logger.info(
            "user_approved",
            extra={
                "event": "user_approved",
                "user_id": user.id,
            },
        )
        flash("{} has been approved.".format(user.username), "success")
    else:
        flash("{} is already approved.".format(user.username), "success")
    return redirect(url_for("auth.users"))


@bp.post("/admin/users/<int:user_id>/role")
@admin_required
def update_user_role(user_id):
    db = get_db()
    user = db.session.get(User, user_id)
    if user is None or user.is_admin:
        abort(404)
    role = request.form.get("role")
    if role not in ("user", "registration"):
        abort(400)
    if user.role != role:
        user.role = role
        user.auth_version += 1
        user.updated_at = datetime.now()
        db.commit()
        current_app.logger.info(
            "user_role_updated",
            extra={
                "event": "user_role_updated",
                "user_id": user.id,
                "role": role,
            },
        )
        flash("{} now has the {} role.".format(user.username, role.title()), "success")
    return redirect(url_for("auth.users"))


def init_app(app) -> None:
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.session_protection = "strong"

    @app.context_processor
    def authorization_context():
        return {
            "dashboard_allowed": can_view_dashboard(),
            "analytics_allowed": can_view_analytics(),
            "satellites_allowed": can_view_satellites(),
            "data_quality_allowed": can_view_data_quality(),
            "imports_allowed": can_view_imports(),
            "event_creation_allowed": can_create_events(),
            "event_settings_visible": can_view_event_settings(),
            "event_mutations_allowed": event_mutations_allowed(),
            "user_management_allowed": can_manage_users(),
        }

    @login_manager.user_loader
    def load_user(user_id):
        try:
            identifier = int(user_id)
        except (TypeError, ValueError):
            return None
        user = get_db().session.get(User, identifier)
        if user is None or user.status != "approved":
            return None
        if session.get("auth_version") != user.auth_version:
            return None
        return user

    @app.before_request
    def require_authenticated_operator():
        if current_app.config.get("AUTHENTICATION_DISABLED", False):
            return None
        if request.endpoint in {
            "static",
            "auth.login",
            "auth.register",
            "operations.liveness",
            "operations.readiness",
        }:
            return None
        if current_user.is_authenticated:
            if current_user.role == "registration":
                capability = REGISTRATION_ENDPOINT_CAPABILITIES.get(request.endpoint)
                if capability is None or not has_capability(capability):
                    abort(403)
            return None
        next_url = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("auth.login", next=next_url))

    @app.cli.command("admin-init")
    def initialize_admin_command():
        """Create the sole administrator or reset its password."""
        plaintext_password = secrets.token_urlsafe(24)
        password_hash = hash_password(plaintext_password)
        db = get_db()
        existing = False
        now = datetime.now()
        try:
            with db.session.begin():
                candidates = db.session.scalars(
                    select(User)
                    .where(
                        or_(
                            User.role == "admin",
                            func.lower(User.username) == "admin",
                        )
                    )
                    .with_for_update()
                ).all()
                if len(candidates) > 1:
                    raise click.ClickException(
                        "Conflicting administrator records exist; no password was changed."
                    )
                if candidates:
                    admin = candidates[0]
                    existing = True
                    admin.auth_version += 1
                else:
                    admin = User(username="admin", auth_version=1)
                    db.session.add(admin)
                admin.username = "admin"
                admin.password_hash = password_hash
                admin.role = "admin"
                admin.status = "approved"
                admin.approved_at = admin.approved_at or now
                admin.approved_by = None
                admin.failed_login_count = 0
                admin.locked_until = None
                admin.updated_at = now
                db.session.flush()
        except click.ClickException:
            raise
        except Exception as exc:
            db.rollback()
            raise click.ClickException(
                "Administrator initialization failed; no password was displayed."
            ) from exc

        current_app.logger.info(
            "administrator_initialized",
            extra={
                "event": "administrator_initialized",
                "user_id": admin.id,
                "changed": existing,
            },
        )

        if existing:
            click.echo("WARNING: An admin account already exists.\n")
            click.echo("The existing admin password has been OVERRIDDEN.\n")
            click.echo("Username: admin")
            click.echo("New Password: {}\n".format(plaintext_password))
            click.echo("The previous admin password is no longer valid.\n")
            click.echo("Existing admin sessions have been invalidated.")
            click.echo("Save this password securely.")
        else:
            click.echo("Admin account initialized successfully.\n")
            click.echo("Username: admin")
            click.echo("Password: {}\n".format(plaintext_password))
            click.echo("IMPORTANT:")
            click.echo("Save this password securely.")
            click.echo("It will not be displayed again unless admin-init is rerun.")
