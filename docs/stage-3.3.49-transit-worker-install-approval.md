# Stage 3.3.49 — Transit Worker Install Approval

## 1. Purpose

Stage 3.3.49 records approval boundaries for manually installing LiveLine Worker on
the selected transit server.

This stage is documentation-only. It does not run the generated Worker install
command, does not connect to the VPS, does not install Worker, does not execute
SSH, does not run Worker commands, does not create transit routes, does not open
ports, does not modify firewall rules, and does not perform cutover.

## 2. Operator decision

The operator agreed to enter this approval stage after receiving the recommendation
that installing Worker is the correct next step for the selected transit server.

Approval scope recorded by this stage:

- Proceed to a separate manual Worker install step after this document is merged.
- The operator must manually execute the system-generated Worker install command
  on the selected VPS.
- The full install command and token must remain private and must not be copied
  into documentation, PR comments, task logs, screenshots, or chat messages.

This stage itself does not execute the command.

## 3. Selected transit server

| Field | Value |
| --- | --- |
| Transit server name | `香港中转服务器` |
| Transit server IP | `163.223.216.108` |
| Role | `transit` |
| Connection mode | Worker install command |
| Current console state | `pending_worker` resource / active one-time token |
| Expected post-install state | Worker registered and heartbeat online |

## 4. Recommendation

Recommendation: **Proceed with manual Worker install after this approval record is
merged.**

Reasoning:

1. The current transit-server onboarding flow is Worker based.
2. Without installing Worker, the transit server remains `pending_worker` and cannot
   be accepted as an online Worker-managed transit resource.
3. Worker install is required before Worker status checks and future Worker-based
   route planning can be used.
4. Current Worker v1 and command-channel behavior are limited to registration,
   heartbeat, basic read-only status reporting, and approved read-only / no-op
   command types.
5. Worker install does not by itself create a transit link, install `socat` / `gost`,
   bind a listener port, modify firewall rules, or perform cutover.

## 5. Allowed manual action after merge

After this document is merged, the operator may manually run the generated Worker
install command on `163.223.216.108`.

Allowed action:

- Install `liveline-worker` on the selected transit VPS.
- Register the Worker against the console using the generated one-time token.
- Write the Worker runtime config on the VPS.
- Create and enable `liveline-worker.service`.
- Start or restart `liveline-worker.service`.
- Allow the Worker to send heartbeat and basic read-only status reports.

Expected install-script effects, based on the current Worker bootstrap design:

- `/usr/local/bin/liveline-worker` is installed.
- `/etc/liveline-worker/config.yaml` is written with local Worker runtime
  credentials.
- `/etc/systemd/system/liveline-worker.service` is written.
- `systemctl daemon-reload` is run.
- `systemctl enable liveline-worker` is run.
- `systemctl restart liveline-worker` is run.

## 6. Explicitly not authorized

This approval does not authorize:

- creating a transit route,
- installing `socat`,
- installing `gost`,
- creating or modifying any `socat` or `gost` service,
- creating or modifying Xray configuration,
- creating or modifying a listener port,
- binding or reserving any TCP port,
- opening a cloud security group port,
- opening a cloud firewall port,
- modifying the server-local firewall,
- modifying iptables or nftables,
- generating a usable transit client endpoint,
- exporting a full client link,
- modifying `nodes.share_link`,
- changing the accepted landing node,
- creating, deleting, rebuilding, or rotating nodes,
- running route cutover,
- deleting old routes,
- stopping fallback links,
- restarting existing `socat` / `gost` route services,
- running database migrations,
- deploying the public console.

## 7. Operator execution checklist

Before running the command manually, the operator should confirm:

- The command is copied only from the console UI.
- The command is not pasted into chat, docs, PR comments, logs, or screenshots.
- The VPS is the selected transit server: `163.223.216.108`.
- The command role argument remains `transit`.
- The interface argument should be the intended network interface shown by the UI
  or install command.
- The command is run as root or with sufficient privileges.
- The console public URL in the command is reachable from the VPS.

After running the command, the operator should check the console first:

- Transit server should move from `pending_worker` toward `online` after heartbeat.
- Worker role should show `transit`.
- Worker hostname / interface / version should appear if heartbeat succeeds.

If the console does not show online status, inspect only Worker status/logs first;
do not attempt route creation.

## 8. Allowed post-install local checks

After manual install, the next acceptance stage may record only non-route checks:

- Worker appears in console.
- Worker is bound to the selected transit server resource.
- Worker role is `transit`.
- Worker heartbeat is fresh.
- Worker status is online.
- Worker version is visible.
- Basic read-only Worker check can be planned or run only under a separately
  approved read-only stage.

## 9. Port and firewall reminder

This stage does not require opening any transit listener port.

A future stage that opens, reserves, binds, or changes a transit listener port must
remind the operator before execution:

1. Allow the selected TCP port in the cloud provider security group.
2. Allow the selected TCP port in the cloud firewall if separate from the security
   group.
3. Verify the server-local firewall state and allow the selected TCP port if the
   local firewall is active.
4. Confirm the selected port is not already used by SSH, web, database, Redis,
   console, Worker, Xray, or another transit route.

## 10. Rollback / stop guidance boundary

This stage does not execute rollback.

If the operator installs Worker and later needs to stop it, a separate stage should
record the requested operation before changing the server. Possible future actions
may include checking `liveline-worker.service` status or stopping the Worker, but
those are not authorized by this stage.

## 11. Sensitive-data handling

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

The generated Worker install command is a sensitive one-time secret. It must stay
in the console UI and the operator's terminal only.

## 12. Stage result

Stage 3.3.49 is complete when this approval record is merged.

Result:

- Manual Worker install is approved after merge for `香港中转服务器` /
  `163.223.216.108` only.
- Approval is limited to installing, registering, enabling, and starting
  `liveline-worker`.
- Transit route creation remains No-Go.
- `socat` / `gost` install or modification remains No-Go.
- Listener port creation or firewall change remains No-Go.
- Cutover remains No-Go.

Recommended next stage after the operator manually runs the command:

`Stage 3.3.50-transit-worker-registration-acceptance`

That next stage should record whether the Worker registered successfully, whether
heartbeat is fresh, whether the server shows online in the UI, and whether any
read-only status information is visible without exposing secrets.
