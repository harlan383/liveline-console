# Stage 3.3.122 — HAProxy TCP Worker Create Plan

## Decision

Route-diagnosis tooling is postponed until after HAProxy TCP mode is usable. The immediate next implementation target is:

```text
HAProxy TCP mode real create path
```

This document defines the Worker implementation plan for the next code stage.

## Non-negotiable safety boundary

```text
No cutover.
No existing socat route replacement.
No existing socat service stop/restart/delete.
No Xray mutation.
No firewall mutation.
No cloud security group/cloud firewall mutation.
No transit_routes.share_link write.
No full nodes.share_link read, print, log, or mutation.
No raw shell/systemd/config payload accepted from API.
```

## Target behavior

When `forwarding_method=haproxy_tcp`, the transit Worker should create a dedicated LiveLine-managed HAProxy TCP route:

```text
0.0.0.0:<listen_port> -> <landing_target_host>:<landing_target_port>
```

Recommended route example:

```text
liveline-haproxy-23844.service
/etc/haproxy/liveline/routes/liveline-haproxy-23844.cfg
```

Keep current route unchanged:

```text
liveline-socat-23843.service
```

## Worker version

Next Worker version should be:

```text
0.1.24-stage-3.3.122
```

## Worker command handling

Existing command type can remain:

```text
transit_route_create
```

The Worker should branch by typed payload:

```text
forwarding_method = socat        -> existing socat path
forwarding_method = haproxy_tcp  -> new HAProxy TCP path
```

## HAProxy binary check

The Worker should not install packages during route creation. It should only verify an existing HAProxy binary:

```text
/usr/sbin/haproxy
/usr/bin/haproxy
haproxy from PATH
```

If missing, fail clearly:

```text
HAPROXY_NOT_INSTALLED
```

The UI can later show:

```text
中转 VPS 未安装 HAProxy，请先安装 haproxy 后再创建 HAProxy TCP 链路。
```

## Generated HAProxy config

Worker must generate config from typed fields only:

```text
global
    log /dev/log local0
    maxconn 4096

defaults
    mode tcp
    log global
    option tcplog
    timeout connect 5s
    timeout client 6h
    timeout server 6h

frontend liveline_transit_<listen_port>
    bind 0.0.0.0:<listen_port>
    default_backend liveline_landing_<listen_port>

backend liveline_landing_<listen_port>
    mode tcp
    option tcp-check
    server landing <target_host>:<target_port> check
```

## Generated systemd service

```text
[Unit]
Description=LiveLine HAProxy TCP transit route <listen_port>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=<haproxy_binary> -f <config_path> -db
ExecReload=/bin/kill -USR2 $MAINPID
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

## Validation before write/start

Worker must validate:

```text
transit_worker_id matches current Worker
transit_resource_id matches current Worker server_id
interface_name matches current Worker interface_name
forwarding_method == haproxy_tcp
listen_port valid and not protected
target_host safe
target_port valid
route_name safe
haproxy exists
systemctl exists
config path does not already exist
service path does not already exist
listen port is not already listening
target TCP connect succeeds
```

## Verification after start

After `systemctl enable --now liveline-haproxy-<port>.service`, Worker verifies:

```text
systemctl is-active == active
listen port is listening
transit can TCP-connect to landing target
```

Optional later check:

```text
haproxy -c -f <config_path>
```

## Rollback on failure

If creation fails after writing artifacts:

```text
stop service if started
disable service if enabled
remove service file if written
remove config file if written
systemctl daemon-reload
systemctl reset-failed
verify listen port is not left listening
```

## Result payload

Success result should include only safe structured fields:

```text
status=succeeded
forwarding_method=haproxy_tcp
planned_listen_port
target_host
target_port
service_name
service_path
config_path
worker_version
checks[]
safety_boundary[]
```

Failure result should include:

```text
status=failed
forwarding_method=haproxy_tcp
redacted_error
rollback_attempted
diagnostics redacted/truncated
checks[]
```

No full client links, no secrets, no raw config containing secrets.

## Backend follow-up

A later backend/UI stage must:

```text
Allow haproxy_tcp create execution.
Require matching readonly preflight with forwarding_method=haproxy_tcp.
Require Worker >= 0.1.24-stage-3.3.122.
Set service_name = liveline-haproxy-<listen_port>.service.
Set service_path = /etc/systemd/system/liveline-haproxy-<listen_port>.service.
Keep transit_routes.share_link = NULL.
```

## Public deploy follow-up

After code merge, public deployment requires:

```text
pull latest main on /opt/liveline-console
rebuild backend/frontend if needed
rebuild Worker linux amd64 binary
upgrade transit Worker on the transit VPS
verify Worker heartbeat version
verify existing socat 23843 remains active
verify no HAProxy route is created until user starts one from UI
```

## Port reminder

Any new HAProxy TCP listen port must be allowed in:

```text
cloud security group
cloud firewall
server local firewall
```

Do not modify these automatically unless explicitly approved.
