# Target-Environment Security Validation

This is an executable acceptance procedure, not evidence that a production
environment exists. Record target, date, image digest, configuration version,
operator, reviewer, redacted output/evidence links, and Pass/Fail for each item.
The production platform remains **Decision Required**, so every target-only
control below is currently **Blocked — Target Environment**.

## Transport and proxy boundary

1. From outside the trusted network, confirm the HTTPS endpoint presents the
   approved certificate and protocol policy:

   ```sh
   curl --fail --silent --show-error --head https://APP_HOST/health/live
   openssl s_client -connect APP_HOST:443 -servername APP_HOST </dev/null
   ```

2. Request `http://APP_HOST/` and verify the platform's approved redirect or
   rejection policy. The application container itself must not be publicly
   reachable over plaintext HTTP.
3. Confirm the application receives the expected HTTPS scheme and host through
   exactly the configured `CCF_PROXY_X_*` hops.
4. From an untrusted network, confirm the backend port is unreachable. If the
   platform provides a protected direct-backend test path, send forged
   `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-For` values and
   verify they cannot bypass the trusted proxy boundary. `ProxyFix` assumes
   network-level restriction of direct backend access.

## Session and authentication security

1. Authenticate through HTTPS using a dedicated acceptance account.
2. Inspect `Set-Cookie` and verify `Secure`, `HttpOnly`, and the approved
   `SameSite` value. Confirm no session cookie is sent on a plaintext request.
3. Verify login redirects remain on the approved host and an external `next`
   URL is rejected.
4. Submit a state-changing request without CSRF and verify rejection.
5. Directly request administrator-only URLs as a standard user and verify HTTP
   403, independently of navigation visibility.

## Secrets

1. Confirm `CCF_DASHBOARD_SECRET` and MySQL credentials are injected from the
   approved external secret source, not an image build argument, image layer,
   manifest, ConfigMap/plain environment file, or repository file.
2. Confirm production startup rejects a missing/default secret.
3. Review deployment output and sampled application/container logs for secret,
   database URL, cookie, CSRF, password, and personal-data leakage.
4. Inspect the immutable image without printing secret values:

   ```sh
   docker history --no-trunc IMAGE_DIGEST
   docker image inspect IMAGE_DIGEST
   ```

## Filesystem and container

1. Confirm the runtime identity is not root:

   ```sh
   docker run --rm --entrypoint id IMAGE_DIGEST
   ```

2. Confirm `/data/staged` is writable only by the intended runtime identity and
   is backed by the approved private encrypted volume:

   ```sh
   docker run --rm --entrypoint sh IMAGE_DIGEST -c 'id; stat -c "%a %u %g" /data /data/staged; test -w /data/staged'
   ```

3. Verify sensitive files are not world-readable and no `.env`, CSV, database,
   backup, private key, or local `instance/` artifact exists in the image.
4. Verify the staging volume is scoped to the application/environment and is
   not shared with unrelated workloads.

## MySQL

1. Confirm MySQL is not publicly exposed and only approved application,
   migration, and backup identities/networks can connect.
2. Review grants using a protected administrative channel; application runtime
   should not have account-management or global privileges.
3. Verify approved connection encryption, certificate validation, firewall/
   security-group rules, encryption at rest, and audit/monitoring controls.
4. Confirm the configured database name/environment and current Alembic head
   without printing credentials.

## Backups

1. Verify the approved store encrypts backups at rest with the approved key
   owner and restricts read/delete/restore actions to approved roles.
2. Verify protected transport from backup creator to the store.
3. Create a checksum manifest, retrieve a backup through the approved path, and
   perform the scheduled restoration verification without exposing row data.

## Acceptance outcome

Do not check the target-security Phase 2 item until all sections pass in the
selected staging/production environment and evidence is reviewed by the
assigned security/release approver.
