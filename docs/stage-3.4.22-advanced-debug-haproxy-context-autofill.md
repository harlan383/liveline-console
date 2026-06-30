# Stage 3.4.22 Advanced Debug HAProxy Context Autofill

## Scope

Stage 3.4.22 adds context autofill only to the Advanced Debug HAProxy Runtime Readiness page.

This stage does not change the ordinary product UI. It does not change customer-facing line builder flows, server resource screens, customer lines, overview, authentication, Worker behavior, database schema, docker-compose, or deployment ports.

## Context Autofill

The Advanced Debug page can now load sanitized local control-plane context for HAProxy TCP readiness debugging:

- Transit resource candidates.
- Landing node candidates.
- Recent HAProxy TCP dry-run WorkerCommand candidates.

After selecting a dry-run candidate, the operator can fill the readiness payload fields:

- `dry_run_command_id`
- `transit_resource_id`
- `landing_node_id`
- `planned_listen_port`
- `landing_target_host`
- `landing_target_port`
- `forwarding_method`
- `route_name`
- `route_display_name`
- `approval_stage`
- `final_approval_text`
- `real_execution_text`

Autofill does not check firewall confirmation boxes. It does not run readiness. It does not create a real-execution WorkerCommand. Operators must still manually confirm every firewall and safety checkbox, run readiness explicitly, and pass the protected real-execution confirmation flow.

## Endpoint

This stage adds:

```text
GET /api/transit-routes/haproxy-runtime-debug-context
```

The endpoint is read-only and requires an admin session. It returns only whitelisted, sanitized fields:

- `transit_resources`
- `landing_nodes`
- `haproxy_dry_run_commands`
- `generated_at`
- `safety_boundary`

The dry-run command list only includes HAProxy TCP dry-run candidates and does not expose raw `payload_json`. It does not return full client links, tokens, private keys, install commands, or secrets.

## Safety Boundary

This stage preserves these boundaries:

- No ordinary product UI changes.
- No live VPS operation.
- No SSH.
- No remote execution.
- No WorkerCommand creation by autofill.
- No TransitRoute creation.
- No listener binding.
- No firewall, cloud firewall, or cloud security group mutation.
- No share_link export.
- No full client link exposure.
- No cutover.
- No migration.
- No Worker binary change.
- No docker-compose change.

## Validation

Planned validation:

- `git diff --check`
- `git diff --cached --check`
- frontend typecheck
- frontend production build
- `PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `PYTHONPATH=backend python3 -m unittest backend.tests.test_stage_3_4_22_haproxy_context_autofill`
- staged diff sensitive scan
