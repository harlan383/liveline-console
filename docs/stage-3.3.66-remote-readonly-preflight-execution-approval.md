# Stage 3.3.66 — Remote Readonly Preflight Execution Approval

## Purpose

Stage 3.3.66 records approval to run one remote readonly preflight for the planned transit route.

This is an approval-only stage. It does not run the preflight command by itself.

## Preconditions

The following preconditions are satisfied:

| Item | Value |
| --- | --- |
| Transit Worker status | `online` |
| Transit Worker version | `0.1.7-stage-3.3.63` |
| Transit Worker role | `transit` |
| Pending/running tasks | `0 rows` |
| Existing `transit_readonly_preflight` commands | `0 rows` |

## Approved plan inputs

| Item | Value |
| --- | --- |
| Transit resource | `香港中转服务器` |
| Transit IP | `163.223.216.108` |
| Landing node | `liveline-reality-27939` |
| Planned listener port | `24731` |
| Landing target port | `27939` |
| Purpose | `直播线路` |

## Approved action

A later user operation may click the UI action labeled `执行远程只读预检` exactly once for the recorded plan.

The action may create one `transit_readonly_preflight` Worker command through the approved Worker/API path.

## Allowed checks

Only the fixed Worker allowlist readonly checks are approved:

- Worker identity and version readback,
- planned port occupancy readback,
- `socat` readonly status,
- `gost` readonly status,
- transit-to-landing TCP reachability readback,
- local firewall readonly summary,
- redacted result summary.

## No-Go boundary

This approval does not authorize transit route creation, package installation, service restart, listener binding, firewall changes, Xray changes, `nodes.share_link` changes, full link export, or cutover.

## Result recording

The next stage should record the result of the one remote readonly preflight as `passed`, `blocked`, or `failed`.

Recommended next stage:

`Stage 3.3.67-remote-readonly-preflight-result-acceptance`

## Result

Stage 3.3.66 approves one remote readonly preflight execution for the recorded plan. Real route creation remains No-Go.
