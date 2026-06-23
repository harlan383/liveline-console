# Stage 3.3.139 New Transit HAProxy Route Create Real Execution

## Stage Goal

Stage 3.3.139 adds the protected real-execution entry for the approved HAProxy TCP route:

- Route name: `haproxy-tcp-23843`
- Planned service: `liveline-haproxy-23843.service`
- Listen port: `23843`
- Target: `64.90.13.19:27939`
- Forwarding method: `haproxy_tcp`

This PR adds the code path only. It does not deploy the controller, does not upgrade the remote Worker, does not create a Worker command during development, and does not create a real HAProxy route.

## Preconditions

The real-execution entry requires:

- Stage 3.3.137 HAProxy route dry-run command exists.
- Dry-run command status is `succeeded`.
- Dry-run payload is a HAProxy TCP dry-run with matching route parameters.
- Stage 3.3.138 final approval text is provided.
- The new real-execution confirmation text is provided:

```text
CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843
```

The endpoint rechecks the transit resource, landing node, transit Worker role/status/version/interface, firewall confirmations, no-cutover confirmation, and no share-link/full-link confirmations before creating any Worker command.

## Backend API

The backend adds:

- `TransitHaproxyRouteCreateRealExecutionRequest`
- `POST /api/transit-routes/haproxy-route-create-real-execution`

If any check is blocked, the endpoint returns a blocked result and does not create a Worker command.

If all checks pass, it creates exactly one protected `transit_route_create` Worker command with:

- `command_intent=haproxy_route_create_real_execution`
- `approval_stage=Stage 3.3.139-new-transit-haproxy-route-create-real-execution`
- `dry_run=false`
- `approval_required=false`
- `execution_mode=real_create`
- `approved_real_execution=true`
- `forwarding_method=haproxy_tcp`
- fixed listen/target/service parameters

The endpoint itself does not create a `TransitRoute` active record. A route record is expected only after the Worker executes successfully and command result ingestion accepts the success result.

## Worker Validation

The Worker HAProxy real-create validator now requires the Stage 3.3.139 approval stage for `haproxy_tcp` real execution.

The existing socat real-create path remains on its historical Stage 3.3.73d approval stage.

## Frontend UX

The transit routes advanced panel now exposes Stage 3.3.139 only after final approval returns `ready_for_real_create=true`.

The operator must type:

```text
CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843
```

before the `创建真实 HAProxy TCP route` button is enabled.

The result area displays whether a Worker command was created and shows blocked checks when the backend refuses execution.

## Safety Boundary

This stage does not:

- Deploy the controller
- Execute SSH or remote commands
- Create a Worker command during local development or tests
- Create a real execution command outside the protected API
- Create a HAProxy route during this PR
- Create a `TransitRoute` active record directly
- Install HAProxy
- Bind `23843`
- Modify firewall, cloud firewall, or cloud security group
- Modify Xray or the landing node
- Read, print, or record full `nodes.share_link`
- Write `transit_routes.share_link`
- Generate, show, log, or document a full VLESS/V2Ray client link
- Cut over traffic

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Backend tests for HAProxy real-execution approval and command creation
- Go tests/build if Worker source changed
- Frontend production build
- Sensitive information scan
