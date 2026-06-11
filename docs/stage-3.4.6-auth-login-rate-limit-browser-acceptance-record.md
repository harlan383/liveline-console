# Stage 3.4.6 Auth Login Rate Limit Browser Acceptance Record

## Stage Result

Stage 3.4.6 records the manual browser acceptance result for the Stage 3.4.5
auth login rate-limit hardening.

Acceptance passed in the local browser. This stage is an acceptance-record
stage only. It does not modify authentication logic, business code, production
link state, or any remote system.

## Acceptance Environment

- Environment: local browser
- URL: `http://localhost:3000`
- Scope: browser-visible login gate and rate-limit behavior after Stage 3.4.5
- Real admin password handling: entered only in the browser

## Browser Acceptance Checklist

| Check | Result |
| --- | --- |
| Open `http://localhost:3000` and show only the login page | Passed |
| Correct username and password can enter the system panel | Passed |
| Logout returns to the login page | Passed |
| Wrong password before the threshold shows login failure | Passed |
| Repeated wrong attempts reaching the threshold show a generic rate-limit message | Passed |
| Rate-limit message does not reveal whether the account exists | Passed |
| After logout, the system panel is no longer visible | Passed |

## Password Handling

- The real password was entered only in the browser.
- The real password was not written to this document.
- The real password was not written to terminal commands.
- The real password was not written to logs.
- The real password was not written to Git.
- No screenshot containing a real password was recorded.

## Current Auth State

- The login gate is active.
- Important backend APIs are protected by login checks.
- Login failure rate limiting is active.
- `401` responses still send unauthenticated users back to the login flow.
- `429 AUTH_RATE_LIMITED` shows a generic rate-limit message.
- The frontend does not store plaintext passwords, password hashes, tokens, or
  session values in localStorage or sessionStorage.

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

Stage 3.4.5 login rate-limit hardening is accepted in the local browser. The
manual acceptance confirms that login, logout, pre-threshold failure, threshold
rate limiting, generic rate-limit messaging, and post-logout panel hiding work
as expected without exposing the real password or affecting the current transit
links.
