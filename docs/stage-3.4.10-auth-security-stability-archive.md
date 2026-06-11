# Stage 3.4.10 Auth Security Stability Archive

## Current Stage Conclusion

Stage 3.4.10 archives the stable baseline for the Stage 3.4 login and
authentication security module.

This stage is documentation-only. It does not change authentication logic,
business logic, database schema, `node.share_link`, listening ports, firewall
rules, backend tasks, or the current transit links.

## Stage 3.4 Completed Capability Overview

Stage 3.4 has completed the following Auth capabilities:

| Item | Archived result |
| --- | --- |
| Login gate | Completed |
| Unauthenticated frontend behavior | Only the login screen is shown |
| Successful login behavior | The operator enters the system panel |
| Logout behavior | Logout returns to the login screen |
| Protected backend APIs | Important APIs require authentication |
| Login failure rate limiting | Implemented |
| Rate-limit browser acceptance | Passed |
| Auth/session hardening plan | Archived |
| Production Auth environment readiness | Checked and documented |
| Production Auth guardrails | Implemented |
| Production guardrails acceptance | Passed |

## Current Auth Stable Baseline

The current Auth module baseline is:

| Baseline item | Status |
| --- | --- |
| Local development / local environment startup | Available |
| `/api/health` | Public and accessible |
| `/api/nodes` when unauthenticated | Returns `401` |
| `/api/vps` when unauthenticated | Returns `401` |
| `/api/tasks` when unauthenticated | Returns `401` |
| `/api/transit-routes` when unauthenticated | Returns `401` |
| `/api/transit-resources` when unauthenticated | Returns `401` |
| Wrong login before rate-limit threshold | Returns `401` |
| Repeated wrong login after threshold | Returns `429` |
| Rate-limit message | Generic, does not reveal whether an account exists |
| Correct password handling | Entered only through the browser during manual acceptance |
| Correct password storage in terminal/docs/logs/Git | Not written |
| Production weak `SESSION_SECRET` guardrail | Rejects unsafe configuration |
| Production `COOKIE_SECURE=false` guardrail | Rejects unsafe configuration |
| Missing production `ADMIN_PASSWORD_HASH` guardrail | Rejects unsafe configuration |
| Invalid production `COOKIE_SAMESITE` guardrail | Rejects unsafe configuration |
| Non-positive production `SESSION_TTL_SECONDS` guardrail | Rejects unsafe configuration |
| Non-positive production login rate-limit parameters | Rejects unsafe configuration |

## Current Production Link Stable Baseline

The current production transit baseline remains unchanged by Stage 3.4:

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |
| Stage 3.4 `node.share_link` changes | None |
| Stage 3.4 new listening ports | None |
| Stage 3.4 `socat` 8443 takeover | None |
| Stage 3.4 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.4 cutover activity | None |

Stage 3.4 is an Auth/security module stage. It did not alter the production
transit path. The `socat` 18443 formal link and `gost` 8443 fallback link
remain in their existing roles.

## Security Boundary Archive

The following security boundaries are archived for Stage 3.4.10:

- No real password is written to code, docs, terminal commands, logs, or Git.
- No real password hash is written to docs or reports.
- No real `SESSION_SECRET` value is written to docs or reports.
- No SSH Key is written to docs or reports.
- No Passphrase is written to docs or reports.
- No token is written to docs or reports.
- No complete node link is written to docs or reports.
- `node.share_link` is not read or modified in this stage.
- No database migration is added.
- No listening port is added.
- No SSH or remote command is executed.
- No backend Worker/RQ task is triggered.
- No firewall rule is modified.
- `socat` is not allowed to take over 8443 in this stage.
- `gost` 8443 is not closed, stopped, downgraded, or replaced.
- No cutover is performed.

## Follow-Up Suggestions

Future stages may separately review and implement:

- Production deployment preparation with a strong `SESSION_SECRET`.
- Production deployment preparation with a production `ADMIN_PASSWORD_HASH`.
- HTTPS deployment confirmation with `COOKIE_SECURE=true`.
- Auth audit logging.
- Session rotation and idle timeout behavior.
- Frontend role or permission boundaries.

Each follow-up must be handled in a separately approved stage and must preserve
the no-secret-in-docs boundary.

## Stage 3.4.10 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Final Archive Conclusion

Stage 3.4 Auth security is archived as a stable baseline. Login gate,
protected API enforcement, login failure rate limiting, session hardening
planning, production configuration readiness, production guardrails, and
guardrail acceptance are complete. The production transit links remain
unchanged: `socat` 18443 is the formal link and `gost` 8443 remains the
fallback link.
