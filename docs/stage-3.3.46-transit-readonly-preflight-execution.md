# Stage 3.3.46 — Transit Readonly Preflight Execution

## 1. Purpose

Stage 3.3.46 records the updated read-only preflight authorization boundary after
the operator supplied additional constraints for future transit-resource checks.

This stage is documentation-only. It does not run the preflight. It records the
allowed preflight mode, the permitted candidate-port range, the still-missing
concrete transit target, and the continued No-Go boundary for real route creation.

## 2. Operator-provided constraints

The operator has now provided these constraints:

- Transit resources are prepared and will be added into the system when needed.
- Candidate transit listener ports should be randomly selected from TCP
  `10000-30000`.
- Authorization is limited to read-only preflight.
- Real transit-route creation is not authorized.
- Cutover is not authorized.

These constraints narrow the future execution envelope but do not by themselves
select a concrete transit resource.

## 3. Current decision

Current decision: **Limited Go for future read-only preflight planning, but No-Go
for immediate read-only preflight execution until a concrete transit resource is
selected in the system.**

Reason:

- The operator has approved the read-only-only preflight mode.
- The operator has approved the candidate port policy: random TCP port in
  `10000-30000`.
- The exact transit resource is still not selected in the system.
- The exact candidate listener port is still not generated or recorded for a
  concrete target.
- Cloud security group / cloud firewall confirmation remains future-stage work.
- Server-local firewall confirmation remains future-stage work.

Because the concrete target is still missing, this stage must not execute Worker,
SSH, or remote diagnostic commands.

## 4. Baseline carried forward

The preceding approval record is
`docs/stage-3.3.45-transit-readonly-preflight-approval.md`.

Baseline carried forward:

- Accepted landing-node destination baseline: `liveline-reality-27939`.
- Transit resource: prepared by operator, not yet selected in the system.
- Candidate port policy: random TCP `10000-30000`.
- Preferred future forwarding method: `socat` TCP forward.
- Fallback method: `gost` TCP forwarding only if later explicitly selected.
- Read-only preflight mode: operator-authorized.
- Real route execution: No-Go.
- Cutover: No-Go.

## 5. Updated approval matrix

| Item | Current value | Current status |
| --- | --- | --- |
| Exact transit resource | Prepared externally; pending system selection | Missing for execution |
| Transit resource type | To be selected when resource is added | Missing for execution |
| Transit resource region / line | Hong Kong / IEPL / IPLC candidate expected | Missing for execution |
| Candidate TCP listener port policy | Random TCP `10000-30000` | Approved as policy |
| Exact candidate TCP listener port | Not generated / not recorded | Missing for execution |
| Landing node destination | `liveline-reality-27939` | Present |
| Read-only-only confirmation | Operator confirmed | Approved |
| Cloud security group status | Future confirmation required for selected port | Pending |
| Cloud firewall status | Future confirmation required if separate | Pending |
| Server-local firewall status | Future read-only check / confirmation required | Pending |
| Authorization for package install / writes | Not authorized | Correctly blocked |
| Authorization for real route execution | Not authorized | Correctly blocked |
| Authorization for cutover | Not authorized | Correctly blocked |

## 6. What a later concrete read-only preflight may do

After the operator adds or selects the exact transit resource in the system, a
later concrete read-only preflight may inspect only non-mutating facts.

Allowed read-only categories:

- Transit resource identity and role.
- OS and kernel information.
- CPU architecture.
- Current user and privilege boundary.
- systemd availability.
- Installed forwarding tool presence, such as `socat` or `gost`, without
  installing anything.
- Current TCP listeners.
- Whether a generated candidate port from TCP `10000-30000` is already occupied.
- Firewall tooling and current firewall state.
- Basic TCP reachability from the transit resource to the accepted landing-node
  destination.
- Basic route and DNS diagnostics that do not modify network configuration.
- Sensitive-output scan for task results and logs.

The later preflight may report that a tool is missing. It must not install the
missing tool.

## 7. Candidate port generation rules

A future concrete preflight or plan-builder may generate one candidate listener
port using this policy:

- TCP only.
- Random integer in the inclusive range `10000-30000`.
- Do not choose a port already present in the transit host listener inventory.
- Do not choose a port already assigned to another planned or active transit route
  in the console.
- Do not choose a port already known to be used by SSH, web, database, Redis,
  console, Worker, Xray, or another route.
- Do not reserve, open, bind, or listen on the port during read-only preflight.
- Record the candidate port as a plan value only.

The actual future execution stage must re-check the candidate port immediately
before any write action, because a read-only preflight result can become stale.

## 8. Firewall and security-group reminder

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

## 9. Explicitly forbidden in this stage

Stage 3.3.46 does not:

- Execute SSH commands.
- Execute Worker commands.
- Run the read-only preflight.
- Install packages.
- Run `apt`, `yum`, `dnf`, `apk`, `curl | bash`, or installer scripts.
- Write, move, delete, or chmod files.
- Create or modify systemd services.
- Start, stop, restart, enable, or disable services.
- Modify Xray config.
- Modify `socat` / `gost` configuration.
- Modify iptables / nftables.
- Modify cloud security groups, cloud firewalls, or local firewall rules.
- Open, reserve, bind, or listen on ports.
- Create a transit route.
- Generate a transit client endpoint.
- Modify `nodes.share_link`.
- Export a full client link.
- Create, delete, rebuild, or rotate nodes.
- Run database migrations.
- Deploy the public console.

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

A future preflight result must redact or omit sensitive values from
`tasks.result_data`, task logs, PR comments, and operator-facing summaries.

## 11. Stage result

Stage 3.3.46 is complete when this document is merged.

Result:

- The operator's read-only-only authorization is recorded.
- The future candidate listener port policy is recorded as random TCP
  `10000-30000`.
- The exact transit resource remains pending system selection.
- Immediate remote preflight execution remains blocked until a concrete target is
  selected.
- Real transit-route creation remains No-Go.
- Cutover remains No-Go.

Recommended next stage:

`Stage 3.3.47-transit-resource-selection-and-port-plan`

That next stage should record the exact system transit resource, resource type,
region / line, and generated candidate TCP port from `10000-30000`. It should
remain documentation-only unless a later explicit command-execution stage is
opened.
