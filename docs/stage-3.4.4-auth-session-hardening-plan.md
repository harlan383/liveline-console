# Stage 3.4.4 Auth Session Hardening Plan

## Stage Goal

Stage 3.4.4 reviews the current authentication and session mechanism and records
a hardening plan for future stages.

This stage is a planning and security-review stage only. It does not directly
change authentication logic, does not change production link state, and does not
perform any network or cutover operation.

## Current Auth State

| Area | Current state |
| --- | --- |
| Login endpoint | `POST /api/auth/login` verifies the active admin password and creates an admin session. |
| Logout endpoint | `POST /api/auth/logout` revokes an existing session when present and clears the session cookie. If no session exists, it still clears the cookie safely. |
| Current user endpoint | `GET /api/auth/me` returns the active admin identity when the session is valid and returns `401` when unauthenticated or invalid. |
| Session cookie | Existing cookie name is `livelines_session`; it is set as `httpOnly`, uses configured `secure` and `sameSite` values, and has `max_age` from `SESSION_TTL_SECONDS`. |
| CSRF | `GET /api/auth/csrf` requires a valid session and rotates the CSRF token. Mutating protected endpoints use the existing CSRF validation helpers. |
| Password verification | Existing admin-table password hash verification is reused. Optional `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` can validate a configured hash for the matching active admin user. |
| Session expiration | Sessions expire using `SESSION_TTL_SECONDS`. Expired or revoked sessions are rejected by the session lookup. |
| 401 frontend handling | `frontend/lib/api.ts` emits `livelines:auth-expired` for protected API `401` responses; `AppShell` returns the user to the login screen. |
| Frontend password handling | Passwords are entered only in the login form and are not stored in localStorage or sessionStorage. |

## Session And Cookie Security Review

| Item | Current / planned requirement |
| --- | --- |
| `httpOnly` cookie | Required and currently used for the session cookie. |
| `sameSite` | `COOKIE_SAMESITE` must be `lax`, `strict`, or `none`. `lax` is acceptable for local and standard same-site deployments; `strict` may be considered for tighter deployments. |
| Secure cookie | `COOKIE_SECURE=true` is required for production HTTPS deployments. `COOKIE_SECURE=false` should be limited to local development. |
| Session TTL | `SESSION_TTL_SECONDS` controls session lifetime. Suggested production range is a bounded operational window such as 8 to 24 hours, adjusted to operator needs. |
| Session secret | `SESSION_SECRET` must be long, random, unique per deployment, and never committed. |
| Logout cookie clearing | Logout must continue deleting the session cookie and revoking the server-side session when present. |
| Login failure message | Login failure should remain generic, such as "username or password is wrong", without revealing which field failed. |
| Password/token storage | Do not store passwords, tokens, or session identifiers in frontend storage. |
| Logging | Do not log passwords, password hashes, cookies, raw session tokens, CSRF tokens, or full request bodies containing credentials. |

## Environment Variable Hardening Plan

| Variable | Requirement |
| --- | --- |
| `.env.example` | Must contain placeholders only. |
| `SESSION_SECRET` | Production must set a strong random value. The real value must not be committed, logged, or written to docs. |
| `SESSION_TTL_SECONDS` | Production must choose a bounded operational TTL. |
| `COOKIE_SECURE` | Must be `true` in production HTTPS environments; `false` is local-development only. |
| `COOKIE_SAMESITE` | Must remain one of `lax`, `strict`, or `none`; avoid `none` unless HTTPS and cross-site requirements are explicit. |
| `ADMIN_USERNAME` | May document the expected admin username; do not use it to expose credentials. |
| `ADMIN_PASSWORD_HASH` | Must be a secure password hash when used in production. Do not write plaintext passwords or real hashes into `.env.example`, docs, logs, or Git. |
| `INIT_TOKEN` | Must remain a placeholder in `.env.example`; real values must not be committed. |

`.env.example` must not contain real passwords, real password hashes, real
`SESSION_SECRET` values, SSH keys, Passphrases, tokens, or full node links.

## API Security Boundary

Public or public-callable interfaces:

- `GET /api/health`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`, which returns `401` when unauthenticated
- `POST /api/admin/init` as a one-time bootstrap exception protected by init
  token / initialization rules

Protected interfaces:

- `/api/nodes`
- `/api/vps`
- `/api/tasks`
- `/api/transit-resources`
- `/api/transit-routes`

All APIs that read or mutate system data, task data, server data, node data,
transit resource data, or route data must continue to require an authenticated
admin session and return `401` when unauthenticated.

## Frontend Security Boundary

- Unauthenticated users see only the login page.
- Authenticated users see the system panel.
- Protected API `401` responses trigger the login-expired flow.
- The frontend must not store plaintext passwords in localStorage or
  sessionStorage.
- The frontend must not hard-code real usernames, passwords, tokens, or node
  links.
- Login failure messages must remain generic and must not disclose account
  existence, password validity, hash state, session details, or internal errors.

## Future Hardening Recommendations

These items are recommended for later dedicated stages:

1. Add login failure rate limiting or exponential backoff.
2. Add temporary lockout or IP / username throttling for repeated failed login
   attempts.
3. Add optional session rotation after login and after privileged actions.
4. Add production checks that refuse startup when `COOKIE_SECURE=false` in a
   production environment.
5. Add stronger admin password reset and hash-generation operational guidance.
6. Add audit reporting for login failures without logging credentials.
7. Add optional idle-session timeout in addition to absolute TTL.
8. Add automated tests for unauthenticated protected API access.

## Explicit Non-Goals For This Stage

- This stage does not implement login rate limiting.
- This stage does not force cookie config changes.
- This stage does not add database migrations.
- This stage does not change business logic.
- This stage does not change auth/session code.
- Future login throttling, forced secure-cookie startup checks, session
  rotation, or idle timeout must be designed and implemented in separate
  stages.

## Production Link Boundary

- The formal production link remains `socat` 18443.
- The fallback link remains `gost` 8443.
- `node.share_link` was not read, printed, or modified.
- No full node link was written to documents, logs, task results, or Git.
- No listening port was added.
- No firewall rule was modified.
- No SSH or remote command was executed.
- No backend task was triggered.
- No cutover was performed.
- `socat` did not take over 8443.
- `gost` 8443 was not closed, stopped, disabled, downgraded, or replaced.

## Stage Result

Stage 3.4.4 records that the current auth/session implementation has a working
HttpOnly session-cookie login gate, protected API behavior, logout cookie
clearing, and frontend 401 handling. The remaining hardening work should be
implemented only in separately approved future stages.
