# Stage 3.3.122-d — main.go Codex Patch Instructions

## Status

This Codex patch was completed locally and pushed to PR #196 as commit:

```text
f0e28f0
```

The patch is retained as an audit record of the local execution steps.

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

## Files edited

```text
worker/cmd/liveline-worker/main.go
```

## Patch 1 — Worker version

Changed from:

```go
const workerVersion = "0.1.23-stage-3.3.117"
```

To:

```go
const workerVersion = "0.1.24-stage-3.3.122"
```

## Patch 2 — route create real execution branch

At the top of `executeTransitRouteCreateReal(...)`, the HAProxy branch was added:

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

The existing socat implementation below remained unchanged.

## Expected behavior after patch

```text
forwarding_method=socat
  -> existing fixed socat path remains unchanged

forwarding_method=haproxy_tcp or haproxy or haproxy-tcp
  -> new executeTransitRouteCreateHaproxy() path
```

## Local validation reported

From the user-local repository:

```text
gofmt -w worker/cmd/liveline-worker/main.go worker/cmd/liveline-worker/transit_haproxy.go: passed
cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./cmd/liveline-worker: passed
cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./cmd/liveline-worker: passed
git diff --check: passed
git diff --cached --check: passed
git status: clean
```

Root-level Go commands failed only because the repository root has no Go module; the Worker module validation passed under `worker/`.

## Deployment is not included

This patch does not deploy Worker and does not create a real HAProxy route. Public deploy and transit Worker binary upgrade should be a later, explicit stage.
