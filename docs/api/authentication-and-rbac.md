# Individual accounts and the three-role policy

Exactly three operational roles are supported: SUPERADMIN, EDITOR and CONTENT_WRITER. The former shared editor token is not accepted by any newsroom endpoint. FastAPI authenticates an opaque cookie against a hashed, expiring PostgreSQL session record, rechecks account status and role on every request, and applies ownership/assignment checks independently of the UI.

| Capability | Superadmin | Editor | Content Writer |
| --- | --- | --- | --- |
| Write, generate, upload images, maintain credits | Any story | Any story | Own or explicitly assigned stories |
| Submit an exact saved revision | Yes | Yes | Yes |
| Review, approve, reject, request changes, authorize READY | Yes | Yes | No |
| Set publication schedules | Yes | Yes | No |
| Create/edit/suspend/delete users or change roles | Yes | No | No |
| Assign/reassign/reopen tasks and see all workloads | Yes | No | No |
| Manage sources and collection configuration | Yes | No | No |
| Access administrative audit history and system settings | Yes | No | No |
| View/update own assigned tasks and account security | Yes | Yes | Yes |

Editors cannot approve a revision they own, edited or submitted. A Superadmin can do so only with an explicit `self_approval_override=true` and a nonempty reason. The exception is stored in immutable decision history and the audit log. Account administration serializes the active Superadmin set, blocks disabling/demoting the last active Superadmin, and blocks self-suspension, self-deletion and self-demotion. Soft-deleted users retain their IDs and all historical foreign keys.

## Bootstrap and local setup

1. Set `AUTH_ENCRYPTION_KEY` in the ignored `.env`. Generate a Fernet key using the installed cryptography package on a trusted API host. Keep the key in deployment secrets and backups; losing it prevents MFA verification.
2. Set `AUTH_ORIGIN` to the exact dashboard origin. Local HTTP uses `AUTH_COOKIE_SECURE=false`. Production requires HTTPS and `AUTH_COOKIE_SECURE=true` (the backend default). Do not use the local development credentials or HTTP setting in production.
3. Recreate the services so the API receives these settings, then initialize the first account interactively:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy the generated value into AUTH_ENCRYPTION_KEY in .env; do not commit it.
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -it api python -m app.auth.bootstrap
```

The CLI prompts for name, email, username and a password without echoing it. It closes permanently once a Superadmin identity exists; PostgreSQL advisory locking serializes concurrent bootstrap attempts. There is no default administrator account or password. Existing shared identities migrate to inactive CONTENT_WRITER records with no password, preserving their historical authorship without elevating them.

Sign in at `/login`, enroll an authenticator using the setup URI, and verify a current code. Superadmin password verification alone creates a restricted ten-minute session: no newsroom or administration access is allowed until MFA succeeds. Editors and Writers can enroll from My Account; `AUTH_REQUIRE_EDITOR_MFA=true` also makes Editor MFA mandatory.

MFA uses PyOTP TOTP, rejects replayed time steps, rate limits verification, encrypts secrets with Fernet, revokes existing sessions on enrollment, and rotates the verified session. MFA recovery/backup codes are not provided in this phase; lost authenticators require a trusted deployment administrator to perform an audited recovery. Password reset never bypasses enrolled MFA.

## Session and password behavior

Passwords use Argon2id through argon2-cffi; accepted lengths are 12–256 characters, with rehash on login when parameters change. Session cookies are HttpOnly, SameSite=Strict, Path=/, Secure by default, and contain only a random opaque identifier. Only SHA-256 token hashes are stored. Passwords, cookies, hashes and MFA secrets are excluded from user APIs and audit payloads. The enrollment URI necessarily reveals the enrolling user's own MFA setup secret and must be treated as sensitive.

Sessions expire after eight hours by default (`AUTH_SESSION_HOURS`). `/auth/renew` rotates a fully verified session; there is no indefinite implicit renewal. Logout revokes the current session; logout-all revokes all devices. Suspension, deletion, identity/role changes and password reset revoke sessions immediately. Reactivation does not revive old sessions. The UI refreshes account state every 30 seconds; the backend denies revoked access immediately.

Unsafe API methods require the exact configured Origin, including login/reset requests. The Next.js proxy independently rejects cross-origin writes, bounds JSON request sizes, forwards only the incoming session cookie and Origin, and returns backend Set-Cookie headers. It never substitutes a service token. Expose the API only through trusted infrastructure; terminate production TLS correctly and configure the exact HTTPS origin.

Database-backed throttles survive API restarts and serialize attempt increments: ten password attempts per normalized account per 15 minutes, sixty per API-visible client address, six MFA attempts per account and additional reset limits. Behind the BFF, the IP bucket can be shared by users; capacity planning and edge rate limits remain deployment responsibilities. Expired session, reset and throttle record retention requires operational cleanup.

## Password reset delivery

Configure `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_FROM`. Delivery requires certificate-verified STARTTLS. SMTP credentials remain environment-managed. Tokens contain 48 random bytes, are hashed in PostgreSQL, expire after 30 minutes and are single-use. Reset links put the token in a URL fragment; it is removed after success. The public initiation endpoint always returns a generic eligibility message. Superadmin initiation reports missing/unavailable SMTP; no endpoint returns a reset token. Successful initiation revokes sessions and earlier reset tokens. Tests replace mail delivery and never send real email.

## API

All routes below use `/api/v1`:

- `POST /auth/login` (`identity`, `password`), `GET /auth/me`.
- `POST /auth/logout`, `/auth/logout-all`, `/auth/renew`.
- `POST /auth/mfa/setup`, `/auth/mfa/verify` (`code`).
- `POST /auth/forgot-password` (`identity`), `/auth/reset-password` (`token`, `password`).
- Superadmin-only `GET/POST /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/users/{id}/status` and `/reset-password`.
- Superadmin-only `GET /admin/audit?user_id=...` (latest 200 events).

Account listing supports name/email/username search, role and active/suspended/deleted filters. Lists currently return at most 200 rows. Account editing replaces profile/role fields; passwords change through reset. AI and platform credentials remain managed through the backend deployment environment rather than browser forms. External integration delivery is outside this phase.

Security references: [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html), [PyOTP](https://pyauth.github.io/pyotp/).

The Superadmin Settings page now displays real non-secret backend configuration status (MFA policy, session duration, cookie mode, origin, reset-delivery readiness and AI configuration) and links to accounts, assignments, collection and audit. The endpoint is independently Superadmin-only; credential values are never returned. Enable AUTH_REQUIRE_EDITOR_MFA for production Editor accounts where possible.