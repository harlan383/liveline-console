# Stage 3.9.3 Readonly Preflight No-op API Acceptance Record

## Current Stage Conclusion

Stage 3.9.3 records local acceptance for the Stage 3.9.2 readonly preflight
no-op API scaffold.

Acceptance result: passed for the local no-op API scaffold baseline.

This stage is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, connect to remote servers, create
real forwarding, perform cutover, let `socat` take over 8443, or stop,
downgrade, or replace `gost` 8443.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## No-op API Path

`POST /api/transit-routes/readonly-preflight-plan`

The API is login protected, local, and no-op. It returns a readonly preflight
plan only.

## Local Service Acceptance

| Item | Result |
| --- | --- |
| `docker compose up --build -d` | Passed |
| `/api/health` backend | ok |
| `/api/health` database | ok |
| `/api/health` redis | ok |
| `/api/health` worker | ok |
| `http://localhost:3000` | HTTP 200 |
| Redis `temp_credential:*` | 0 |
| pending / running tasks | 0 |

## Access Control Acceptance

| Item | Result |
| --- | --- |
| Unauthenticated `POST /api/transit-routes/readonly-preflight-plan` | Returned `401` |
| API remains protected by login | Passed |
| Real username/password written to terminal | No |
| Real username/password written to docs or logs | No |

Authenticated browser-session testing must be done only through a safe browser
session or another approved secure test method. This record does not write real
credentials to terminal commands, docs, logs, screenshots, or Git.

## Port Rule Acceptance

The local no-op plan logic was validated with non-sensitive test data.

| Input | Result |
| --- | --- |
| `planned_listen_port = 8443` | `blocked`, `ready=false` |
| `planned_listen_port = 18443` | `blocked`, `ready=false` |
| `planned_listen_port = 22` | `blocked`, `ready=false` |
| `planned_listen_port = 20575` | `blocked`, `ready=false` |
| Empty planned listen port | `blocked`, `ready=false` |
| Out-of-range planned listen port | `blocked`, `ready=false` |
| Valid high port without firewall / backup / approval confirmations | `no_go`, `ready=false` |
| Valid high port with all local confirmations | `ready`, `ready=true` |

The `ready=true` response summary states:

`Ready for readonly preflight approval / execution stage. This does not authorize real forwarding.`

Ready does not mean real forwarding can be created.

## No-side-effect Acceptance

| Item | Result |
| --- | --- |
| Database route record created | No |
| Task created | No |
| Redis temporary credential written | No |
| SSH executed | No |
| Remote command executed | No |
| Remote server connected | No |
| Real forwarding created | No |
| Real listening port added | No |
| `node.share_link` modified | No |
| Cutover performed | No |
| Redis `temp_credential:*` after validation | 0 |
| pending / running tasks after validation | 0 |

## Response Structure Acceptance

The no-op response contains these top-level fields:

- `ready`
- `blocked`
- `status`
- `summary`
- `next_action`
- `checks`
- `safety_boundary`
- `redacted_summary`

The returned `checks` list includes:

- `transit_resource_selected`
- `landing_node_selected`
- `planned_port_valid`
- `planned_port_not_reserved`
- `landing_target_port_valid`
- `firewall_confirmations_present`
- `local_backup_confirmed`
- `user_approved_readonly_preflight`
- `no_cutover_confirmed`
- `no_node_share_link_change_confirmed`
- `workbuddy_authorization_status`
- `future_transit_reachable`
- `future_planned_port_available`
- `future_formal_socat_18443_preserved`
- `future_fallback_gost_8443_preserved`
- `future_transit_to_landing_tcp_connectivity`

Future checks are returned as `skipped` and explicitly mean future checks were
not executed in this stage.

## Redaction Acceptance

The validation output did not contain:

- Complete node links.
- SSH keys.
- Passwords.
- Tokens.
- Real `SESSION_SECRET` values.
- Real `ADMIN_PASSWORD_HASH` values.
- Cookie or session content.
- Complete `node.share_link` values.

## Current Link Protection

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.9.3 does not read or modify `node.share_link`.
- Stage 3.9.3 does not add real listening ports.
- Stage 3.9.3 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.9.3 does not let `socat` take over 8443.
- Stage 3.9.3 does not overwrite `socat` 18443.
- Stage 3.9.3 does not perform cutover.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.9.3 because this stage only records local
no-op API acceptance.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login.
- Real remote read-only preflight.
- Real remote port checks.
- Real `socat` or `gost` service checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Safety Boundary

This stage maintains the following boundaries:

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH keys.
- Do not write passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not connect to remote servers.
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not create real forwarding.
- Do not let `socat` take over 8443.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Frontend function modified | No |
| Backend logic modified | No |
| Script added | No |
| Real backup file generated | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| Complete node link read or output | No |
| SSH or remote command executed | No |
| Remote server connected | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
