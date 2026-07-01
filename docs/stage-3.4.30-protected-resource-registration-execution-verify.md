# Stage 3.4.30 Protected Resource Registration Execution Verify

## Goal

Stage 3.4.30 executes the protected local resource-registration handoff created by Stage 3.4.29.

This is the first protected stage that may write local database resource records, but only after a successful dry-run, approval dry-run, pending command creation, a final approval phrase, and explicit safety confirmations.

## Endpoint

```text
POST /api/transit-routes/protected-resource-registration-execution-verify
```

The endpoint requires an admin session and CSRF token.

## Allowed Local Writes

This stage may create or reuse:

- one local `transit_resources` record
- one local landing `nodes` record
- the original Stage 3.4.29 pending command task execution audit/result

If the same command has already been executed successfully, the endpoint returns the existing result with `idempotent_reuse = true` and does not create duplicate resource records.

## Why Local DB Registration Is Allowed

The previous protected stages only produced plans, dry-run results, approval evidence, and a pending command record. Stage 3.4.30 is the controlled handoff from an approved pending command into local database resource records.

The endpoint rechecks the command source, approval status, registration source preview, duplicate resource conflicts, landing VPS existence, safety confirmations, and sensitive-value redaction before any local write.

If a safe landing VPS record cannot be matched, the endpoint blocks instead of inventing a server record.

## Final Approval Text

The request must include the exact approval text:

```text
EXECUTE_PROTECTED_RESOURCE_REGISTRATION:<command_id>
```

Any mismatch blocks execution without writing records.

## Idempotency

The execution result stores a fingerprint based on:

- `command_id`
- Stage 3.4.29 `idempotency_key`
- sanitized registration source preview

Repeated execution of an already verified command returns the stored `created` ids and marks `idempotent_reuse = true`.

## Verification

The response includes verification flags proving this stage stayed inside the protected boundary:

```text
transit_resource_exists = true
landing_node_exists = true
worker_command_created = false
transit_route_created = false
haproxy_route_created = false
listening_port_changed = false
remote_execution_triggered = false
firewall_changed = false
cutover_done = false
```

Blocked requests return `executed = false`, checks, and blocked reasons without creating records.

## Safety Boundary

This stage does not:

- create a `WorkerCommand`
- create a `TransitRoute`
- create a HAProxy route
- generate HAProxy config
- bind or change a listening port
- run SSH or remote commands
- install, start, stop, or reload HAProxy
- change firewall, cloud firewall, or cloud security groups
- perform cutover
- read, output, or modify complete client configuration values
- modify `nodes.share_link`
- write `transit_routes.share_link`
- modify ordinary product UI
- modify Worker, docker-compose, or migrations

## Frontend

The frontend entry is limited to the Advanced Debug HAProxy panel.

It lets an operator paste or reuse the Stage 3.4.29 command-create result, enter the final execution approval text, review the execution-verify payload, confirm the safety boundary, call the protected endpoint, and inspect created ids, idempotency state, checks, blocked reasons, and verification flags.

No ordinary product page is changed.

## Next Stage

After a successful execution verification, the recommended next stage is:

```text
Stage 3.4.31-regenerate-haproxy-dry-run
```

Stage 3.4.31 should generate a fresh HAProxy dry-run from the newly registered local resources. It must remain dry-run first, approval-based, auditable, and blocked by default.
