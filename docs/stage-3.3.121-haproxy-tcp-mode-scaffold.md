# Stage 3.3.121 — HAProxy TCP Mode Scaffold

## Scope

This stage adds the system-level scaffold for a future `haproxy_tcp` forwarding method while preserving the current working `socat` transit route.

Current production route remains unchanged:

```text
hk-socat-live-23843
forwarding_method = socat
listen_port = 23843
target = 64.90.13.19:27939
transit_routes.share_link = NULL
```

## Why HAProxy TCP mode

HAProxy TCP mode is a Layer 4 forwarding mode. It relays TCP streams without parsing HTTP, which is suitable for transparent forwarding from a transit VPS to the landing Reality/Xray TCP listener. HAProxy also supports TCP health checks, making it a better long-term production forwarding method than a bare `socat` process.

## Safety boundary

This stage is only a scaffold:

```text
No cutover.
No firewall mutation.
No cloud security group mutation.
No server firewall mutation.
No existing socat service stop/restart/delete.
No Xray mutation.
No Worker command execution for HAProxy.
No transit_routes.share_link write.
No nodes.share_link read, print, log, or mutation.
No full VLESS/V2Ray link written to docs, PR, logs, or chat.
```

## Added forwarding method identifier

The canonical new method name is:

```text
haproxy_tcp
```

Accepted aliases at schema-normalization level:

```text
haproxy
haproxy_tcp
haproxy-tcp
```

The stored and transmitted canonical value should always be:

```text
haproxy_tcp
```

## Worker implementation required in the next stage

A later stage should upgrade the Worker and implement real HAProxy execution. The Worker should generate a fixed LiveLine-managed HAProxy config and systemd service from typed fields only. It must not accept raw shell, raw systemd units, raw config text, or arbitrary command payloads.

Recommended generated files for one route:

```text
/etc/haproxy/liveline/routes/liveline-haproxy-<listen_port>.cfg
/etc/systemd/system/liveline-haproxy-<listen_port>.service
```

Recommended HAProxy template:

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

Recommended systemd wrapper:

```text
[Unit]
Description=LiveLine HAProxy TCP transit route <listen_port>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/sbin/haproxy -f /etc/haproxy/liveline/routes/liveline-haproxy-<listen_port>.cfg -db
ExecReload=/bin/kill -USR2 $MAINPID
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

## Required Worker validations for real execution

Before writing files or starting HAProxy, Worker must verify:

```text
payload.transit_worker_id == current Worker id
payload.transit_resource_id == current Worker config server_id
payload.interface_name == current Worker interface_name
payload.forwarding_method == haproxy_tcp
planned_listen_port is valid and not protected
landing_target_host is a safe IP/hostname
landing_target_port is valid
matching successful readonly preflight exists
/usr/sbin/haproxy or haproxy binary exists
systemctl exists
service path does not already exist
config path does not already exist
the planned listen port is not already listening
transit can TCP-connect to the landing target
```

## Required backend behavior for real execution

A later backend stage should keep the current `socat` route untouched and add an explicit HAProxy create path. It should not silently convert the existing fixed `socat` route to HAProxy.

Recommended backend behavior:

```text
socat route creation continues to work as it does today.
haproxy_tcp requires a newer Worker minimum version.
haproxy_tcp requires successful readonly preflight with the same forwarding_method.
haproxy_tcp service_name should be liveline-haproxy-<listen_port>.service.
haproxy_tcp service_path should be /etc/systemd/system/liveline-haproxy-<listen_port>.service.
transit_routes.share_link remains NULL.
client candidate link remains transient/export-only.
```

## Required cleanup behavior

Remote cleanup must become method-aware:

```text
socat         -> validate and remove only liveline-socat-<port>.service
haproxy_tcp   -> validate and remove only liveline-haproxy-<port>.service and its LiveLine-owned config file
gost          -> no new behavior unless separately approved
```

For `haproxy_tcp`, cleanup must first verify the service and config are LiveLine-owned and match the specific listen port before stop/disable/remove.

## UI requirements for a later full feature stage

The UI should show:

```text
socat — 当前已验证，简单透明
HAProxy TCP mode — 推荐长期稳定，支持 TCP health check
```

The create modal should warn:

```text
选择 HAProxy TCP mode 前，中转 VPS 必须已安装 haproxy，并且监听端口必须已在云安全组、云防火墙、服务器本机防火墙放行。
```

## Current stage result

This stage only introduces the schema-level method scaffold and documents the safe full implementation path. It does not deploy HAProxy and does not modify the current live route.
