# Stage 3.3.51 — Transit Worker Registration Acceptance

## 1. Purpose

Stage 3.3.51 records the acceptance result after the selected transit server's
LiveLine Worker was manually installed and registered.

This stage is documentation-only. It records UI-observed Worker registration and
heartbeat status. It does not run Worker commands, does not execute SSH, does not
create transit routes, does not install `socat` / `gost`, does not open ports, does
not modify firewall rules, and does not perform cutover.

## 2. Preconditions

Previous stages:

- Stage 3.3.48 reconciled the transit UI flow and recorded that Transit Servers is
  the resource onboarding layer while Transit Links is the route composition layer.
- Stage 3.3.49 approved manual Worker install for the selected transit server.
- Stage 3.3.50 added a recovery path for regenerating a one-time Worker install
  command for `pending_worker` transit resources.

Operator-side manual action before this acceptance record:

- The operator manually executed the system-generated Worker install command on the
  selected transit VPS.
- The complete command and one-time token were not shared in documentation or chat.

## 3. Accepted transit server

| Field | Value |
| --- | --- |
| Transit server name | `香港中转服务器` |
| Transit server IP | `163.223.216.108` |
| Resource type | `server` |
| Worker role | `transit` |
| UI status | `在线` |
| Worker status | `在线` |
| UI last heartbeat | `2026/6/17 12:09:48` |
| Acceptance source | Operator-provided LiveLine Console screenshot |

## 4. Acceptance result

Stage 3.3.51 accepts the transit Worker registration as successful based on the UI
state shown by the operator.

Accepted observations:

- The selected transit resource is visible in Transit Servers.
- The selected transit resource is no longer `pending_worker` in the UI.
- The selected transit resource displays `在线`.
- The Worker displays `在线`.
- The Worker is associated with the selected transit resource.
- The UI displays a recent heartbeat timestamp.
- The resource remains a transit server resource, not a transit route.

## 5. What this acceptance does not prove

This acceptance does not prove or authorize:

- A transit route exists.
- `socat` is installed or configured on the selected transit VPS.
- `gost` is installed or configured on the selected transit VPS.
- Any listener port is open on the selected transit VPS.
- Any cloud security group or cloud firewall allows a future transit listener port.
- The selected transit VPS can reach the accepted landing node.
- The selected transit VPS can forward traffic.
- A client can use a transit link.
- `nodes.share_link` has changed.
- cutover is ready.

Those checks require later stages.

## 6. Current safe next step

Recommended next stage:

`Stage 3.3.52-transit-worker-readonly-check-approval`

That stage should authorize only a read-only Worker check such as `collect_status`
or `service_status` for the selected transit resource.

The read-only check may inspect only non-mutating status facts such as:

- Worker status and version.
- Hostname.
- Interface name.
- OS / kernel summary.
- CPU / memory / disk summary.
- Read-only service status for `liveline-worker`, `socat`, and `gost`.

The read-only check must not create or modify transit routes.

## 7. Explicit No-Go boundary for this stage

Stage 3.3.51 does not:

- click or run `Worker 检查`,
- enqueue Worker commands,
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

## 8. Port and firewall reminder

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

## 9. Sensitive-data handling

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

## 10. Stage result

Stage 3.3.51 is complete when this document is merged.

Result:

- The selected transit Worker registration is accepted as successful.
- The selected transit resource is recorded as online in the UI.
- Worker heartbeat is recorded as present.
- No Worker command execution is authorized or performed by this stage.
- No transit route creation is authorized or performed by this stage.
- Next recommended stage is read-only Worker check approval.
