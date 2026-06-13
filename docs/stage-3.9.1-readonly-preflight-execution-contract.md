# Stage 3.9.1 Readonly Preflight Execution Contract

## Current Stage Conclusion

Stage 3.9.1 documents the future execution contract for a single-route remote
read-only preflight. It defines the proposed request fields, response fields,
task result shape, check item structure, safety boundaries, redaction rules,
and frontend display expectations for a later Workbuddy-authorized stage.

Current conclusion: contract documented; real remote execution remains No-Go.

This stage is documentation-only. It does not modify code, frontend behavior,
backend logic, Worker/RQ jobs, scripts, database schema, `node.share_link`,
listening ports, firewall rules, current route state, or current transit links.
It does not execute SSH or remote commands, connect to remote servers, trigger
backend tasks, create real forwarding, perform cutover, let `socat` take over
8443, or stop, downgrade, or replace `gost` 8443.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Current Implementation Review

The current implementation already provides these relevant primitives:

| Area | Current behavior |
| --- | --- |
| `frontend/lib/api.ts` | Defines `TaskData` with `task_type`, `status`, `current_step`, `progress`, `result_data`, and timestamps |
| `frontend/components/TransitRoutesPanel.tsx` | Contains the single-route page, local dry-run planner, readonly preflight framework, local Go / No-Go rules, and redacted summary text |
| `frontend/components/TaskHistoryPanel.tsx` | Displays task status, failure summaries, logs, and sanitized `result_data` / `raw_output` |
| `backend/app/api/routes/tasks.py` | Protects task list/detail/log APIs and serializes task fields |
| `backend/app/models/task.py` | Stores task type, status, current step, progress, errors, JSON `result_data`, and timestamps |
| `backend/app/api/routes/transit_routes.py` | Contains existing route create / diagnose / restart endpoints and protected-port checks |
| `backend/app/schemas/transit_route.py` | Defines protected create ports `22`, `8443`, `18443`, and `20575` |
| `backend/app/worker/ssh_transit_diagnose.py` | Existing real route diagnosis result shape includes route summary, checks, hints, warnings, failures, and sanitized command output |

Stage 3.9.1 does not connect these primitives to a new execution endpoint.
The contract below is for a future stage only.

## Future Endpoint / Task Naming

Future endpoint candidate:

- `POST /api/transit-routes/readonly-preflight`

Future task type candidate:

- `single_route_readonly_preflight`

The endpoint and task type are not implemented in this stage. If implemented
later, they must remain separate from real route creation and formal cutover.

## Future Request Contract

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `transit_resource_id` | string | Yes | Selected transit server resource id |
| `transit_resource_name` | string | Yes | Display name only; not an authority source |
| `transit_host_hint` | string | Yes | Redacted or partial host hint only |
| `landing_node_id` | string | Yes | Selected active landing node id |
| `landing_node_name` | string | Yes | Display name only; not an authority source |
| `landing_host_hint` | string | Yes | Redacted or partial host hint only |
| `landing_target_port` | integer | Yes | Target TCP port on the landing side |
| `planned_listen_port` | integer | Yes | Planned transit listen port, must pass protected-port rules |
| `route_purpose` | string | Yes | Target platform or route purpose |
| `firewall_security_group_confirmed` | boolean | Yes | Cloud security group confirmation |
| `cloud_firewall_confirmed` | boolean | Yes | Cloud firewall confirmation |
| `server_firewall_confirmed` | boolean | Yes | Server firewall confirmation |
| `local_backup_confirmed` | boolean | Yes | Local DB backup confirmation |
| `user_approved_readonly_preflight` | boolean | Yes | User approval for read-only preflight only |
| `workbuddy_authorized` | boolean | Yes | Whether Workbuddy remote read-only execution is explicitly authorized |
| `no_cutover_confirmed` | boolean | Yes | Confirms this is not a cutover stage |
| `no_node_share_link_change_confirmed` | boolean | Yes | Confirms `node.share_link` must not be modified |

The request must never include real SSH keys, passphrases, passwords, tokens,
complete node links, complete `node.share_link` values, or real secret values.

## Future Response Contract

Immediate response after accepting a future request should be task-oriented:

