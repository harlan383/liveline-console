# Stage 3.4.21 Advanced Debug UI Rebuild HAProxy Runtime Readiness

## Scope

Stage 3.4.21 rebuilds the current Advanced Debug page and focuses it on HAProxy TCP runtime readiness debugging.

This stage changes only the advanced debug frontend surface. It does not change ordinary product pages, backend routes, database schema, Worker binaries, deployment configuration, or live infrastructure.

## UI Changes

- `AdvancedDebugPanel` no longer renders the old `SystemStatus`, `ServerManagementPanel`, `TransitServersPanelWithWorkerFolding`, `TransitRoutesPanel`, or `TransitTopologyPreviewPanel` stack on the current Advanced Debug page.
- The old components and APIs are retained in the codebase.
- A new Advanced Debug window is rendered for HAProxy TCP runtime readiness and protected real-execution command creation.
- The page includes the reference-style shell, tabs, status cards, parameter form, firewall confirmations, safety confirmations, readiness result cards, checks list, task detail area, and redacted JSON panels.

## Runtime Readiness

The new UI calls:

```text
POST /api/transit-routes/haproxy-route-real-execution-readiness
```

The readiness action is read-only. It returns:

- `ready_for_real_execution`
- `blocked`
- `summary`
- `next_action`
- `expected_real_execution_text`
- target Worker metadata
- planned HAProxy service and route fields
- runtime checks
- explicit safety flags

The UI uses the backend-returned `expected_real_execution_text` and does not hard-code the old `23843` confirmation text.

## Real Execution Protection

The UI includes a protected real-execution command action. It remains disabled unless:

- Runtime readiness returned `ready_for_real_execution=true`.
- The entered `real_execution_text` matches the backend-returned `expected_real_execution_text`.
- All firewall and safety confirmation checkboxes are selected.
- The operator enters `CONFIRM_CREATE_HAPROXY_REAL_EXECUTION_COMMAND`.

When enabled and submitted, the action calls:

```text
POST /api/transit-routes/haproxy-route-create-real-execution
```

That action creates only a protected WorkerCommand. It does not directly create a HAProxy route, bind a listener, mutate firewalls, mutate share links, or cut over traffic.

## Safety Boundary

This stage does not:

- Change ordinary product UI.
- Change backend routes, schemas, or migrations.
- Change database schema.
- Change Worker binaries.
- Change `docker-compose.yml`.
- SSH to any server.
- Execute remote commands from the readiness action.
- Directly create HAProxy routes from the UI.
- Bind listeners from the UI.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Read or write `nodes.share_link`.
- Write `transit_routes.share_link`.
- Export full client links.
- Perform cutover.
- Commit reference images or screenshots.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- frontend TypeScript typecheck
- frontend production build
- staged diff sensitive scan

Backend compileall is not required unless backend files are changed.
