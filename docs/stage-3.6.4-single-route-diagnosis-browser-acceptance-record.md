# Stage 3.6.4 Single Route Diagnosis Browser Acceptance Record

## Current Stage Conclusion

Stage 3.6.4 records the browser manual acceptance result after Stage 3.6.2
single-route create safety gates and Stage 3.6.3 single-route diagnosis polish
were merged.

Browser manual acceptance passed.

This stage is documentation-only. It does not modify code, frontend behavior,
backend logic, database schema, scripts, `node.share_link`, listening ports,
firewall rules, route state, or remote services.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Acceptance Environment

| Item | Value |
| --- | --- |
| Environment | Local single-user console |
| URL | `http://localhost:3000` |
| Deployment model | Local Mac usage only |
| Public production deployment | Not used |
| Workbuddy required for this stage | No |

## Browser Acceptance Items

| Item | Result |
| --- | --- |
| Login page displays at `http://localhost:3000` | Passed |
| Correct username and password entered in browser can open system panel | Passed |
| Single-route page opens | Passed |
| `8443` is blocked or clearly marked as reserved for `gost` fallback | Passed |
| `18443` is blocked or clearly marked as the formal `socat` route that must not be overwritten | Passed |
| Invalid port input has a clear message | Passed |
| Cloud security group / cloud firewall / server firewall reminder is clear before port changes | Passed |
| Diagnosis result display is clearer than before | Passed |
| Diagnosis result distinguishes `listen_check`, `process_check`, `target_connectivity`, and `service_status` | Passed |
| Task status, current step, progress, failure summary, and next action are visible | Passed |
| Complete node links are not displayed | Passed |
| SSH Key, password, token, and `SESSION_SECRET` are not displayed | Passed |
| Page states diagnosis does not modify `node.share_link` | Passed |
| Page states diagnosis does not perform cutover | Passed |
| Page states diagnosis does not close `gost 8443` | Passed |
| Page states diagnosis does not let `socat` take over `8443` | Passed |
| Logout returns to the login page | Passed |

## Current Auth / UI Status

- Login gate is active.
- Important APIs remain protected by login.
- Single-route create safety gates are active.
- Single-route diagnosis display is polished.
- Route safety reminders remain visible.
- Complete node links and sensitive values are not shown in normal UI display.

## Current Production Route Impact

| Item | Result |
| --- | --- |
| `socat 18443` formal link | Unchanged |
| `gost 8443` fallback link | Unchanged |
| `node.share_link` | Not modified in this stage |
| New listening port | None |
| Remote command | None |
| Backend task trigger | None |
| Cutover | None |

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.6.4 because this stage only records browser
manual acceptance results.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login.
- Real remote route creation.
- Real remote listening-port checks.
- Real remote diagnosis.
- Formal `node.share_link` cutover or rollback.

## Security Notes

- The real password was entered only in the browser.
- The real password was not written into this document.
- The real password was not written into terminal commands.
- The real password was not written into logs.
- The real password was not written into Git.
- No screenshots containing real passwords were recorded.
- Complete node links were not written into this document.

## Security Boundary

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not modify firewall rules.
- Do not let `socat` take over `8443`.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Stage Conclusion

Stage 3.6.2 and Stage 3.6.3 browser acceptance passed. The local operator can
see the login gate, protected-port warnings, single-route safety boundaries, and
clearer diagnosis results. The stage records acceptance only and does not change
current route state.
