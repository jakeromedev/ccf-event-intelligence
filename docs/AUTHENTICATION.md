# Authentication and user approval

Application operators are stored in `users`. They are intentionally separate
from event `registrants` and the curated participant identity model.

## Roles and lifecycle

- `admin`: the single terminal-initialized administrator. Its username is
  always `admin`, and it is always approved.
- `user`: a normal operator created through public registration. Every new
  account starts as `pending` and cannot enter the application until approved.
- `registration`: operational event-registration staff. This role is assigned
  only by the administrator and has deny-by-default access to Dashboard and
  Registrations, including attestation verification.

Usernames are normalized to lowercase and are unique under a case-insensitive
MySQL collation. The database reserves every case variant of `admin` and checks
that no other username can have the `admin` role. Public registration never
accepts a role selection. The administrator can select Standard User or
Registration during approval and can change an existing non-admin account
between those two roles. The web application has no admin promotion, admin
registration, or admin deletion operation.

## Role matrix

| Capability | Administrator | Registration |
|---|---:|---:|
| Dashboard | Yes | Yes, read-only |
| Registrations | Yes | Yes |
| Edit attestation verification | Yes | Yes |
| Analytics and Compare | Yes | No |
| Data Quality | Yes | No |
| Admin Tables and source lineage | Yes | No |
| Imports and batch administration | Yes | No |
| Event and Participant Target settings | Yes | No |
| Satellite pages and Dataset settings | Yes | No |
| User approval and role management | Yes | No |

The existing `user` role retains its established approved-user behavior. It is
not silently converted to Registration, and the optional standard-user mutation
configuration never grants privileges to a Registration operator.

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
4. The admin opens **Users**, chooses **Standard User** or **Registration**, and
   selects **Approve**.
5. Approval records the timestamp and administrator ID. The user can then log
   in normally.

Approval and user-management endpoints enforce the admin role on the server.
The centralized capability map grants Registration only `dashboard.view`,
`registrations.view`, and `registrations.attestation.edit`. A global
Registration-role endpoint allow-list then denies every unlisted route with
HTTP 403, while the listed Registrations routes still validate Event, batch,
and registrant ownership. Sidebar visibility is presentation only and is not
the security boundary.

The attestation PATCH route requires global CSRF validation and supplies the
reviewer ID and timestamp from the authenticated server context. Enabling
authentication-disabled local reads never permits an anonymous verification
update. Imported registration fields remain immutable.

Phase 3 Analytics pages and aggregate APIs remain available under the existing
administrator/standard-user boundary, but are expressly denied to Registration.
The current application has no per-user Event ACL, so the role does not invent
one: an approved Registration operator can select the same project Events as
other approved operators. Within every selected Event, active and historical
batch identifiers and registration records are validated against that Event;
cross-Event batch/registrant manipulation is rejected. Phase 3 introduces no
row-level export permission: downloadable reports remain disabled pending the
separate decision in `PHASE_3_DECISIONS.md`. `REPORTING.md` records the required
future server-side permission and safety contract. Admin Tables remains
administrator-only and does not imply export authority.

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
staging default those mutations to administrator-only. Registration is always
excluded from that optional policy. Users, Admin Tables, Event configuration,
imports/batches, Satellite Dataset settings, and all advanced analytical
modules remain denied to Registration.

## Tests

Run the complete suite against the dedicated MySQL test schema:

```sh
. instance/mysql.env
.venv/bin/python -m unittest discover -s tests -v
```

`MYSQL_TEST_DATABASE_URL` must point to a disposable database whose name
contains `test`; the suite recreates its application tables.

The 2026-08-31 Registration-role verification passed **104 SQLite tests** and
the identical **104-test disposable MySQL 8.4 suite**. It also passed a fresh
MySQL Alembic upgrade to `c8f5d2b0e417`, the role revision's
downgrade/re-upgrade contract, `alembic check`, Ruff, compilation, production
configuration validation, and local Gunicorn readiness/graceful shutdown.
Hosted CI was not executed from the local working tree.
