# Stage 3.3.53 — Transit Worker Readonly Check Acceptance

## 1. Purpose

Stage 3.3.53 records the acceptance result for the first read-only Worker check on
the selected online transit server.

This stage is documentation-only. It records the database-observed result of the
previously approved read-only Worker check. It does not enqueue new Worker
commands, execute SSH, run read-only preflight, create transit routes, install
`socat` / `gost`, open ports, modify firewall rules, or perform cutover.

## 2. Preconditions

Previous stages:

- Stage 3.3.51 accepted that the selected transit Worker registered successfully
  and was online in the UI.
- Stage 3.3.52 approved one future read-only Worker check for the selected transit
  server.

Selected transit resource:

| Field | Value |
| --- | --- |
| Transit server name | `香港中转服务器` |
| Transit server IP | `163.223.216.108` |
| Resource type | `server` |
| Worker role | `transit` |
| Previous UI status | `在线` |

## 3. Read-only command result

The operator queried the local control-plane database after running the approved UI
`Worker 检查` action.

Observed command row:

| Field | Value |
| --- | --- |
| Worker command id | `ecd25b32-2630-4ca7-8e41-41fd7e0351ae` |
| Command type | `collect_status` |
| Status | `succeeded` |
| Attempts | `1` |
| Error message | empty |
| Created at | `2026-06-17 04:26:30.489191+00` |
| Claimed at | `2026-06-17 04:26:48.752861+00` |
| Completed at | `2026-06-17 04:26:48.82893+00` |

## 4. Acceptance result

Stage 3.3.53 accepts the read-only Worker check as successful.

Accepted observations:

- The Worker command was created.
- The Worker command type was `collect_status`.
- The Worker claimed the command.
- The Worker completed the command.
- The command status is `succeeded`.
- The command completed in one attempt.
- The command returned no error message.
- The result confirms the Worker command channel is functional for read-only status
  collection.

## 5. What this acceptance proves

This acceptance proves only:

- The selected transit Worker can receive a first-party read-only command from the
  control plane.
- The selected transit Worker can execute the `collect_status` command.
- The selected transit Worker can report command completion back to the control
  plane.
- The Worker command database state records the command as `succeeded`.

## 6. What this acceptance does not prove

This acceptance does not prove or authorize:

- A transit route exists.
- `socat` is installed or configured.
- `gost` is installed or configured.
- Any new listener port is open.
- Any cloud security group or cloud firewall allows a future listener port.
- Any server-local firewall rule is ready.
- The transit server can reach the accepted landing node.
- The transit server can forward traffic.
- A client can use a transit link.
- `nodes.share_link` has changed.
- cutover is ready.

Those checks require later planning and approval stages.

## 7. Current safe next step

Recommended next stage:

`Stage 3.3.54-transit-link-worker-readonly-plan`

That stage should move to the Transit Links layer and plan a future route without
creating it. It should select or record:

- the online transit server: `香港中转服务器` / `163.223.216.108`,
- the accepted landing node: `liveline-reality-27939`,
- a candidate TCP listener port from `10000-30000`,
- the intended forwarding method for future planning,
- no-op / read-only preflight boundaries,
- firewall and security-group confirmation requirements.

## 8. Explicit No-Go boundary for this stage

Stage 3.3.53 does not:

- enqueue additional Worker commands,
- execute SSH,
- run read-only preflight,
- create transit routes,
- install `socat`,
- install `gost`,
- create or modify systemd services,
- start, stop, or restart `socat` / `gost`,
- generate a transit client endpoint,
- generate or bind a listener port,
- open or modify cloud security groups,
- open or modify cloud firewalls,
- modify server-local firewall rules,
- modify iptables / nftables,
- modify Xray config,
- modify `nodes.share_link`,
- export full client links,
- create, delete, rebuild, or rotate nodes,
- run database migrations,
- deploy the public console,
- perform cutover.

## 9. Port and firewall reminder

This stage does not require opening a transit listener port.

A future stage that opens, reserves, binds, or changes a transit listener port must
remind the operator before execution:

1. Allow the selected TCP port in the cloud provider security group.
2. Allow the selected TCP port in the cloud firewall if separate from the security
   group.
3. Verify the server-local firewall state and allow the selected TCP port if the
   local firewall is active.
4. Confirm the selected port is not already used by SSH, web, database, Redis,
   console, Worker, Xray, or another transit route.

## 10. Sensitive-data handling

This document intentionally excludes:

- complete Worker install command,
- full one-time Worker token,
- Worker secret,
- full `vless://` links,
- full `nodes.share_link` values,
- Reality private keys,
- database passwords,
- full Xray configuration,
- provider credentials,
- SSH private keys.

## 11. Stage result

Stage 3.3.53 is complete when this document is committed.

Result:

- The first read-only transit Worker check is accepted as successful.
- The `collect_status` command completed with `succeeded`.
- Worker command channel readiness for read-only status collection is accepted.
- Transit route creation remains No-Go.
- `socat` / `gost` installation or modification remains No-Go.
- Listener port creation or firewall change remains No-Go.
- Cutover remains No-Go.
