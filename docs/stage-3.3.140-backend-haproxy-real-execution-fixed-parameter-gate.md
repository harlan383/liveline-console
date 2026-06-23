# Stage 3.3.140 Backend HAProxy Real Execution Fixed Parameter Gate

## Stage Goal

Stage 3.3.140 hardens the Stage 3.3.139 HAProxy real-execution entry by mirroring the Worker fixed-parameter policy in the backend gate before creating any WorkerCommand.

Approved HAProxy real-create parameters remain:

- Route name: `haproxy-tcp-23843`
- Planned service: `liveline-haproxy-23843.service`
- Listen port: `23843`
- Target: `64.90.13.19:27939`
- Forwarding method: `haproxy_tcp`
- Approval stage: `Stage 3.3.139-new-transit-haproxy-route-create-real-execution`

## Backend Behavior

Before delegating to the Stage 3.3.139 real-execution handler, the backend now checks the request and the matched dry-run payload for the fixed approved HAProxy parameters.

The backend blocks before WorkerCommand creation if any of these differ:

- `planned_listen_port != 23843`
- `landing_target_host != 64.90.13.19`
- `landing_target_port != 27939`
- `route_name != haproxy-tcp-23843`
- `planned_service_name != liveline-haproxy-23843.service`
- `forwarding_method != haproxy_tcp`

This does not replace Worker validation. It prevents the backend from queuing a doomed real-execution WorkerCommand when the dry-run evidence or request is outside the fixed approved HAProxy route.

## Implementation Notes

The stage adds a small backend guard module that installs a wrapped route before the main app includes the transit routes router. The wrapper performs the fixed-parameter check and then delegates to the existing Stage 3.3.139 handler when the parameters are approved.

The existing Worker source and bundled Worker binary are not changed in this stage.

## Safety Boundary

This stage is code-path only.

This stage did not and must not:

- Deploy the controller
- Rebuild bundled Worker binaries
- Deploy or restart any Worker
- Create a Worker command during development or review
- Create a real HAProxy route
- Create a `TransitRoute` active record
- Install, start, stop, or reload HAProxy
- Bind `23843` or any other listener
- Modify firewall, cloud firewall, or cloud security group
- SSH or execute remote commands
- Read, output, log, or write full `nodes.share_link`
- Write `transit_routes.share_link`
- Generate a full VLESS/V2Ray client link
- Cut over traffic

## Validation

Planned validation:

- Backend compile check
- Unit tests for approved fixed-parameter gate
- Regression test that valid approved parameters still pass to the existing Stage 3.3.139 handler
- Sensitive information scan

Local validation may be limited when the local Python environment lacks FastAPI or Docker is unavailable.
