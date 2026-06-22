# Stage 3.3.126-a - Worker 0.1.24 build artifact

## Stage goal

Stage 3.3.126-a rebuilds and records the bundled Linux amd64 Worker artifact for HAProxy TCP readiness.

Target Worker version:

```text
0.1.24-stage-3.3.122
```

Target artifact:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

This stage only builds and commits the local repository artifact. It does not deploy the public controller and does not replace any remote Worker.

## Built Worker version

Source version check:

```text
worker/cmd/liveline-worker/main.go: const workerVersion = "0.1.24-stage-3.3.122"
```

Artifact embedded version check:

```text
0.1.24-stage-3.3.122
```

The artifact is a Linux amd64 binary, so it was not executed locally on macOS. The version was verified from the embedded string, and the file type was verified with `file`.

## Modified artifact path

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

File metadata after rebuild:

```text
ELF 64-bit LSB executable, x86-64, statically linked
mode: executable
size: about 9.7M
```

## Build commands

Executed from `worker`:

```text
gofmt -w cmd/liveline-worker/main.go cmd/liveline-worker/transit_haproxy.go
GOCACHE=/private/tmp/liveline-go-cache go test ./cmd/liveline-worker
GOCACHE=/private/tmp/liveline-go-cache go build ./cmd/liveline-worker
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 GOCACHE=/private/tmp/liveline-go-cache go build -o ../backend/worker-binaries/liveline-worker-linux-amd64 ./cmd/liveline-worker
```

After returning to the repository root:

```text
chmod +x backend/worker-binaries/liveline-worker-linux-amd64
```

The local temporary `worker/liveline-worker` output from `go build ./cmd/liveline-worker` was removed and is not part of this stage.

## Test commands

```text
GOCACHE=/private/tmp/liveline-go-cache go test ./cmd/liveline-worker
GOCACHE=/private/tmp/liveline-go-cache go build ./cmd/liveline-worker
```

Both commands completed successfully.

## SHA256 checksum

```text
cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce  backend/worker-binaries/liveline-worker-linux-amd64
```

## Validation result

Validation performed:

```text
Worker source version confirmed as 0.1.24-stage-3.3.122.
HAProxy helper source exists at worker/cmd/liveline-worker/transit_haproxy.go.
executeTransitRouteCreateHaproxy exists.
haproxy_tcp source references exist.
go test ./cmd/liveline-worker passed.
go build ./cmd/liveline-worker passed.
Linux amd64 artifact build passed.
Artifact file exists and is executable.
Artifact file type is Linux amd64 ELF.
Artifact embedded version string includes 0.1.24-stage-3.3.122.
SHA256 checksum recorded.
```

## Safety boundary

Stage 3.3.126-a safety boundary:

```text
No public deploy.
No Docker Compose up/down/restart.
No SSH login.
No remote command.
No remote Worker replacement.
No upload to the transit VPS.
No liveline-worker service stop/restart.
No Worker command created.
No HAProxy route created.
No HAProxy install.
No existing socat service stop/restart/delete.
No Xray mutation.
No firewall/security group/cloud firewall mutation.
No cutover.
No full nodes.share_link exposure.
No transit_routes.share_link write.
No full VLESS/V2Ray link output.
```

## Next recommended stage

Recommended next stage:

```text
Stage 3.3.126-b-worker-binary-0.1.24-deploy-approval
```

That stage should perform deployment approval and pre-checks before any upload, service restart, Worker replacement, remote command, or production validation.