| Field | Type | Notes |
| --- | --- | --- |
| `task_id` | string | New task id if execution is accepted |
| `task_type` | string | Expected value: `single_route_readonly_preflight` |
| `status` | string | Initial value such as `pending` |
| `current_step` | string | Initial step, for example `queued` |
| `progress` | integer | Initial progress, for example `0` |
| `passed` | boolean | `false` until checks complete |
| `blocked` | boolean | `true` if preflight is rejected before execution |
| `checks` | array | Check items, empty or planned at enqueue time |
| `summary` | string | Redacted summary only |
| `next_action` | string | Human-readable next step |
| `safety_boundary` | object | Safety flags carried forward |
| `redacted_outputs` | object | Optional sanitized evidence summaries |
| `created_at` / `updated_at` | string | Reuse existing task timestamps when available |

If the future API refuses the request, it should return a clear error code and
message without printing sensitive input values.

## Future Task Result Contract

Future `tasks.result_data` should use a predictable object shape:

```json
{
  "classification": "single_route_readonly_preflight",
  "passed": false,
  "blocked": true,
  "go_no_go": "No-Go",
  "summary": "Readonly preflight blocked before remote execution.",
  "next_action": "Complete required confirmations and request approval again.",
  "request_summary": {
    "transit_resource_id": "<uuid>",
    "transit_resource_name": "<redacted display name>",
    "transit_host_hint": "<redacted host hint>",
    "landing_node_id": "<uuid>",
    "landing_node_name": "<redacted display name>",
    "landing_host_hint": "<redacted host hint>",
    "planned_listen_port": 0,
    "landing_target_port": 0,
    "route_purpose": "<purpose>"
  },
  "checks": [],
  "safety_boundary": {},
  "redacted_outputs": {},
  "warnings": [],
  "failures": []
}
```

This shape is illustrative only. It must not include complete node links, SSH
keys, passphrases, passwords, tokens, complete command output, complete
`node.share_link`, cookie / session content, real `SESSION_SECRET` values, or
real `ADMIN_PASSWORD_HASH` values.

## Check Item Structure

Each future check item should use this structure:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable machine-readable check id |
| `label` | string | Human-readable label |
| `category` | string | Example: `remote`, `local`, `firewall`, `route_safety` |
| `status` | string | One of `pending`, `running`, `passed`, `failed`, `skipped`, `blocked` |
| `passed` | boolean | `true` only when the check clearly passed |
| `message` | string | Redacted user-facing summary |
| `evidence_summary` | string | Redacted evidence, never raw sensitive output |
| `next_action` | string | Suggested next step |
| `sensitive_output_redacted` | boolean | Must be `true` when output was sanitized |

## Check Status Definitions

| Status | Meaning |
| --- | --- |
| `pending` | Check is planned but has not started |
| `running` | Check is currently executing |
| `passed` | Check completed successfully |
| `failed` | Check ran and found a failure |
| `skipped` | Check was intentionally not run because it did not apply |
| `blocked` | Check cannot run because a required approval, confirmation, target, or safety condition is missing |

## Future Check List

| Check id | Category | Purpose |
| --- | --- | --- |
| `transit_reachable` | `remote` | Confirm the transit server can be reached by authorized read-only SSH |
| `planned_port_available` | `remote` | Confirm the planned listen port is not already occupied |
| `formal_socat_18443_preserved` | `route_safety` | Confirm 18443 remains the formal `socat` route and is not being overwritten |
| `fallback_gost_8443_preserved` | `route_safety` | Confirm 8443 remains reserved for `gost` fallback |
| `gost_status_readonly` | `remote` | Read `gost` service / process status only |
| `socat_status_readonly` | `remote` | Read `socat` service / process status only |
| `transit_to_landing_tcp_connectivity` | `remote` | Read-only TCP connectivity check from transit to landing target |
| `server_firewall_readonly` | `remote` | Read server firewall state only |
| `local_health_ok` | `local` | Confirm local health is OK |
| `task_queue_clear` | `local` | Confirm pending / running tasks are clear |
| `firewall_confirmations_present` | `firewall` | Confirm cloud security group, cloud firewall, and server firewall confirmations are present |

All remote checks are future-only. They must not run until a later stage
explicitly authorizes Workbuddy or an equivalent remote execution path.

## Go / No-Go Result Fields

Future result data should include:

