# Stage 3.3.179 Reality dest / SNI Template

## Goal

Stage 3.3.179 fixes the Reality template and client-link compatibility used by newly created landing Reality nodes.

The new default Reality template is:

- SNI: `dash.cloudflare.com`
- Dest: `dash.cloudflare.com:443`
- Fingerprint: `chrome`
- Flow: `xtls-rprx-vision`
- Security: `reality`
- Transport: `tcp`

Existing nodes are not modified.

## Changes

- Landing-node plan/create requests now validate Reality SNI, dest, and fingerprint.
- `reality_sni` / `reality_dest` aliases are accepted and mapped to the existing `server_name` / `dest` fields.
- The backend sends the actual SNI, dest, fingerprint, flow, security, and transport to the Worker command payload.
- The Worker version is bumped to `0.1.32-stage-3.3.179-reality-dest-sni-template`.
- The Worker no longer falls back to the old `www.microsoft.com` Reality template.
- Direct VLESS Reality links include `headerType=none`.
- Transit temporary export still only replaces host and port, preserves Reality parameters, and adds `headerType=none` for client compatibility.

## Binary

Bundled Linux amd64 Worker binary:

- Path: `backend/worker-binaries/liveline-worker-linux-amd64`
- Version marker: `0.1.32-stage-3.3.179-reality-dest-sni-template`
- sha256: `5188c10c2d11dfdb90c3882ba4fc29d3c7031069a3c29f750ce883dd7bd40044`

## Safety Boundary

This stage only changes code and the bundled Worker artifact.

It does not:

- create a real landing node
- add a real listening port
- create a real transit route
- delete a node or route
- perform remote cleanup or local remove
- SSH or execute remote commands
- install or uninstall HAProxy
- cut over traffic
- write `transit_routes.share_link`
- mutate existing `nodes.share_link`
- output a full share link in docs
- modify firewall, cloud security group, or cloud firewall rules

## Validation

Planned validation for this PR:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Backend focused tests in Docker when local Python dependencies are unavailable
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./...`
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./...`
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o ../backend/worker-binaries/liveline-worker-linux-amd64 ./cmd/liveline-worker`
- `grep -a "0.1.32-stage-3.3.179-reality-dest-sni-template" backend/worker-binaries/liveline-worker-linux-amd64 | head`
- `shasum -a 256 backend/worker-binaries/liveline-worker-linux-amd64`
- frontend production build
