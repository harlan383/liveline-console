# Stage 3.4.8 Auth Production Environment Guardrails

## Stage Goal

Stage 3.4.8 implements startup guardrails for Auth production environment
configuration. When `APP_ENV=production`, unsafe Auth settings must fail fast
before the backend starts. Local development remains usable with local
placeholders and safe defaults.

This stage is an Auth security hardening implementation stage. It does not
change production link state and does not perform any network, task, or cutover
operation.

## Environment Marker

The project already had an environment marker:

- `APP_ENV`

Stage 3.4.8 reuses `APP_ENV`. Production guardrails apply only when:

- `APP_ENV=production`

Local development continues to use:

- `APP_ENV=local`

This keeps local Docker Compose and `.env.example` placeholders usable while
still enforcing stronger checks for production deployments.

## Production Guardrails

When `APP_ENV=production`, `backend/app/core/config.py` now enforces:

| Setting | Guardrail |
| --- | --- |
| `SESSION_SECRET` | Required, at least 32 characters, and must not look like an obvious placeholder or weak example value. |
| `ADMIN_PASSWORD_HASH` | Required and must look like the project secure hash format: `pbkdf2_sha256$iterations$salt$digest`. |
| `COOKIE_SECURE` | Must be `true`. |
| `COOKIE_SAMESITE` | Must be one of `lax`, `strict`, or `none`. |
| `SESSION_TTL_SECONDS` | Must be a positive integer. |
| `AUTH_LOGIN_MAX_ATTEMPTS` | Must be a positive integer. |
| `AUTH_LOGIN_WINDOW_SECONDS` | Must be a positive integer. |
| `AUTH_LOGIN_LOCK_SECONDS` | Must be a positive integer. |

Production error messages identify the invalid setting and requirement, but
they do not print real secret values, real password hashes, cookies, sessions,
tokens, or node links.

## Local Development Compatibility

- `APP_ENV=local` does not apply production-only placeholder checks.
- `.env.example` remains local-development friendly.
- `COOKIE_SECURE=false` remains valid for local HTTP development.
- Local Docker Compose must continue to build and start.
- `/api/health` must remain accessible after local startup.
- Login gate and login failure rate limiting remain unchanged.

## Modified Files

- `backend/app/core/config.py`
- `README.md`
- `docs/stage-3.4.8-auth-production-env-guardrails.md`

No database migration was added.

## Local Acceptance Results

| Check | Result |
| --- | --- |
| `python compileall backend/app` | Passed |
| `npm run build` | Passed |
| `docker compose up --build -d` | Passed |
| `/api/health` reports backend/database/redis/worker ok | Passed |
| Local development environment starts with existing local placeholders | Passed |
| Production simulation rejects weak `SESSION_SECRET` | Passed |
| Production simulation rejects `COOKIE_SECURE=false` | Passed |
| Production simulation rejects missing `ADMIN_PASSWORD_HASH` | Passed |
| Production simulation avoids real secret/hash/password values | Passed |
| Redis `temp_credential:*` remains empty | Passed |
| Pending / running tasks remain `0` | Passed |

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

## Safety Boundary

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write full node links.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not let `socat` take over 8443.
- Do not close, stop, disable, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Conclusion

Stage 3.4.8 adds production-only Auth configuration guardrails. Production now
fails fast for weak or placeholder Auth settings, while local development keeps
working with local placeholders and defaults.
