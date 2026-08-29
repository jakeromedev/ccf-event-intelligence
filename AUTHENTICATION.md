# Authentication and user approval

Application operators are stored in `users`. They are intentionally separate
from event `registrants` and the curated participant identity model.

## Roles and lifecycle

- `admin`: the single terminal-initialized administrator. Its username is
  always `admin`, and it is always approved.
- `user`: a normal operator created through public registration. Every new
  account starts as `pending` and cannot enter the application until approved.

Usernames are normalized to lowercase and are unique under a case-insensitive
MySQL collation. The database reserves every case variant of `admin` and checks
that no other username can have the `admin` role. The web application has no
role selector, promotion endpoint, admin registration route, or admin deletion
operation.

## First-time administrator initialization

Apply Alembic migrations, then run this only from a trusted terminal:

```sh
. instance/mysql.env
.venv/bin/alembic upgrade head
.venv/bin/flask --app 'app:create_app()' admin-init
```

The first execution creates the sole admin and prints a cryptographically
random password once:

```text
Admin account initialized successfully.

Username: admin
Password: <generated-password>

IMPORTANT:
Save this password securely.
It will not be displayed again unless admin-init is rerun.
```

Running the command again resets the existing administrator's password. It
does not create another administrator:

```text
WARNING: An admin account already exists.

The existing admin password has been OVERRIDDEN.

Username: admin
New Password: <generated-password>

The previous admin password is no longer valid.

Existing admin sessions have been invalidated.
Save this password securely.
```

The operation is transactional. Password plaintext appears only in terminal
output; the database stores an Argon2id hash. Resetting increments the account's
authentication version, invalidating existing admin sessions.

## Registration and approval

1. A user opens `/register` and provides a username and strong password.
2. The server creates a `user/pending` account and does not log it in.
3. Valid credentials for a pending account produce an awaiting-approval notice.
4. The admin opens **Users** in the application navigation and selects
   **Approve**.
5. Approval records the timestamp and administrator ID. The user can then log
   in normally.

Approval and user-management endpoints enforce the admin role on the server.
Existing event dashboards, imports, Data Quality endpoints, settings, and APIs
all require an approved authenticated account. Existing PII-bearing Admin
Tables additionally require the administrator role.

## Security controls

- Argon2id password hashing; plaintext passwords are never persisted or logged.
- Global Flask-WTF CSRF validation on state-changing requests.
- Flask-Login signed sessions with strong session protection.
- Pre-login session data is cleared before authentication to prevent fixation.
- Eight-hour permanent-session lifetime by default, with `HttpOnly` and
  `SameSite=Lax` cookies. Production requires `Secure`; it cannot silently fall
  back to an insecure cookie or development secret.
- Five failed attempts lock an account for 15 minutes; successful login and
  terminal admin reset clear the counter.
- Safe relative-only post-login redirects prevent open redirects.
- Database checks and case-insensitive uniqueness enforce the admin identity.

Production uses Gunicorn behind an explicitly trusted HTTPS proxy. Forwarded
headers are ignored unless their exact proxy-hop counts are configured. The
application validates trusted hosts, production secrets, disabled debug mode,
secure cookies, authentication, CSRF, MySQL, and Alembic head before serving.
Safe relative-only login redirects continue to work through the trusted proxy.

While the standard-user settings/import policy is unresolved, production and
staging default those mutations to administrator-only. This does not weaken the
permanent administrator-only boundaries for Users, Admin Tables, or batch deletion.

## Tests

Run the complete suite against the dedicated MySQL test schema:

```sh
. instance/mysql.env
.venv/bin/python -m unittest discover -s tests -v
```

`MYSQL_TEST_DATABASE_URL` must point to a disposable database whose name
contains `test`; the suite recreates its application tables.
