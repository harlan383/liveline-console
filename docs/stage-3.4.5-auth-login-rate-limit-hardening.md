# Stage 3.4.5 Auth Login Rate Limit Hardening

## Stage Goal

Stage 3.4.5 adds login failure rate limiting to `POST /api/auth/login` to reduce
password-guessing and brute-force risk.

This stage is an Auth security hardening implementation stage. It does not
change production link state and does not perform any network or cutover
operation.

## Implemented Rate Limit Strategy

- Scope: `POST /api/auth/login` only.
- Dimension: client IP + submitted username.
- Redis storage: existing Redis is used.
- Redis key shape: the IP + username identifier is HMAC-hashed with
  `SESSION_SECRET`; the Redis key does not contain plaintext username,
  password, password hash, cookie, session token, or CSRF token.
- Failed attempts:
  - Failed login attempts increment a short-lived counter.
  - When the counter reaches the configured threshold, the key is locked for the
    configured lock duration.
- Locked attempts:
  - A locked IP + username pair receives `429 AUTH_RATE_LIMITED`.
  - The response message remains generic: `登录尝试过多，请稍后再试。`
- Successful login:
  - A successful login clears the failure counter and lock key for that IP +
    username pair.
- Redis failure behavior:
  - Redis errors do not leak sensitive details.
  - The login flow does not write passwords or hashes into logs or Redis keys.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUTH_LOGIN_MAX_ATTEMPTS` | `5` | Maximum failed attempts in the window before lock. |
| `AUTH_LOGIN_WINDOW_SECONDS` | `600` | Failed-attempt counting window. |
| `AUTH_LOGIN_LOCK_SECONDS` | `900` | Temporary lock duration after the threshold is reached. |

`.env.example` contains placeholders and default numeric values only. It must
not contain real passwords, real password hashes, real `SESSION_SECRET` values,
SSH keys, Passphrases, tokens, or full node links.

## Frontend Behavior

- `LoginScreen` shows a generic rate-limit message when the login API returns
  `AUTH_RATE_LIMITED`.
- The frontend does not store plaintext passwords, password hashes, tokens, or
  session values in localStorage or sessionStorage.
- The frontend does not reveal whether the username exists or which field is
  wrong.

## Local Acceptance Results

| Check | Result |
| --- | --- |
| Wrong password returns `401` before threshold | Passed |
| Repeated wrong attempts reach rate limit | Passed |
| Rate-limited login returns `429 AUTH_RATE_LIMITED` | Passed |
| Rate-limit message is generic | Passed |
| `/api/health` remains public | Passed |
| Unauthenticated protected API access remains `401` | Passed |
| Redis `temp_credential:*` remains empty | Passed |
| Pending / running tasks remain `0` | Passed |

Correct-password browser login remains a manual acceptance step because the real
admin password must not be written to terminal commands, logs, documents, or
Git. The rate limiter clears the corresponding failure counter after successful
login.

## Modified Files

- `backend/app/api/routes/auth.py`
- `backend/app/core/config.py`
- `backend/app/services/auth_rate_limit.py`
- `frontend/components/LoginScreen.tsx`
- `.env.example`
- `README.md`
- `docs/stage-3.4.5-auth-login-rate-limit-hardening.md`

No database migration was added.

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

Stage 3.4.5 adds Redis-backed login failure rate limiting with configurable
threshold, window, and lock duration. The implementation uses hashed Redis keys
and generic error messages, preserving the existing HttpOnly session login flow.
