# Stage 3.3.167 Delete Result And Empty State

## Goal

Stage 3.3.167 records the successful UI-driven remote cleanup delete result for the former HAProxy TCP `23843` transit route and verifies the user-facing empty state after active transit routes become empty.

This stage does not restore `23843`, create a new transit route, create Worker commands, connect to remote servers, cutover, or modify share links.

## Delete Test Conclusion

Stage 3.3.166 executed remote cleanup delete through the LiveLine Console UI delete button. The deletion was not performed manually through SSH.

The cleanup Worker command completed successfully:

- Command id: `6a741cd0-8195-42fe-9288-74bcfbd8697f`
- Command type: `cleanup_transit_route`
- Status: `succeeded`
- Server type: `transit`
- Server id: `80ec346d-3ac1-402e-ab09-33cb404ca81c`
- Error message: empty

Result:

- UI remote cleanup delete passed.
- Remote HAProxy service was cleaned up.
- Remote HAProxy route config was cleaned up.
- Port `23843` was released.
- The database route record was soft-deleted.
- Active transit routes are now empty.
- `nodes.share_link` was not modified.
- `transit_routes.share_link` was not written.

`109.244.79.147:23843` is now unavailable. This is the expected result of the delete test.

## Database Acceptance Result

Deleted transit route:

- Route id: `28a9d585-4377-46f1-a1f3-dfd78c08616e`
- Name: `haproxy-tcp-23843`
- Status: `deleted`
- Forwarding method: `haproxy_tcp`
- Entry before deletion: `109.244.79.147:23843`
- Target: `64.90.13.19:27939`
- Service name: `liveline-haproxy-23843.service`
- Service path: `/etc/systemd/system/liveline-haproxy-23843.service`
- `share_link_present`: `false`
- `deleted_at`: `2026-06-24 12:18:34.609586+00`

Active transit routes:

- `0 rows`

Landing node:

- Node id: `7cf3ec9c-8e76-418e-97c1-5ee3ddb28e31`
- Node name: `liveline-reality-27939`
- Status: `active`
- Service status: `active`
- Connectivity status: `not_checked`
- `nodes.share_link_present`: `true`
- `share_link_length`: `250`
- `deleted_at`: empty

The landing node remained active and was not affected by the transit route cleanup.

## Remote Acceptance Result

Remote MKiepl acceptance after cleanup:

- `liveline-haproxy-23843.service`: inactive / unit not found
- `/etc/systemd/system/liveline-haproxy-23843.service`: removed
- `/etc/haproxy/liveline/routes/liveline-haproxy-23843.cfg`: removed
- Port `23843`: no longer listening
- Route-specific HAProxy process using `/etc/haproxy/liveline/routes/liveline-haproxy-23843.cfg -db`: not present
- Default system HAProxy master process: still present and unrelated, expected to remain

## Current System State

The system currently has no active transit route.

Implications:

- `109.244.79.147:23843` can no longer be used.
- Temporary export for `haproxy-tcp-23843` is no longer applicable because the corresponding transit route has been deleted.
- The landing node remains available and retained.
- If transit access is needed again, a new HAProxy TCP route must be created through the protected route creation flow.

## Empty State UI Acceptance

The transit routes page now clarifies the empty state:

- There is no active transit route.
- If this follows the delete test, the empty state is expected.
- Deleted routes no longer listen on their port and should not be shown as usable lines.
- To use transit again, create a new transit route through the protected flow.

This keeps ordinary users from assuming `23843` is still available after cleanup.

## Safety Boundary

Stage 3.3.167 did not:

- restore `23843`,
- create a new transit route,
- click create route real execution,
- click delete, remote cleanup, or offline local remove,
- create Worker commands,
- SSH or execute remote commands,
- cutover,
- write `transit_routes.share_link`,
- modify `nodes.share_link`,
- output a complete share link,
- modify firewall, cloud security group, or cloud firewall rules,
- add a listener,
- install or restart HAProxy, Xray, socat, or gost,
- modify public-controller `docker-compose.yml`,
- commit `.bak` files.
