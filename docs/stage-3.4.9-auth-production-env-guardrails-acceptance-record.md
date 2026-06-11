# Stage 3.4.9 Auth Production Environment Guardrails Acceptance Record

## Stage Goal

Stage 3.4.9 records the acceptance result after Stage 3.4.8 Auth production
environment guardrails were merged.

This stage is an acceptance-record stage only. It does not modify
authentication logic, business code, production link state, or any remote
system.

## Current Auth State

- Stage 3.4.1 login gate is implemented.
- Stage 3.4.2 local browser login acceptance passed.
- Stage 3.4.3 protected API sweep passed.
- Stage 3.4.4 Auth/session hardening plan is documented.
- Stage 3.4.5 login failure rate limiting is implemented.
- Stage 3.4.6 browser acceptance for rate limiting passed.
- Stage 3.4.7 production Auth environment readiness check is documented.
- Stage 3.4.8 production Auth environment guardrails are implemented.
- Login gate is active.
- Login failure rate limiting is active.
- Important backend APIs are protected by login checks.

## Local Development Acceptance

| Check | Result |
| --- | --- |
| `docker compose up --build -d` after Stage 3.4.8 merge | Passed |
| `/api/health` is accessible | Passed |
| `/api/health` reports backend/database/redis/worker ok | Passed |
| `http://localhost:3000` returns 200 | Passed |
| Login page displays in the browser | Passed |
| Correct username and password can enter the system panel | Passed by browser-only manual acceptance |
| Logout returns to the login page | Passed by browser-only manual acceptance |
| Wrong login still returns `401` before the threshold | Passed |
| Repeated wrong login attempts still return `429 AUTH_RATE_LIMITED` at threshold | Passed |

The correct password was entered only in the browser. It was not written to
terminal commands, documents, logs, or Git.

## Production Guardrails Simulation Acceptance

All production simulations used fake values or placeholders only. No real
secret, real password hash, real password, cookie, session, token, SSH key, or
full node link was used or written.

| Simulation | Result |
| --- | --- |
| `APP_ENV=production` with weak `SESSION_SECRET` | Rejected |
| `APP_ENV=production` with `COOKIE_SECURE=false` | Rejected |
| `APP_ENV=production` with missing `ADMIN_PASSWORD_HASH` | Rejected |
| `APP_ENV=production` with invalid `COOKIE_SAMESITE` | Rejected |
| `APP_ENV=production` with non-positive `SESSION_TTL_SECONDS` | Rejected |
| `APP_ENV=production` with non-positive `AUTH_LOGIN_MAX_ATTEMPTS` | Rejected |
| `APP_ENV=production` with non-positive `AUTH_LOGIN_WINDOW_SECONDS` | Rejected |
| `APP_ENV=production` with non-positive `AUTH_LOGIN_LOCK_SECONDS` | Rejected |
| `APP_ENV=production` with valid-shape fake configuration | Accepted |

The failure messages identify the invalid setting and requirement, but do not
print real `SESSION_SECRET`, real `ADMIN_PASSWORD_HASH`, password, cookie,
session, token, or full node-link values.

## System Security State Acceptance

| Check | Result |
| --- | --- |
| Unauthenticated `/api/nodes` returns `401` | Passed |
| Unauthenticated `/api/transit-routes` returns `401` | Passed |
| Unauthenticated `/api/transit-resources` returns `401` | Passed |
| `/api/health` remains public | Passed |
| Redis `temp_credential:*` remains empty | Passed |
| Pending / running tasks remain `0` | Passed |

## Current Production Link Boundary

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

Stage 3.4.8 production Auth environment guardrails passed local development
acceptance and production-configuration simulation acceptance. The system keeps
working in local development, rejects unsafe production Auth configuration, and
preserves the current production transit links.
