# Stage 3.3.62 — Transit Worker Remote Readonly Preflight API Design

## Purpose

This stage defines the API and Worker command contract for remote readonly transit preflight.

This is a design-only stage. It does not implement the API, does not add Worker behavior, and does not run remote checks.

## Contract name

Proposed Worker command type:

`transit_readonly_preflight`

This command type is reserved for non-mutating transit preflight probes.

## Request contract

The control plane should create the command with a structured payload containing only validated planning inputs:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `transit_resource_id` | string | yes | Selected transit resource id. |
| `landing_node_id` | string | yes | Selected landing node id. |
| `planned_listen_port` | number | yes | Planned transit listener port. |
| `landing_target_port` | number | yes | Landing-side target port. |
| `forwarding_method` | string | yes | Planned method, initially `socat`. |
| `purpose` | string | no | Short label for the plan. |
| `readonly` | boolean | yes | Must be `true`. |

The payload must not contain arbitrary shell, private keys, full client links, Worker tokens, or credentials.

## Backend validation rules

Before creating the Worker command, the API should verify:

- transit resource exists,
- transit resource type is `server`,
- transit resource is Worker-online,
- transit Worker role is `transit`,
- landing node exists,
- landing node is active,
- planned ports are valid numeric TCP ports,
- protected ports are rejected,
- `readonly` is explicitly true,
- the command target Worker supports this command type.

If any validation fails, the API should return a blocked response and avoid creating a Worker command.

## Worker allowlist

The Worker should implement this command using a fixed allowlist of read-only probes only.

Allowed result categories:

- worker identity and version,
- planned port occupancy status,
- `socat` service or process status,
- `gost` service or process status,
- transit-to-landing TCP reachability status,
- local firewall status as a read-only fact,
- short redacted diagnostic details.

The Worker must not accept arbitrary command strings from the payload.

## Result contract

The Worker should return a structured result such as:

| Field | Type | Description |
| --- | --- | --- |
| `passed` | boolean | True only when all required checks pass. |
| `status` | string | `passed`, `blocked`, or `failed`. |
| `summary` | string | Short redacted result summary. |
| `checks` | array | Per-check structured results. |

Each check item should include:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Stable check id. |
| `label` | string | Human-readable label. |
| `status` | string | `passed`, `blocked`, `failed`, or `skipped`. |
| `passed` | boolean | Per-check pass flag. |
| `detail` | string | Redacted detail text. |

Raw output should be omitted by default. If retained for troubleshooting, it must be redacted and truncated.

## Frontend behavior

The Transit Links page should only expose the remote readonly preflight action after local plan validation succeeds.

The UI should show:

- submitted Worker command id,
- command status,
- per-check result rows,
- redacted summary,
- clear No-Go warning for real creation.

The real creation path must remain unavailable until a later explicit creation approval stage.

## Audit and logging

The API should record an audit event when the command is requested.

Logs and task results must exclude:

- full proxy links,
- Worker tokens,
- Worker secrets,
- private keys,
- database passwords,
- provider credentials.

## No-Go boundary

This design does not authorize route creation, service installation, config writes, service restarts, listener binding, firewall changes, Xray changes, `nodes.share_link` changes, full link export, or cutover.

## Recommended next stage

Recommended next stage:

`Stage 3.3.63-transit-worker-remote-readonly-preflight-api-implementation`

That stage may implement the backend API and Worker command handler while keeping real route creation disabled.

## Result

Stage 3.3.62 records the API and Worker command contract for remote readonly transit preflight. Real execution remains No-Go.
