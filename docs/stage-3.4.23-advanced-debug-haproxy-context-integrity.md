# Stage 3.4.23 Advanced Debug HAProxy Context Integrity

## Scope

This stage adds context integrity checks to the Advanced Debug HAProxy Runtime Readiness context autofill flow.

Only the Advanced Debug HAProxy panel and its read-only context endpoint are affected. Ordinary product pages and customer-facing flows are unchanged.

## Problem

A historical HAProxy dry-run candidate can exist in `worker_commands.payload_json` even when the formal transit resource or landing node record no longer exists.

That means:

- a dry-run candidate can provide historical parameters,
- but it does not prove that the linked transit resource still exists,
- it does not prove that the linked landing node still exists,
- it does not prove that the transit Worker is online,
- and it does not prove that the candidate host/port still matches the formal landing node.

The UI must therefore treat dry-run candidates as historical context until integrity checks prove that the current database context is complete.

## Integrity Checks

Each HAProxy dry-run candidate returned by `GET /api/transit-routes/haproxy-runtime-debug-context` now includes:

- `integrity_ready`
- `integrity_blocked`
- `integrity_summary`
- `integrity_next_action`
- `integrity_checks`

The checks include:

- `transit_resource_record_exists`
- `transit_resource_not_deleted`
- `transit_resource_status_supported`
- `transit_worker_record_exists`
- `transit_worker_online`
- `transit_worker_role_is_transit`
- `transit_worker_interface_detected`
- `landing_node_record_exists`
- `landing_node_not_deleted`
- `landing_node_active`
- `landing_node_has_vps_ip`
- `landing_node_xray_port_present`
- `candidate_landing_host_matches_node_vps_ip`
- `candidate_landing_port_matches_node_xray_port`
- `candidate_forwarding_method_is_haproxy_tcp`
- `candidate_is_dry_run`
- `candidate_is_not_real_execution`
- `candidate_status_succeeded`

`integrity_ready` is true only when all danger-level checks pass.

## UI Behavior

The Advanced Debug context autofill area now shows the selected candidate's context integrity state and check list.

Operators may still fill the readiness payload from a blocked candidate for inspection, but blocked candidates cannot run readiness or real execution.

The UI also makes missing linked records explicit:

- missing `transit_resource_id` is shown next to the transit resource selector,
- missing `landing_node_id` is shown next to the landing node selector,
- matched records are shown as matched formal transit resource / landing node.

Autofill remains passive:

- it does not auto-check firewall confirmations,
- it does not auto-run readiness,
- it does not create real execution commands,
- it clears previous readiness / real execution results after filling.

## Safety Boundary

This stage does not:

- change ordinary product UI,
- create WorkerCommand records,
- create TransitRoute records,
- create HAProxy routes,
- bind listener ports,
- connect over SSH,
- execute remote commands,
- mutate firewall / cloud security group / cloud firewall settings,
- read or output full `share_link`,
- output full client URI values, tokens, private keys, or install commands,
- perform cutover,
- modify Worker code,
- modify docker-compose,
- add migrations.

The context endpoint remains read-only and does not call `commit`, `flush`, `refresh`, or audit writes.

## Validation

- `git diff --check`
- `git diff --cached --check`
- frontend typecheck
- frontend production build
- backend compileall
- targeted backend unittest
- staged diff sensitive scan
