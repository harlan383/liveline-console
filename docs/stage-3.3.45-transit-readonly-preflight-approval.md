# Stage 3.3.45 — Transit Readonly Preflight Approval

## 1. Purpose

Stage 3.3.45 records the approval gate for a future transit-route read-only
preflight.

This stage is intentionally documentation-only. It does not execute the preflight.
It only defines what would be allowed in a later read-only preflight stage and
records whether the current prerequisites are sufficient to approve that future
execution.

## 2. Current decision

Current decision: **Blocked / No-Go for read-only preflight execution**.

Reason:

- The exact transit resource has not been selected.
- The transit resource type has not been selected.
- The candidate transit listener port has not been selected.
- Cloud security group / cloud firewall confirmation is still pending.
- Server-local firewall confirmation is still pending.
- The operator has not yet granted explicit approval for any concrete preflight
  target.

Because those values are missing, this stage must not authorize any Worker,
SSH, or remote diagnostic execution.

## 3. Baseline carried forward

The preceding target-selection record is
`docs/stage-3.3.44-transit-target-selection-record.md`.

Baseline carried forward:

- Accepted landing-node destination baseline: `liveline-reality-27939`.
- Transit resource: `Pending operator selection`.
- Candidate transit listener port: `Pending operator selection`.
- Preferred future forwarding method: `socat` TCP forward.
- Fallback method: `gost` TCP forwarding only if later explicitly selected.
- Real route execution: No-Go.
- Cutover: No-Go.

## 4. Required concrete inputs before approval can change to Go

The approval state can change from Blocked to Go only after the operator provides
or confirms all of the following:

| Required input | Current value | Current status |
| --- | --- | --- |
| Exact transit resource | `Pending operator selection` | Missing |
| Transit resource type | `server`, `iepl`, `iplc`, or `other` | Missing |
| Transit resource region / line | Hong Kong / IEPL / IPLC candidate expected | Missing |
| Candidate TCP listener port | `Pending operator selection` | Missing |
| Landing node destination | `liveline-reality-27939` | Present |
| Read-only-only confirmation | Not explicitly confirmed for a concrete target | Missing |
| Cloud security group status | Pending | Missing |
| Cloud firewall status | Pending | Missing |
| Server-local firewall status | Pending | Missing |
| Authorization for package install / writes | Not authorized | Correctly blocked |
| Authorization for real route execution | Not authorized | Correctly blocked |
| Authorization for cutover | Not authorized | Correctly blocked |

## 5. Approved command category for a future Go stage

If a later stage receives the missing target values and explicit operator
approval, the future read-only preflight may inspect only non-mutating facts.

Allowed categories for that later stage:

- OS and kernel information.
- CPU architecture.
- Current user and privilege boundary.
- systemd availability.
- Installed forwarding tool presence, such as `socat` or `gost`, without
  installing anything.
- Current TCP listeners.
- Whether the proposed listener port is already occupied.
- Firewall tooling and current firewall state.
- Basic TCP reachability from the transit resource to the accepted landing-node
  destination.
- Basic route and DNS diagnostics that do not modify network configuration.

The later read-only preflight must record command intent before execution and must
not expose sensitive links or private keys in task output.

## 6. Explicitly forbidden in read-only preflight

Even if a later stage becomes Go for read-only preflight, it must not:

- Install packages.
- Run `apt`, `yum`, `dnf`, `apk`, `curl | bash`, or installer scripts.
- Write, move, delete, or chmod files.
- Create or modify systemd services.
- Start, stop, restart, enable, or disable services.
- Modify Xray config.
- Modify `socat` / `gost` configuration.
- Modify iptables / nftables.
- Modify cloud security groups, cloud firewalls, or local firewall rules.
- Open or reserve ports.
- Create a transit route.
- Generate a transit client endpoint.
- Modify `nodes.share_link`.
- Export a full client link.
- Create, delete, rebuild, or rotate nodes.
- Run database migrations.
- Deploy the public console.

## 7. Future preflight evidence template

A later read-only preflight execution stage should record results in this shape:

| Check | Expected evidence | Pass condition |
| --- | --- | --- |
| Transit target identity | Resource name / id, type, region | Matches approved target |
| OS / architecture | Read-only OS and arch output | Supported Linux target |
| Privilege boundary | `whoami` / user context | Matches expected Worker or SSH user |
| systemd availability | Read-only systemd check | Available if systemd-managed route is planned |
| Tool presence | `command -v socat`, `command -v gost` | Tool state known; missing tool is not installed |
| Listener inventory | `ss -lntp` or equivalent | Candidate port is not occupied |
| Firewall state | ufw/firewalld/nft/iptables read-only status | State recorded without changes |
| Destination reachability | TCP probe from transit to landing destination | Reachability known without creating route |
| Sensitive output scan | Review task output | No full links, keys, tokens, or passwords |

## 8. Operator reminder for future port work

Any later stage that selects, opens, or changes a transit listener port must remind
the operator to complete all of the following before execution:

1. Allow the selected TCP port in the cloud provider security group.
2. Allow the selected TCP port in the cloud firewall if separate from the security
   group.
3. Verify the server-local firewall state and allow the selected TCP port if the
   local firewall is active.
4. Confirm the selected port is not already used by SSH, web, database, Redis,
   console, Worker, Xray, or another transit route.

This stage does not select, reserve, open, or test any port.

## 9. Sensitive-data handling

This document intentionally excludes:

- Full `vless://` links.
- Full `nodes.share_link` values.
- Reality private keys.
- Worker setup tokens.
- Database passwords.
- Full Xray configuration.
- Provider account credentials.
- SSH private keys.

A future read-only preflight result must also redact or omit sensitive values from
`tasks.result_data`, task logs, PR comments, and operator-facing summaries.

## 10. Stage result

Stage 3.3.45 is complete when this document is merged.

Result:

- Read-only preflight approval is documented.
- Current approval decision is **Blocked / No-Go**.
- The blocker is not a technical failure; the blocker is missing concrete operator
  inputs.
- No remote command was authorized or executed by this stage.
- No real transit route execution or cutover was authorized.

Recommended next step:

The operator should provide the exact transit resource and candidate TCP listener
port before moving to a future `Stage 3.3.46-transit-readonly-preflight-execution`.
If those inputs remain missing, Stage 3.3.46 must also remain No-Go.
