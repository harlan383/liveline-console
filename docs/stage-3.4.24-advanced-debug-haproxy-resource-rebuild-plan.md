# Stage 3.4.24 Advanced Debug HAProxy Resource Rebuild Plan

## Scope

This stage adds a read-only resource rebuild plan to the Advanced Debug HAProxy Runtime Readiness page.

It does not change ordinary product pages or customer-facing flows. The plan is generated only from the selected HAProxy dry-run candidate and the integrity checks introduced in Stage 3.4.23.

## Problem

Stage 3.4.23 can correctly mark a historical dry-run candidate as blocked when its linked transit resource, landing node, Worker, or target host/port no longer matches the current database context.

Operators still need a clear next-step plan that explains what is missing before a new readiness or real execution attempt is allowed.

## Resource Rebuild Plan

The Advanced Debug UI now derives a plan from the selected candidate:

- candidate summary
- danger-level blocked checks
- required resource actions
- recommended next stage

The plan is read-only. It does not create resources, regenerate dry-runs, run readiness, create real execution commands, or touch remote hosts.

## UI Behavior

When a candidate is ready:

- the plan states that no resource rebuild is required,
- operators are reminded to manually confirm port exposure and safety boundaries before readiness.

When a candidate is blocked:

- the plan states that the candidate is historical parameter context only,
- readiness and protected execution remain blocked,
- the UI lists blocked checks and grouped remediation actions,
- operators can copy a redacted plain-text plan for follow-up work.

The copy output includes only dry-run identifiers, route names, ports, target host/port, blocked checks, required actions, and recommended next stage. It does not include full client links, share links, secrets, private keys, passwords, or install commands.

## Safety Boundary

This stage does not:

- change ordinary product UI,
- create transit resources,
- create landing nodes,
- create WorkerCommand records,
- create TransitRoute records,
- create HAProxy routes,
- bind listener ports,
- connect over SSH,
- execute remote commands,
- mutate firewall / cloud security group / cloud firewall settings,
- export share links,
- export full client links,
- perform cutover,
- modify Worker code,
- modify docker-compose,
- add migrations.

## Validation

- `git diff --check`
- `git diff --cached --check`
- frontend typecheck
- frontend production build
- staged sensitive scan
