# Stage 3.3.47 — Transit Resource Selection and Port Plan

## 1. Purpose

Stage 3.3.47 records the resource-selection and candidate-port planning boundary
for a future transit-route read-only preflight.

This stage is documentation-only. It does not select a concrete resource on behalf
of the operator, does not generate a real route endpoint, does not execute
read-only preflight, and does not create a transit route.

## 2. Baseline carried forward

The preceding stage is
`docs/stage-3.3.46-transit-readonly-preflight-execution.md`.

Baseline carried forward:

- Accepted landing-node destination baseline: `liveline-reality-27939`.
- Transit resources: prepared by the operator and will be added in the system when
  needed.
- Candidate listener port policy: random TCP `10000-30000`.
- Authorization scope: read-only preflight only.
- Real transit-route creation: No-Go.
- Cutover: No-Go.
- Preferred first forwarding method for future execution planning: `socat` TCP
  forward.
- Fallback method: `gost` TCP forwarding only if later explicitly selected.

## 3. Current selection status

| Item | Current value | Status |
| --- | --- | --- |
| Exact transit resource | Pending operator system selection | Missing |
| Transit resource type | `server`, `iepl`, `iplc`, or `other` | Missing |
| Transit resource region / line | Hong Kong / IEPL / IPLC candidate expected | Missing |
| Landing node destination | `liveline-reality-27939` | Present |
| Candidate port range | Random TCP `10000-30000` | Policy approved |
| Exact candidate TCP port | Pending generation after resource selection | Missing |
| Read-only preflight authorization | Approved only after concrete target is selected | Conditional |
| Real route execution authorization | Not authorized | No-Go |
| Cutover authorization | Not authorized | No-Go |

## 4. Stage decision

Current decision: **Resource-selection and candidate-port planning only.**

The operator has confirmed that transit resources are ready and will be added into
the system when needed. However, this stage still does not have a selected system
resource record. Therefore, this stage records the selection framework but does not
execute a preflight.

A future concrete preflight stage may proceed only after the operator selects a
specific transit resource in the system and records a candidate TCP port generated
from the approved `10000-30000` range.

## 5. Resource-selection checklist

Before a concrete read-only preflight can run, the selected resource must be
recorded with these fields:

| Field | Requirement |
| --- | --- |
| Resource name / label | Must match a resource visible in the console |
| Resource id | Must be the system record id or stable identifier |
| Resource type | `server`, `iepl`, `iplc`, or `other` |
| Region / line | Hong Kong / IEPL / IPLC / other operator-selected line |
| Connectivity role | Transit listener in front of `liveline-reality-27939` |
| Access method | Worker-based read-only preflight or explicitly approved equivalent |
| Candidate port | One TCP port generated from `10000-30000` |
| Real execution status | Must remain No-Go during this planning stage |

If any required field is missing, the preflight execution stage remains blocked.

## 6. Candidate-port plan

A future candidate port must be generated only after a concrete transit resource is
selected.

Port policy:

- TCP only.
- Random integer in the inclusive range `10000-30000`.
- Generated as a plan value only.
- Not opened, reserved, bound, or listened on during planning.
- Must be checked against the selected transit host listener inventory during
  read-only preflight.
- Must be checked against console route records to avoid collision with existing
  or planned transit routes.
- Must be re-checked immediately before any future write action because earlier
  listener inventories can become stale.

This stage does not generate or record a final candidate port because the concrete
transit resource has not been selected in the system yet.

## 7. Future read-only preflight scope

After a concrete resource and candidate port are recorded, a later read-only
preflight may inspect only non-mutating facts:

- Transit resource identity and role.
- OS and kernel information.
- CPU architecture.
- Current user and privilege boundary.
- systemd availability.
- Installed forwarding tool presence, such as `socat` or `gost`, without
  installing anything.
- Current TCP listeners.
- Whether the generated candidate port is already occupied.
- Firewall tooling and current firewall state.
- Basic TCP reachability from the transit resource to the accepted landing-node
  destination.
- Basic route and DNS diagnostics that do not modify network configuration.
- Sensitive-output scan for task results and logs.

## 8. Explicit No-Go boundary

Stage 3.3.47 does not:

- Execute SSH commands.
- Execute Worker commands.
- Run read-only preflight.
- Generate a real usable client endpoint.
- Install packages.
- Write, move, delete, or chmod files.
- Create or modify systemd services.
- Start, stop, restart, enable, or disable services.
- Modify Xray config.
- Modify `socat` / `gost` configuration.
- Modify iptables / nftables.
- Modify cloud security groups, cloud firewalls, or local firewall rules.
- Open, reserve, bind, or listen on ports.
- Create a transit route.
- Modify `nodes.share_link`.
- Export a full client link.
- Create, delete, rebuild, or rotate nodes.
- Run database migrations.
- Deploy the public console.

## 9. Firewall and security-group reminder

Any future stage that opens, reserves, binds, or changes a transit listener port
must remind the operator before execution:

1. Allow the selected TCP port in the cloud provider security group.
2. Allow the selected TCP port in the cloud firewall if separate from the security
   group.
3. Verify the server-local firewall state and allow the selected TCP port if the
   local firewall is active.
4. Confirm the selected port is not already used by SSH, web, database, Redis,
   console, Worker, Xray, or another transit route.

This stage does not select, reserve, open, bind, or test any port.

## 10. Sensitive-data handling

This document intentionally excludes:

- Full `vless://` links.
- Full `nodes.share_link` values.
- Reality private keys.
- Worker setup tokens.
- Database passwords.
- Full Xray configuration.
- Provider account credentials.
- SSH private keys.

A future resource-selection or preflight result must redact or omit sensitive
values from `tasks.result_data`, task logs, PR comments, and operator-facing
summaries.

## 11. Stage result

Stage 3.3.47 is complete when this document is merged.

Result:

- The resource-selection framework is recorded.
- The candidate-port planning policy remains random TCP `10000-30000`.
- The exact transit resource remains pending operator system selection.
- The exact candidate TCP port remains pending generation after resource
  selection.
- Read-only preflight remains conditional on concrete target selection.
- Real transit-route creation remains No-Go.
- Cutover remains No-Go.

Recommended next stage:

`Stage 3.3.48-transit-resource-selected-readonly-preflight-approval`

That next stage should be opened only after the operator selects the exact transit
resource in the system and records a candidate TCP port from `10000-30000`. It
should still authorize only read-only preflight unless the operator separately
opens a real execution approval stage.
