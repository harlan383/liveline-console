# Stage 3.3.122-d — main.go Codex Patch Instructions

## Purpose

Patch `worker/cmd/liveline-worker/main.go` locally with Codex so HAProxy TCP mode can be wired into the Worker real-create path safely.

This patch should be applied locally because `main.go` is a large file and must be protected by:

```text
gofmt
go test
go build
```

## Safety boundary

```text
Do not stop, restart, delete, or replace the current socat service.
Do not create a real HAProxy route during this patch.
Do not deploy the Worker binary during this patch.
Do not change firewall, cloud security group, or cloud firewall rules.
Do not read, print, log, or mutate full nodes.share_link.
Do not write transit_routes.share_link.
No cutover.
```

## Files to edit

```text
worker/cmd/liveline-worker/main.go
```

## Patch 1 — Worker version

Find:

```go
const workerVersion = "0.1.23-stage-3.3.117"
```

Replace with:

```go
const workerVersion = "0.1.24-stage-3.3.122"
```

## Patch 2 — route create real execution branch

Find this function:

```go
func executeTransitRouteCreateReal(cfg config, hostname string, request transitRouteCreateRequest) (map[string]any, error) {
	if err := validateTransitRouteCreateRealRequest(cfg, request); err != nil {
		return nil, err
	}
```

Replace only the function opening block with:

```go
func executeTransitRouteCreateReal(cfg config, hostname string, request transitRouteCreateRequest) (map[string]any, error) {
	if isTransitHaproxyForwardingMethod(request.ForwardingMethod) {
		request.ForwardingMethod = transitHaproxyForwardingMethod
		return executeTransitRouteCreateHaproxy(cfg, hostname, request)
	}

	if err := validateTransitRouteCreateRealRequest(cfg, request); err != nil {
		return nil, err
	}
```

Leave the existing socat implementation below unchanged.

## Expected behavior after patch

```text
forwarding_method=socat
  -> existing fixed socat path remains unchanged

forwarding_method=haproxy_tcp or haproxy or haproxy-tcp
  -> new executeTransitRouteCreateHaproxy() path
```

## Local validation commands

Run from repository root:

```bash
gofmt -w worker/cmd/liveline-worker/main.go worker/cmd/liveline-worker/transit_haproxy.go

go test ./worker/cmd/liveline-worker

go build ./worker/cmd/liveline-worker
```

If the repository build convention requires a binary artifact, rebuild Linux amd64 Worker after tests pass:

```bash
GOOS=linux GOARCH=amd64 go build -o backend/worker-binaries/liveline-worker-linux-amd64 ./worker/cmd/liveline-worker
```

## Post-patch commit checklist

Before committing:

```bash
git diff -- worker/cmd/liveline-worker/main.go worker/cmd/liveline-worker/transit_haproxy.go backend/worker-binaries/liveline-worker-linux-amd64

git status --short
```

Confirm:

```text
workerVersion is 0.1.24-stage-3.3.122
socat code path remains unchanged below the new branch
haproxy_tcp branch is only selected when request.ForwardingMethod matches HAProxy
no remote command was executed locally except tests/builds
no full share link appears in diff
```

## PR update target

Commit back to the existing branch:

```text
stage-3.3.122-haproxy-tcp-worker-create
```

Existing PR:

```text
#196
```

## Deployment is not included

Do not deploy this patch automatically. Public deploy and transit Worker binary upgrade should be a later, explicit stage.
