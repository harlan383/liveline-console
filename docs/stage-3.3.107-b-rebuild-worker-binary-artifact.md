# Stage 3.3.107-b Rebuild Worker Binary Artifact

## Stage Goal

Stage 3.3.107-b rebuilds the bundled Linux amd64 LiveLine Worker binary after Stage 3.3.107 was merged.

Stage 3.3.107 updated the Worker source version to:

```text
0.1.22-stage-3.3.107
```

However, the bundled artifact at `backend/worker-binaries/liveline-worker-linux-amd64` was still an older build. This stage updates that artifact so a later, separately approved remote Worker upgrade can install the correct diagnostic-capable binary.

## Artifact Rebuilt

Rebuilt file:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

Build target:

```text
GOOS=linux
GOARCH=amd64
CGO_ENABLED=0
```

The rebuilt binary was marked executable.

## Version Verification

The rebuilt artifact was checked for the expected embedded version string:

```text
0.1.22-stage-3.3.107
```

This confirms the bundled Worker binary matches the Stage 3.3.107 source version.

## Not Performed

This stage did not:

- execute SSH
- deploy the public console
- upgrade any remote Worker
- create a Worker command
- create a production node
- install Xray
- read or modify `nodes.share_link`
- generate or record a full client link
- modify cloud security groups, cloud firewall, or server firewall
- cut over any route
- physically delete database records

## Safety Boundary

This stage only updates the bundled Worker binary artifact and documentation. Remote Worker replacement must remain a separate, explicitly approved production stage.

## Validation

Required validation for this stage:

```bash
git diff --check
git diff --cached --check
cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./...
cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./...
grep -a '0.1.22-stage-3.3.107' backend/worker-binaries/liveline-worker-linux-amd64 | head
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```
