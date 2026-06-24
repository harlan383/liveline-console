# Stage 3.3.152 HAProxy Parity Cleanup And Worker Install

## Stage Goal

Stage 3.3.152 closes the HAProxy TCP parity gap with the existing socat cleanup flow.

The stage adds:

- Backend cleanup planning for `haproxy_tcp` transit routes.
- Mixed transit-resource cleanup planning for socat and HAProxy TCP routes.
- Worker-side protected HAProxy cleanup validation and execution.
- A new Worker version gate for HAProxy cleanup.
- Standard Worker install script write access for `/etc/haproxy` and `/run/haproxy`.
- Transit route UI status/copy fixes so active HAProxy routes are not shown as socat candidates.

This stage does not execute any production cleanup and does not create a new route.

## Backend Cleanup

The backend now generates HAProxy cleanup plans only for LiveLine-managed route artifacts:

- Service name: `liveline-haproxy-<port>.service`
- Service path: `/etc/systemd/system/liveline-haproxy-<port>.service`
- Config path: `/etc/haproxy/liveline/routes/liveline-haproxy-<port>.cfg`

`cleanup_transit_resource` can now plan mixed route cleanup:

- `socat` routes use the existing socat cleanup plan.
- `haproxy_tcp` routes use the new HAProxy cleanup plan.
- Unsupported forwarding methods block command creation with an explicit error.

Cutover and stored share-link checks remain blocking. Offline local remove remains a local-only soft remove and does not stop HAProxy, delete config, or release a remote listen port.

## Worker Cleanup

The Worker version is bumped to:

```text
0.1.28-stage-3.3.152-haproxy-cleanup-support
```

For `haproxy_tcp` cleanup, the Worker validates:

- `forwarding_method=haproxy_tcp`
- Valid listen and target ports
- Exact LiveLine service name/path
- Exact LiveLine HAProxy config path
- `systemctl cat` content matches a LiveLine HAProxy route service
- HAProxy config contains the expected bind port and landing target

Only after those checks pass does the Worker stop/disable the service, remove the service file, remove the route config, reload systemd, reset failed state, and verify the listen port is no longer listening.

If any validation or cleanup step fails, the Worker returns a failed cleanup result and the backend must keep the system record.

## Worker Version Gate

Existing socat cleanup keeps the existing minimum Worker version.

HAProxy cleanup requires:

```text
0.1.28-stage-3.3.152-haproxy-cleanup-support
```

If a transit resource contains any `haproxy_tcp` route, resource cleanup also requires this version.

## Worker Install Script

The standard Worker install script now prepares:

- `/etc/haproxy/liveline/routes`
- `/run/haproxy`

The systemd `ReadWritePaths` includes:

```text
/etc/haproxy /run/haproxy
```

The install script still does not open ports, does not modify cloud security groups or cloud firewalls, and does not create HAProxy routes by itself.

## Frontend UX

The transit route page now derives the active route summary from the actual active route instead of a fixed socat candidate route.

For `haproxy_tcp` routes:

- The route displays as HAProxy TCP mode.
- The delete dialog says remote cleanup will stop/delete the HAProxy service and config.
- Offline local remove warns that it does not stop the remote HAProxy service and does not release the listen port.

## Safety Boundary

This stage does not:

- Execute SSH or remote commands
- Deploy the controller
- Upgrade a remote Worker
- Execute real cleanup
- Delete the existing `23843` service
- Create a new transit route
- Create a Worker command during development
- Install HAProxy
- Bind a listen port
- Modify firewall, cloud firewall, or cloud security group
- Modify Xray
- Read or output full `nodes.share_link`
- Write `transit_routes.share_link`
- Generate or output a full VLESS/V2Ray link
- Cut over traffic

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app`
- Worker `go test ./...`
- Frontend production build
- Bundled Linux amd64 Worker binary marker check
- Sensitive information scan
