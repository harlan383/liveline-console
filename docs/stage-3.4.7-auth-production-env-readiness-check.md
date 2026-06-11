# Stage 3.4.7 Auth Production Environment Readiness Check

## Stage Result

Stage 3.4.7 records the production Auth environment readiness check for the
current login gate, protected API boundary, session cookie configuration, and
login failure rate limiting.

This stage is a documentation and readiness-check stage only. It does not
modify authentication logic, business code, production link state, or any
remote system.

## Current Auth State

- Stage 3.4.1 login gate is implemented.
- Stage 3.4.2 local browser login acceptance passed.
- Stage 3.4.3 protected API sweep passed.
- Stage 3.4.4 Auth/session hardening plan is documented.
- Stage 3.4.5 login failure rate limiting is implemented.
- Stage 3.4.6 browser acceptance for rate limiting passed.
- Important backend APIs are protected by login checks.
- Unauthenticated users see only the login page in the frontend.
- `401` responses send unauthenticated users back to the login flow.
- `429 AUTH_RATE_LIMITED` shows a generic rate-limit message.

## Production Environment Variable Requirements

| Variable | Production requirement |
| --- | --- |
| `SESSION_SECRET` | Must be a strong random value. It must not be empty, short, default, example, reused across environments, committed, logged, or written to docs. |
| `SESSION_TTL_SECONDS` | Must be explicitly configured with a finite session lifetime. Infinite or unbounded sessions are not acceptable. |
| `COOKIE_SECURE` | Must be `true` in production HTTPS deployments. `false` is local-development only. |
| `COOKIE_SAMESITE` | Must be explicitly set to `lax`, `strict`, or `none`; `lax` is the default recommendation unless cross-site behavior is required. |
| `ADMIN_USERNAME` | Must be explicitly configured for the production admin identity. |
| `ADMIN_PASSWORD_HASH` | Must be a secure production password hash when environment-hash login is used. It must not be empty, an example hash, a plaintext password, or a value committed to Git. |
| `AUTH_LOGIN_MAX_ATTEMPTS` | Must be explicitly set to a positive finite value. Default: `5`. |
| `AUTH_LOGIN_WINDOW_SECONDS` | Must be explicitly set to a positive finite value. Default: `600`. |
| `AUTH_LOGIN_LOCK_SECONDS` | Must be explicitly set to a positive finite value. Default: `900`. |

`.env.example` must contain only placeholders or safe local defaults. It must
not contain real secrets, real password hashes, real passwords, SSH keys,
Passphrases, tokens, or full node links.

## `.env.example` Check

| Item | Result |
| --- | --- |
| `SESSION_SECRET` uses a placeholder | Passed |
| `ADMIN_PASSWORD_HASH` uses a placeholder | Passed |
| Login rate-limit values are numeric safe defaults | Passed |
| `COOKIE_SECURE=false` is present only as local-development default | Passed |
| No real password found | Passed |
| No real hash found | Passed |
| No real `SESSION_SECRET` found | Passed |
| No SSH Key or Passphrase found | Passed |
| No token found | Passed |
| No full node link found | Passed |

## Config Code Review

Reviewed file: `backend/app/core/config.py`.

| Config behavior | Current state | Production note |
| --- | --- | --- |
| `SESSION_SECRET` | Required to be non-empty by validator. | Production still needs strong-random-value verification outside this stage. |
| `COOKIE_SAMESITE` | Validated to `lax`, `strict`, or `none`. | Keep `lax` unless a production cross-site requirement is explicitly approved. |
| `COOKIE_SECURE` | Defaults to `false`. | Must be set to `true` for production HTTPS. A future stage may add production startup enforcement. |
| `SESSION_TTL_SECONDS` | Defaults to `86400`. | Finite default exists; a future stage may add positive-value validation and production policy enforcement. |
| `ADMIN_USERNAME` | Defaults to empty. | Production must configure the intended admin username. |
| `ADMIN_PASSWORD_HASH` | Defaults to empty. | Production must configure a secure hash when environment-hash login is used; do not commit the real value. |
| `AUTH_LOGIN_MAX_ATTEMPTS` | Defaults to `5` and is validated as positive. | Production value must remain finite and deliberate. |
| `AUTH_LOGIN_WINDOW_SECONDS` | Defaults to `600` and is validated as positive. | Production value must remain finite and deliberate. |
| `AUTH_LOGIN_LOCK_SECONDS` | Defaults to `900` and is validated as positive. | Production value must remain finite and deliberate. |

## Production Readiness Checklist

Before production exposure, manually confirm:

| Check | Status |
| --- | --- |
| Strong `SESSION_SECRET` is configured outside Git | Pending production confirmation |
| Production `ADMIN_PASSWORD_HASH` is configured outside Git | Pending production confirmation |
| `COOKIE_SECURE=true` is set for HTTPS production | Pending production confirmation |
| HTTPS is enabled for the production frontend/backend path | Pending production confirmation |
| `COOKIE_SAMESITE` strategy is explicitly selected | Pending production confirmation |
| `SESSION_TTL_SECONDS` is finite and acceptable | Pending production confirmation |
| Login rate-limit parameters are explicitly selected | Pending production confirmation |
| `.env` or deployment environment variables are not committed to Git | Pending production confirmation |
| No real password, hash, secret, token, or full node link is in the repository | Passed for this stage check |
| `node.share_link` was not read or modified | Passed |
| No listening port was added | Passed |

## Follow-Up Recommendations

- Add a future production startup guard that refuses `COOKIE_SECURE=false` when
  `APP_ENV=production`.
- Add a future production startup guard for obvious placeholder
  `SESSION_SECRET` and `ADMIN_PASSWORD_HASH` values.
- Add positive-value validation for `SESSION_TTL_SECONDS`.
- Consider session rotation and idle timeout in a separately approved stage.
- Keep login rate-limit settings finite and documented during deployment.

## Production Link Boundary

- The formal production link remains `socat` 18443.
- The fallback link remains `gost` 8443.
- `node.share_link` was not read, printed, or modified in this stage.
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

Auth production environment readiness is documented. The current implementation
has working login gate, protected API checks, browser-accepted login flow, and
Redis-backed login rate limiting. Production deployment still requires manual
confirmation of strong secrets, production password hash, HTTPS, secure cookie
settings, session TTL policy, and explicit rate-limit parameters.
