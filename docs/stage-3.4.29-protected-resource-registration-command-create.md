# Stage 3.4.29 Protected Resource Registration Command Create

## Goal

Stage 3.4.29 converts a successful Stage 3.4.28 approval dry-run into a local protected pending command record.

This stage exists only to create an auditable handoff record for the next execution-verify stage. It does not make the protected resource registration real.

## Endpoint

```text
POST /api/transit-routes/protected-resource-registration-command-create
```

The endpoint requires an admin session and CSRF token.

## Record Type

The command-create step writes one local `tasks` record:

```text
task_type = protected_resource_registration_command
status = pending_protected_registration_execution
current_step = awaiting_stage_3_4_30_execution_verify
```

The record is a local audit/pending command record only. It is not a `WorkerCommand` and is not consumed by the Worker remote execution flow.

## Required Source

The request must reference a successful Stage 3.4.28 approval dry-run result:

```text
dry_run = true
stage = 3.4.28
mode = approval_dry_run
approved_for_next_stage = true
ready_for_command_create_next_stage = true
```

The endpoint also requires explicit confirmations that this stage remains local and non-destructive.

## Idempotency

The endpoint computes an idempotency key from the source approval summary, normalized approval preview, and safety boundary.

If an existing protected registration command record already has the same idempotency key, the endpoint returns the existing record with:

```text
idempotent_reuse = true
```

It does not create duplicate pending command records for the same approved payload.

## Frontend

The frontend entry is limited to the Advanced Debug HAProxy panel.

It lets an operator:

- reuse the current Stage 3.4.28 approval dry-run result
- paste a copied Stage 3.4.28 approval dry-run result
- preview the command-create payload
- copy the command-create payload
- confirm the safety boundary
- create the local pending command record
- view `command_id`, `command_status`, `idempotency_key`, and blocked reasons
- clear the command draft

No ordinary product page is changed.

## Safety Boundary

This stage does not:

- create a real transit resource
- create a real landing node
- create a `WorkerCommand`
- create a `TransitRoute`
- create a HAProxy route
- bind or change a listener port
- run SSH or remote commands
- install, start, stop, or reload HAProxy
- change firewall, cloud firewall, or cloud security groups
- perform cutover
- read, output, or modify complete client configuration values
- modify `nodes.share_link`
- write `transit_routes.share_link`
- modify ordinary product UI
- modify Worker, docker-compose, or migrations

The response intentionally avoids echoing the full source approval payload. It returns only a sanitized command summary and explicit safety flags.

## Next Stage

If command creation succeeds, the recommended next stage is:

```text
Stage 3.4.30-protected-resource-registration-execution-verify
```

That later stage must be separately reviewed before any protected execution verification is added.
