# Production Acceptance and UAT

Record environment, image digest, commit, database revision, configuration
version, tester, date/time, evidence link, result, and defect for every item.
Unchecked items are not implicitly accepted.

The 2026-08-29 automated and local-disposable results are recorded in
`PHASE_2_VERIFICATION.md`. They prepare this checklist but do not check any
target-environment or human-sign-off item below.

## Production acceptance

### Deployment

- [ ] Clean deployment succeeds through Gunicorn/container.
- [ ] Graceful restart succeeds without interrupted work.
- [ ] Correct environment/configuration and secret references load.
- [ ] External liveness and readiness pass.

### Database and recovery

- [ ] Intended MySQL is reachable with least-required privileges.
- [ ] `alembic current` equals `alembic heads`; `alembic check` is clean.
- [ ] Backup and checksum manifest succeed into approved encrypted storage.
- [ ] Full restore and every restoration verification item succeed in the approved recovery environment.

### Security

- [ ] HTTPS and safe authentication redirects are verified externally.
- [ ] Session cookie is `Secure`, `HttpOnly`, and approved `SameSite`.
- [ ] Secrets/default credentials are absent from Git, image layers, configuration output, and logs.
- [ ] CSRF rejects a state-changing request without a valid token.
- [ ] Administrator-only Users, Admin Tables, and batch deletion are verified.
- [ ] Untrusted forwarded headers do not alter URL/host behavior; trusted proxy behavior matches configured hops.

### Application

- [ ] Administrator and approved-user login/logout/session expiry work.
- [ ] Pending registration and administrator approval work.
- [ ] Two Events remain isolated across dashboard, imports, batches, Data Quality, Admin Tables, and satellite data.
- [ ] A complete batch validates/processes/activates and remains traceable.
- [ ] A failed batch leaves the previous active dataset unchanged.
- [ ] Dashboard headline/demographic/satellite reconciliation passes.
- [ ] Data Quality and administrator-protected Admin Tables work, including safe attestation links.

### Operations

- [ ] Structured lifecycle/request/auth/import logs arrive at the approved collector.
- [ ] Reviewed samples contain no personal data or secrets.
- [ ] A controlled database outage makes readiness fail and recover.
- [ ] A controlled import failure generates the configured observable alert.
- [ ] Application unavailable, readiness, database, and repeated-import alerts are exercised end to end.

## Administrator UAT

- [ ] Authenticate and observe lockout/session/logout behavior.
- [ ] Review and approve a pending user.
- [ ] Create/open Events and verify Event isolation.
- [ ] Change Event settings.
- [ ] Upload/validate all three imports; review validation and batch history.
- [ ] Process/activate, reactivate an inactive batch, and verify atomic recovery.
- [ ] Verify active/in-progress batch deletion restrictions and administrator-only deletion.
- [ ] Reconcile Dashboard and Satellite Datasets.
- [ ] Inspect Data Quality and issue drill-downs.
- [ ] Inspect Admin Tables, attestation links, pagination, columns, and curated sources.
- [ ] Confirm no protected data crosses Event/batch scope.

## Approved standard-user UAT

- [ ] Authenticate and access the normal approved-user application.
- [ ] Verify correct Event/dashboard/Data Quality/satellite isolation.
- [ ] Verify Admin Tables and user management return forbidden/are absent.
- [ ] Verify batch deletion is forbidden.
- [ ] Verify Event settings and import mutation behavior according to P2-09.

P2-09 is currently **Decision Required**. The safe staging/production default is
read access with administrator-only Event settings, Satellite Dataset mutation,
and import validation/processing/activation. Test both the approved policy and
server-side denial; do not change it based only on UAT preference.

## Registration-role UAT

- [ ] Administrator assigns **Registration** during approval and to an existing
  non-admin account; public registration cannot self-select the role.
- [ ] Login lands on Events/Dashboard and the Event sidebar contains only
  **Dashboard** and **Registrations** plus ordinary account actions.
- [ ] Dashboard aggregates load, while Event Date, Participant Target,
  Satellite Dataset, create/import, and other configuration actions are absent.
- [ ] Registrations page/data search, filtering, sorting, pagination, logistics,
  safe form links, and Payment Status work within the selected Event/batch.
- [ ] Pending/Verified/Invalid updates succeed and attribute the authenticated
  Registration operator and server timestamp.
- [ ] Direct Analytics, Compare, Satellite, Data Quality, Admin Tables/source
  lineage, Imports/batches, settings, and Users requests return HTTP 403.
- [ ] Cross-Event batch and registrant URL manipulation is rejected.
- [ ] Administrator access to every existing module and action remains intact.

## Acceptance decision

The final production release approver is **Decision Required**. Acceptance must
list any waivers explicitly. A checklist file or automated test is not evidence
that target-environment HTTPS, restore, alert delivery, or human UAT occurred.
