# Stage 3.3.192 Transit Route Display Name Preserve

## Goal

Stage 3.3.192 fixes the HAProxy TCP transit-route create flow so the user-entered route display name is preserved instead of being replaced by the internal technical route name.

The production symptom was:

- User-entered display name: `mk香港落地15m`
- Persisted `transit_routes.name`: `haproxy-tcp-29833`

The two names represent different concepts and must not be conflated.

## Name Model

- Display name: the user-facing transit route name shown in the console and used as the client export remark, for example `mk香港落地15m`.
- Internal route name: the protected HAProxy route identifier used for command approval and audit, for example `haproxy-tcp-29833`.
- Service name: the systemd unit name derived from the listen port, for example `liveline-haproxy-29833.service`.

## Implementation Notes

- HAProxy dry-run, final approval, and real execution request schemas now carry an optional `route_display_name`.
- The frontend sends the user-entered form name as `route_display_name` while keeping `route_name` as the internal `haproxy-tcp-<port>` value.
- The backend validates and carries `route_display_name` through dry-run, final approval, real execution, and Worker command payloads.
- The create-result persistence path stores `TransitRoute.name` from the display name when present, with fallback to the internal route name only when no display name was supplied.
- Candidate export continues to use `transit_routes.name` for the client-link remark, so exported temporary links prefer the user-facing display name.

## Safety Boundary

This stage does not:

- Delete or recreate the current successful transit route.
- Add a real listener or create a real transit route.
- Modify HAProxy runtime configuration.
- Start, stop, or restart HAProxy.
- Execute SSH or remote commands.
- Perform cutover.
- Write or output a complete share link.
- Modify `nodes.share_link`.
- Modify firewall, cloud security group, or cloud firewall rules.
- Modify Docker Compose files.
- Modify Worker code, upgrade Worker version, or rebuild Worker binaries.

## Validation

Validation for this stage covers:

- HAProxy TCP real-create result persistence stores the display name in `transit_routes.name`.
- The internal `route_name` remains `haproxy-tcp-<port>`.
- `service_name` remains `liveline-haproxy-<port>.service`.
- Fallback behavior still uses the internal route name when no display name is provided.
- Temporary candidate export remarks prefer `transit_routes.name`.
- No `nodes.share_link` mutation is introduced.
