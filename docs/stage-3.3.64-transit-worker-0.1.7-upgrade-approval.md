# Stage 3.3.64 — Transit Worker 0.1.7 Upgrade Approval

## Purpose

Stage 3.3.64 records approval to upgrade the Hong Kong transit Worker so it can support the Stage 3.3.63 remote readonly preflight command.

This is an approval-only stage. It does not perform the upgrade.

## Background

Stage 3.3.63 introduced the `transit_readonly_preflight` Worker/API path.

That command requires Worker version:

`0.1.7-stage-3.3.63`

The Hong Kong transit Worker was previously observed as:

`0.1.6-stage-3.3.37`

## Approved target

| Item | Value |
| --- | --- |
| Transit server | `香港中转服务器` |
| Transit IP | `163.223.216.108` |
| Worker role | `transit` |
| Current known version | `0.1.6-stage-3.3.37` |
| Target version | `0.1.7-stage-3.3.63` |
| Reason | Required for `transit_readonly_preflight` |

## Approved action

A later execution stage may upgrade only the transit Worker binary/service on the Hong Kong transit server to the target version.

The upgrade should preserve the existing Worker binding, role, token state, and server resource identity.

## Verification after future execution

After the later upgrade execution stage, verify:

- Worker is online,
- Worker role remains `transit`,
- Worker version reports `0.1.7-stage-3.3.63`,
- heartbeat resumes,
- no pending or running tasks are introduced unexpectedly,
- no `transit_readonly_preflight` command is created during upgrade validation unless separately authorized.

## No-Go boundary

This approval does not authorize transit route creation, `socat` / `gost` installation or restart, listener binding, firewall changes, Xray changes, `nodes.share_link` changes, full link export, or cutover.

## Recommended next stage

Recommended next stage:

`Stage 3.3.65-transit-worker-0.1.7-upgrade-execution`

That stage should perform only the Worker upgrade and post-upgrade readback.

## Result

Stage 3.3.64 approves the Worker upgrade plan. Real route creation remains No-Go.
