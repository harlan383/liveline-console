# Stage 3.3.52 — Transit Worker Readonly Check Approval

## 1. Purpose

Stage 3.3.52 records approval for one read-only Worker check on the selected
online transit server.

This stage is documentation-only. It authorizes a later operator UI action to run
one `Worker 检查` / read-only Worker command against the selected transit resource.
This document itself does not click the UI button, does not enqueue a Worker
command, does not execute SSH, does not create transit routes, does not install
`socat` / `gost`, does not open ports, does not modify firewall rules, and does not
perform cutover.

## 2. Preconditions

Previous stages:

- Stage 3.3.49 approved manual Worker install on the selected transit server.
- Stage 3.3.50 added recovery for regenerating a one-time Worker install command.
- Stage 3.3.51 accepted that the selected transit Worker is registered and online.

Accepted transit resource:

| Field | Value |
| --- | --- |
| Transit server name | `香港中转服务器` |
| Transit server IP | `163.223.216.108` |
| Resource type | `server` |
| Worker role | `transit` |
| UI status | `在线` |
| Last recorded heartbeat | `2026/6/17 12:09:48` |

## 3. Recommendation

Recommendation: **Approve one read-only Worker check.**

Reasoning:

1. The Worker is online and bound to the selected transit resource.
2. A read-only Worker check is the correct next step before route planning.
3. The check can confirm basic host and service visibility without creating a route.
4. It helps verify whether the Worker can report transit-side status before any
   future read-only preflight or real route execution stage.

## 4. Approved operator action after merge

After this document is merged, the operator may click exactly one `Worker 检查`
button for the selected transit server in the LiveLine Console UI.

Approved scope:

- Create one read-only Worker command for the selected transit resource.
- Expected command category: `collect_status` or equivalent first-party read-only
  status collection command.
- Allow the Worker to report non-mutating host and service status.
- Record the resulting UI status and summary in the next acceptance stage.

## 5. Allowed read-only data

The Worker check may collect only non-mutating information such as:

- Worker status.
- Worker version.
- Hostname.
- Interface name.
- Public / interface IP summary when available.
- OS summary.
- Kernel summary.
- Uptime.
- CPU summary.
- Memory summary.
- Disk summary.
- Read-only service status for `liveline-worker`.
- Read-only service status for `socat`.
- Read-only service status for `gost`.

The command result should remain redacted and must not include secrets.

## 6. Explicitly not authorized

This approval does not authorize:

- running SSH,
- running arbitrary shell commands,
- installing packages,
- installing Worker again,
- installing `socat`,
- installing `gost`,
- creating transit routes,
- creating or modifying systemd services,
- starting, stopping, enabling, disabling, or restarting `socat` / `gost`,
- creating or modifying Xray config,
- creating, reserving, binding, or listening on a TCP port,
- opening cloud security group ports,
- opening cloud firewall ports,
- modifying server-local firewall rules,
- modifying iptables or nftables,
- generating a usable transit client endpoint,
- exporting a full client link,
- modifying `nodes.share_link`,
- changing the accepted landing node,
- creating, deleting, rebuilding, or rotating nodes,
- running route cutover,
- deleting old routes,
- stopping fallback links,
- running database migrations,
- deploying the public console.

## 7. Expected result to capture next

After the operator runs the approved UI check, the next stage should record:

- Whether the Worker command was created.
- Whether it completed successfully.
- Worker command type.
- Worker command status.
- Any redacted summary shown by the UI.
- Worker version if shown.
- Whether `liveline-worker` status is visible.
- Whether `socat` / `gost` status is visible as read-only information.
- Any error message, if the command fails.

Recommended next stage after running the check:

`Stage 3.3.53-transit-worker-readonly-check-acceptance`

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

The read-only Worker command result should also avoid storing or displaying these
values.

## 10. Stage result

Stage 3.3.52 is complete when this approval record is merged.

Result:

- One read-only Worker check is approved after merge for `香港中转服务器` /
  `163.223.216.108` only.
- Approval is limited to non-mutating Worker status collection.
- Transit route creation remains No-Go.
- `socat` / `gost` installation or modification remains No-Go.
- Listener port creation or firewall change remains No-Go.
- Cutover remains No-Go.