- `go_no_go`: one of `Go`, `No-Go`, or `Blocked`.
- `passed`: boolean summary of all required checks.
- `blocked`: boolean summary of whether execution was prevented by missing
  approvals or safety gates.
- `blocking_reasons`: list of redacted reasons.
- `next_action`: concise next step for the operator.
- `workbuddy_authorized`: boolean copied from approved request state.
- `remote_execution_authorized`: boolean derived from all approval gates.

`Ready` in the local UI must remain limited to readiness for a later approval
stage. It must not be interpreted as permission to execute remotely.

## Workbuddy Authorization Boundary Fields

Future request and result data should preserve these approval flags:

- `workbuddy_authorized`.
- `user_approved_readonly_preflight`.
- `no_cutover_confirmed`.
- `no_node_share_link_change_confirmed`.
- `no_real_forwarding_confirmed`.
- `no_new_listen_port_confirmed`.
- `no_firewall_modification_confirmed`.
- `no_service_restart_confirmed`.

If any required flag is missing or false, the future backend must refuse remote
execution and return No-Go / Blocked.

## Backend Safety Contract

If a future backend readonly preflight endpoint is added, it must enforce:

- Unauthenticated requests return `401`.
- Remote execution is refused unless Workbuddy is explicitly authorized.
- Remote execution is refused unless `user_approved_readonly_preflight` is true.
- Remote execution is refused when target transit resource, landing node, or
  ports are missing.
- Remote execution is refused when `planned_listen_port` is `8443`, `18443`,
  `22`, or `20575`.
- Remote execution is refused until cloud security group, cloud firewall, and
  server firewall confirmations are present.
- It must not create a route.
- It must not create or modify systemd services.
- It must not start, stop, restart, enable, or disable services.
- It must not modify firewall rules.
- It must not modify `node.share_link`.
- It must not generate complete node links.
- It must not write temporary credentials unless a later stage separately
  designs and approves that credential path.
- It must not leak SSH keys, passphrases, tokens, passwords, cookie / session
  values, real `SESSION_SECRET` values, or complete node links.
- It must not enqueue any task unless all future approval gates pass.

## Frontend Display Contract

Future frontend display should:

- Show only redacted summaries.
- Never show complete node links.
- Never show SSH keys, passphrases, passwords, tokens, cookie / session values,
  real `SESSION_SECRET` values, or real `ADMIN_PASSWORD_HASH` values.
- Show each check item status clearly.
- Show failure reason summaries.
- Show next-action guidance.
- Mark the feature as `readonly preflight only`.
- Clearly state that it does not create real forwarding.
- Clearly state that it does not modify `node.share_link`.
- Clearly state that it does not perform cutover.
- Clearly state that real execution requires Workbuddy authorization in a later
  stage.

## Redaction Rules

Future request summaries, task results, task logs, and frontend views must:

- Redact complete node links and protocol URLs.
- Redact any field whose key indicates private key, passphrase, password,
  secret, token, cookie, session, or admin password hash content.
- Truncate long command output.
- Store only evidence summaries when possible.
- Avoid writing raw command output unless sanitized.
- Avoid writing complete IP / credential / node details when a partial hint is
  enough.
- Never write real SSH keys, passphrases, passwords, tokens, real
  `SESSION_SECRET` values, or complete node links to docs, logs, task results,
  or Git.

## Current Link Protection

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.9.1 does not read or modify `node.share_link`.
- Stage 3.9.1 does not add real listening ports.
- Stage 3.9.1 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.9.1 does not let `socat` take over 8443.
- Stage 3.9.1 does not overwrite `socat` 18443.
- Stage 3.9.1 does not perform cutover.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.9.1 because this stage only documents the
future contract.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login.
- Real remote read-only preflight.
- Real remote port occupancy checks.
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

## Future Recommendations

- A later stage may decide whether to add TypeScript-only contract types.
- A later stage may decide whether to add Pydantic schema drafts.
- A later stage must separately approve any backend endpoint.
- A later stage must separately approve any Workbuddy remote read-only
  execution.
- Real forwarding creation must be separately approved.
- Candidate link acceptance must be recorded separately after client testing.
- Formal `node.share_link` cutover must enter a separate approval stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Backend interface added | No |
| Frontend function modified | No |
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
