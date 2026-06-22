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

## Current code progress

This stage added the Worker-side HAProxy helper file:

```text
worker/cmd/liveline-worker/transit_haproxy.go
```

The helper currently provides:

```text
haproxy_tcp method normalization
LiveLine-owned HAProxy service/config naming
HAProxy binary detection
fixed HAProxy TCP config generation
fixed service generation
pre-write path availability checks
root/service manager checks
planned listen-port collision checks
transit-to-landing TCP reachability check
HAProxy config validation command
service enable/start flow
post-start active/listen verification
redacted diagnostics
safe rollback for only LiveLine-owned HAProxy artifacts
```

Stage 3.3.122-c added backend version helpers for forwarding-method-aware targeting:

```text
minimum_worker_version_for_transit_forwarding_method()
minimum_worker_version_key_for_transit_forwarding_method()
worker_supports_transit_forwarding_method()
```

This lets later backend/UI code require Worker `0.1.24-stage-3.3.122` for `haproxy_tcp` while preserving the existing `socat` minimum Worker version.

## Stage 3.3.122-d main.go patch

The local Codex patch has been applied and pushed as commit:

```text
f0e28f0
```

Worker version is now:

```text
0.1.24-stage-3.3.122
```

The Worker real-create entry now branches by forwarding method:

```go
func executeTransitRouteCreateReal(cfg config, hostname string, request transitRouteCreateRequest) (map[string]any, error) {
	if isTransitHaproxyForwardingMethod(request.ForwardingMethod) {
		request.ForwardingMethod = transitHaproxyForwardingMethod
		return executeTransitRouteCreateHaproxy(cfg, hostname, request)
	}

	if err := validateTransitRouteCreateRealRequest(cfg, request); err != nil {
		return nil, err
	}
	// existing socat path continues unchanged below
}
```

Expected routing:

```text
forwarding_method=socat
  -> existing fixed socat path remains unchanged

forwarding_method=haproxy_tcp / haproxy / haproxy-tcp
  -> executeTransitRouteCreateHaproxy()
```

Local validation reported for commit `f0e28f0`:

```text
gofmt -w worker/cmd/liveline-worker/main.go worker/cmd/liveline-worker/transit_haproxy.go: passed
cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./cmd/liveline-worker: passed
cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./cmd/liveline-worker: passed
git diff --check: passed
git diff --cached --check: passed
git status: clean
```

Note: root-level `go test ./worker/cmd/liveline-worker` and `go build ./worker/cmd/liveline-worker` fail because the repository root has no Go module; validation must run from the `worker` module directory.

## Target HAProxy route artifacts

For `forwarding_method=haproxy_tcp`, Worker creates only LiveLine-owned files:

```text
/etc/haproxy/liveline/routes/liveline-haproxy-<listen_port>.cfg
/etc/systemd/system/liveline-haproxy-<listen_port>.service
```

## Worker validations before write/start

Worker validates all of these before creating files:

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
service manager exists
config path does not already exist
service path does not already exist
listen port is not already listening
transit can TCP-connect to the landing target
```

## Rollback rules

If creation fails after artifacts were written:

```text
stop service if started
disable service if enabled
remove service file if written
remove config file if written
reload service manager
reset failed state
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

Stage 3.3.122-e review confirmed the Worker helper, main real-create branch, and backend forwarding-method version helpers are in PR #196. Remote deploy, Worker binary replacement on the transit VPS, and real HAProxy route creation are not part of this stage.
