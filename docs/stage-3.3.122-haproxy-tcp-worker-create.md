# Stage 3.3.122 — HAProxy TCP Worker Create

## Stage entry

Stage 3.3.122 starts after Stage 3.3.121 was merged into main.

Baseline main commit:

```text
7147b649a030ebe07a00f00f39961f3f04d00bf7
```

## Priority

The user decided:

```text
Do HAProxy TCP mode first.
Postpone diagnosis / fault attribution tooling until the end.
```

## Goal

Implement HAProxy TCP mode as a first-class transit forwarding method without disrupting the current working socat chain.

Current production chain remains untouched:

```text
hk-socat-live-23843
forwarding_method = socat
listen_port = 23843
target = 64.90.13.19:27939
service = liveline-socat-23843.service
transit_routes.share_link = NULL
```

## Safety boundary

```text
No cutover.
No firewall mutation.
No cloud security group mutation.
No cloud firewall mutation.
No existing socat service stop/restart/delete.
No Xray mutation.
No nodes.share_link full read, print, log, or mutation.
No transit_routes.share_link write.
No full VLESS/V2Ray link in docs, PR, logs, or chat.
No arbitrary shell/systemd/config payload from API.
```

## Target Worker version

```text
0.1.24-stage-3.3.122
```

## Target HAProxy route artifacts

For `forwarding_method=haproxy_tcp`, Worker should create only LiveLine-owned files:

```text
/etc/haproxy/liveline/routes/liveline-haproxy-<listen_port>.cfg
/etc/systemd/system/liveline-haproxy-<listen_port>.service
```

Service naming rule:

```text
liveline-haproxy-<listen_port>.service
```

Config naming rule:

```text
liveline-haproxy-<listen_port>.cfg
```

## HAProxy config template

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

## systemd service template

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

## Worker validations before write/start

Worker must validate all of these before creating files:

```text
transit_worker_id matches current Worker id
transit_resource_id matches current Worker server_id
interface_name matches current Worker interface_name
forwarding_method == haproxy_tcp
planned_listen_port is valid and not protected
landing_target_host is safe
landing_target_port is valid
route_name is safe
haproxy binary exists
systemctl exists
config path does not already exist
service path does not already exist
listen port is not already listening
transit can TCP-connect to the landing target
```

## Worker verification after start

After `systemctl enable --now liveline-haproxy-<port>.service`, Worker must verify:

```text
systemctl is-active == active
listen port is listening
transit can TCP-connect to landing target
```

Optional but recommended:

```text
haproxy -c -f <config_path>
```

## Rollback rules

If creation fails after artifacts were written:

```text
stop service if started
disable service if enabled
remove service file if written
remove config file if written
systemctl daemon-reload
systemctl reset-failed
verify listen port is no longer listening
```

## Backend/UI follow-up

After Worker support exists:

```text
Backend should allow haproxy_tcp for protected create.
Backend should require matching readonly preflight with forwarding_method=haproxy_tcp.
Backend should require Worker >= 0.1.24-stage-3.3.122.
Frontend should allow choosing socat or HAProxy TCP mode.
Frontend should warn that HAProxy must already be installed on the transit VPS.
```

## Port reminder

Every new HAProxy TCP listen port must be manually allowed in:

```text
cloud security group
cloud firewall
server local firewall
```

Do not modify firewalls automatically unless the user explicitly approves.

## Stage status

This stage is entered and ready for code implementation. Remote deploy, Worker binary replacement, and real HAProxy route creation are not part of this entry commit.
