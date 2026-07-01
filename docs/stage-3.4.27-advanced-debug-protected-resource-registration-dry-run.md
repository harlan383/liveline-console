# Stage 3.4.27 Advanced Debug Protected Resource Registration Dry-run

## Goal

Stage 3.4.27 adds a read-only backend dry-run for the Stage 3.4.26 protected resource registration payload.

The endpoint validates the prepared transit resource and landing node registration draft, compares it with the selected HAProxy TCP dry-run command, checks local duplicate risks, and returns a structured `checks` list. It does not create resources or commands.

## Endpoint

```text
POST /api/transit-routes/protected-resource-registration-dry-run
```

The endpoint requires an admin session and CSRF token. It only runs SELECT queries and in-memory validation.

## Safety Boundary

This stage does not:

- create `transit_resource`
- create landing node records
- create `WorkerCommand`
- create `TransitRoute`
- create HAProxy routes
- bind listener ports
- run SSH or remote commands
- change firewall, cloud firewall, or cloud security groups
- read, output, or modify complete client configuration values
- perform cutover
- modify Worker, docker-compose, or migrations

The implementation must not call `db.add`, `db.commit`, `db.flush`, or `db.refresh`.

## Checks

The dry-run returns checks for:

- expected Stage 3.4.26 source payload and `preview_only` mode
- complete safety boundary and manual confirmations
- source dry-run command existence, `succeeded` status, HAProxy TCP method, and dry-run shape
- source route name, planned listen port, landing host, and landing port consistency
- transit resource draft name, host, SSH entry port, regions, resource type, expected status, Worker role, and Worker binding requirement
- duplicate active or Worker-online transit resources by name or entry host
- landing node draft name, VPS IP, Xray port, expected active status, and safe client configuration handling
- duplicate active landing node by VPS IP and Xray port
- sanitized response content

Warnings do not block the next stage. Danger checks must pass before `ready_for_next_stage` becomes true.

## Next Stage

When the dry-run is ready, the response provides:

```text
Stage 3.4.28-advanced-debug-protected-resource-registration-approval
```

It also returns an expected approval text in this format:

```text
CONFIRM_PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_<planned_listen_port>
```

If the planned listen port is not valid, the suffix is `MANUAL`.

## Result

This stage provides backend validation and frontend visibility only. It remains a protected advanced-debug step and does not make resource registration real.
