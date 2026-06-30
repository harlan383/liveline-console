# Stage 3.4.16 Server Resource Real Bootstrap Flow

## Summary

Stage 3.4.16 connects the product-facing server resource entry points to the existing safe Worker bootstrap APIs.

- The product UI `添加落地服务器` modal now calls `POST /api/vps/worker-bootstrap`.
- The product UI `添加中转服务器` modal now calls `POST /api/transit-resources/worker-bootstrap`.
- Both flows fetch CSRF through `GET /api/auth/csrf` before submitting.
- A successful response is shown only in transient modal state so the administrator can manually copy the one-time Worker install command.
- The parent product pages refresh their server/resource data after a successful bootstrap creation.

## UI Behavior

The landing-server bootstrap modal collects:

- Server name
- Server public IP
- Network interface name
- Command expiry duration

The transit-server bootstrap modal collects:

- Transit server name
- Transit VPS public IP
- Network interface name
- Command expiry duration

After success, the modal shows:

- Resource name
- Public IP
- Expiry time
- A read-only install command field
- A copy button

Closing the modal clears the install command state.

## Safety Boundary

This stage only creates bootstrap metadata and returns a one-time install command to the authenticated administrator.

This stage does not:

- SSH to any VPS
- Execute remote commands
- Install Worker automatically
- Create a Worker command
- Create a direct node
- Create a transit route
- Create HAProxy / Xray / systemd forwarding configuration
- Add a listener port
- Modify cloud security groups, cloud firewall, or server firewall
- Read, write, or output `share_link`
- Perform cutover
- Modify `docker-compose.yml`
- Add database migrations
- Modify Worker binaries

The install command contains a one-time token. It must not be written to README, docs, PR descriptions, chat records, task logs, browser storage, or Git history.

## Remaining Demo-Only Areas

The product UI still keeps these actions demo-only:

- New direct node
- New transit line
- Provider transit entry

Those flows need separate reviewed stages before connecting to real creation APIs.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- frontend TypeScript check
- frontend Next build

Backend compile is not required if no backend files are changed.
