# Stage 3.3.193 Transit Route Name Edit Button

## Goal

Stage 3.3.193 adds a small edit entry for transit routes so the operator can rename an existing HAProxy TCP route display name after creation.

This is needed for routes created before Stage 3.3.192, where the persisted display name could still be the internal technical route name such as `haproxy-tcp-29833`.

## Scope

This stage only allows editing:

- `transit_routes.name`

It does not allow editing:

- listen port
- target host or target port
- forwarding method
- internal `route_name`
- `service_name` or `service_path`
- HAProxy config
- Worker assignment or Worker version
- `transit_routes.share_link`
- `nodes.share_link`
- cutover state

## Implementation Notes

- The frontend transit-route list now includes an `编辑` action.
- The edit modal contains only the route name input and a short note that real connection parameters are not changed.
- The backend adds `PATCH /api/transit-routes/{route_id}/name`.
- The request body accepts only `{ "name": "..." }`.
- The backend reuses the display-name sanitization from Stage 3.3.192 and rejects empty names, overly long names, links, tokens, passwords, and private-key-like text.
- The response returns safe route metadata and `share_link_present`; it does not return a complete share link.
- Candidate export already uses `transit_routes.name`, so subsequent temporary exports use the updated display name as the client remark.

## Validation

The tests cover:

- Active route rename succeeds.
- Only `name` and `updated_at` are changed.
- Listen port, target port, forwarding method, service fields, `share_link`, and `nodes.share_link` are not changed.
- Empty, overlong, or sensitive-looking names are rejected.
- Deleted routes cannot be renamed.
- Login and CSRF are required.
- Rename response does not include a complete share link.

## Safety Boundary

This stage does not:

- Delete or rebuild any transit route.
- Add a real listener.
- Modify real HAProxy configuration.
- Start, stop, or restart HAProxy.
- Execute SSH or remote commands.
- Perform cutover.
- Write or output a complete share link.
- Modify `nodes.share_link`.
- Modify listen port, target port, forwarding method, or service fields.
- Modify firewall, cloud security group, or cloud firewall rules.
- Modify Docker Compose files.
- Modify Worker code, upgrade Worker version, or rebuild Worker binaries.
