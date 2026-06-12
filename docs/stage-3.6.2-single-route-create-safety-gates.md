# Stage 3.6.2 Single Route Create Safety Gates

## Current Stage Conclusion

Stage 3.6.2 adds safety gates to the single-route create flow. It improves the
local UI warnings and backend listen-port validation so route creation cannot be
mistaken for formal cutover and protected ports cannot be reused accidentally.

This stage does not execute SSH, run remote commands, create real remote
forwarding, add real listening ports, modify `node.share_link`, trigger backend
tasks, or perform cutover.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Modified Files

| File | Change |
| --- | --- |
| `frontend/components/TransitRoutesPanel.tsx` | Added single-route create safety copy, protected-port validation, safer defaults, and disabled confirmation / submit behavior for unsafe listen ports |
| `frontend/app/globals.css` | Added a small danger text style for inline validation feedback |
| `backend/app/schemas/transit_route.py` | Added protected create-port constants and user-facing validation messages |
| `backend/app/api/routes/transit_routes.py` | Rejects protected listen ports before credential handling or task enqueue |
| `README.md` | Added Stage 3.6.2 scope and status |
| `docs/stage-3.6.2-single-route-create-safety-gates.md` | Records this stage's safety gates, validation rules, and boundaries |

## Safety Gates Added

The single-route create page now states:

- Creating a route is not formal cutover.
- Creating a route does not modify `node.share_link`.
- Changing `node.share_link` requires a separate formal cutover approval stage.
- True remote route creation or remote port checks require Workbuddy or a
  separate authorized stage.
- New or changed listening ports require cloud security group, cloud firewall,
  and server firewall checks before real creation.

The create confirmation is blocked while the listen port is invalid or
protected. The submit button also stays disabled while the port is invalid or
protected.

## Port Validation Rules

The frontend validates listen-port input before route submission:

| Rule | Result |
| --- | --- |
| Empty value | Rejected with a clear message |
| Non-numeric value | Rejected |
| Decimal, negative, or signed value | Rejected |
| Port below `1` or above `65535` | Rejected |
| `22` | Rejected because it is the SSH port |
| `8443` | Rejected because it is reserved for the `gost` fallback route |
| `18443` | Rejected because it is the current formal `socat` route |
| `20575` | Rejected because it is the historical problem port |

The backend also rejects protected ports through `POST /api/transit-routes`
before resource lookup, node lookup, temporary credential handling, or
Worker/RQ task creation can proceed.

## Current Route Protection

| Item | Boundary |
| --- | --- |
| `8443` | Reserved for `gost` fallback; must not be used for new socat routes |
| `18443` | Current formal `socat` route; must not be overwritten or reused |
| `node.share_link` | Not modified by route creation |
| Formal cutover | Separate approval stage only |
| New listening port | Requires cloud security group, cloud firewall, and server firewall checks |

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.6.2 because this stage only updates local
UI validation, backend input validation, and documentation.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login.
- Real remote route creation.
- Real remote listening-port checks.
- Real remote diagnosis.
- Any formal `node.share_link` cutover or rollback.

## Impact Record

| Item | Result |
| --- | --- |
| Modified business logic | Minimal backend input validation only |
| Modified frontend display | Yes |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Read or output complete node link | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

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

The single-route create flow now has explicit safety gates for the two protected
production-adjacent ports: `8443` for the `gost` fallback route and `18443` for
the formal `socat` route. Route creation remains separate from formal cutover,
and any future real remote creation or diagnosis must be explicitly authorized.
