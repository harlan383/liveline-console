# Stage 3.3.153 HAProxy Create Result Persist Parity

## Stage Goal

Stage 3.3.153 fixes backend result ingestion after a protected HAProxy TCP route create succeeds.

Before this stage, `persist_successful_transit_route_create_result` still assumed the real-create result was always a socat route. That meant a successful HAProxy Worker result could pass remote execution but fail to persist an active `transit_routes` record.

This stage keeps the existing socat behavior and adds HAProxy TCP parity for result validation and route persistence.

## Backend Fix

The result ingestion flow now normalizes supported forwarding methods:

- `socat`
- `haproxy`
- `haproxy_tcp`

`haproxy` is normalized to `haproxy_tcp` before validation and persistence.

Expected route artifacts are derived from the forwarding method:

| Method | Service name | Service path | Config path |
| --- | --- | --- | --- |
| `socat` | `liveline-socat-<port>.service` | `/etc/systemd/system/liveline-socat-<port>.service` | none |
| `haproxy_tcp` | `liveline-haproxy-<port>.service` | `/etc/systemd/system/liveline-haproxy-<port>.service` | `/etc/haproxy/liveline/routes/liveline-haproxy-<port>.cfg` |

For HAProxy TCP real-create results, the backend validates:

- `status=succeeded`
- `execution_mode=real_create`
- `real_execution=true`
- Approved listen port
- Approved landing target host and port
- Approved forwarding method
- Approved route name
- Expected HAProxy service name
- Expected HAProxy service path
- Expected HAProxy config path when the Worker returns `config_path`

When validation succeeds, the backend creates an active `TransitRoute` record with:

- `forwarding_method=haproxy_tcp`
- HAProxy service name/path
- `status=active`
- `share_link=NULL`

Existing duplicate protection by `transit_resource_id` and `listen_port` is preserved. If the active route already exists, result ingestion returns the existing route without inserting a duplicate record.

## Safety Boundary

This stage does not:

- Execute SSH or remote commands
- Deploy the controller
- Upgrade a remote Worker
- Create a Worker command
- Execute a real HAProxy create command
- Delete or modify the existing `23843` route
- Install HAProxy
- Bind any listen port
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
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Related backend tests for transit route create result persistence
- Sensitive information scan

No Worker binary rebuild is required because this stage does not change Worker code.

No frontend build is required because this stage does not change frontend code.
