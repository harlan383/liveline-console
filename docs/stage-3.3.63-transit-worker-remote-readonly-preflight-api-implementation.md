# Stage 3.3.63 Transit Worker Remote Readonly Preflight API Implementation

## Goal

Stage 3.3.63 implements the first Worker/API path for remote readonly preflight
of a locally planned transit route.

The new command type is:

`transit_readonly_preflight`

This stage creates a Worker command and displays its redacted result. It does
not create a real forwarding route.

## Implemented Scope

- Added a backend API for creating a transit readonly preflight Worker command.
- Added strict backend validation for transit resource, landing node, protected
  ports, Worker role, Worker online state, and readonly confirmation.
- Added Worker command support for `transit_readonly_preflight`.
- Added frontend API client types and calls.
- Added a frontend action in the transit readonly preflight area:
  `执行远程只读预检`.
- Added frontend display for Worker command id, command status, structured
  checks, and redacted summary.

## Backend API

New endpoint:

`POST /api/transit-routes/readonly-preflight-command`

The request accepts only validated planning fields:

- transit resource id
- landing node id
- planned listen port
- landing target port
- forwarding method
- purpose
- `readonly=true`

The API rejects requests when:

- the transit resource does not exist,
- the transit resource is not a `server`,
- the transit resource is disabled,
- no online `transit` Worker is bound to the resource,
- the online Worker does not support `transit_readonly_preflight`,
- the landing node does not exist or is not active,
- the landing target port does not match the active landing node port,
- the planned listen port is invalid,
- the planned listen port is protected,
- `readonly=true` is missing.

Protected planned listen ports remain:

- `22`
- `8443`
- `18443`
- `20575`

## Worker Allowlist

The Worker handler runs only fixed readonly checks:

- Worker identity and version.
- Planned listen port occupancy.
- `socat` service / process state summary.
- `gost` service / process state summary.
- TCP reachability from transit Worker host to landing target host and port.
- Local firewall readonly summary.

The Worker does not accept arbitrary shell payloads.

## Result Shape

The Worker returns a structured, redacted result:

- `passed`
- `status`
- `summary`
- `checks`
- `redacted_summary`
- `safety_boundary`

Each check contains:

- `id`
- `label`
- `status`
- `passed`
- `detail`

## Redaction Boundary

Results must not include:

- full client links,
- Worker tokens,
- Worker secrets,
- SSH private keys,
- database passwords,
- provider credentials,
- full Xray configuration,
- `nodes.share_link` values.

## No-Go Boundary

This stage does not:

- create a transit route,
- install `socat` or `gost`,
- start, stop, or restart services,
- bind a planned listen port,
- add a listening port,
- modify firewall, cloud firewall, or cloud security group rules,
- modify Xray,
- modify `nodes.share_link`,
- export a full client link,
- perform cutover.

## Validation

Required local validation:

- `git diff --check`
- `git diff --cached --check`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`
- `GOCACHE=/private/tmp/liveline-gocache go test ./...`
- `GOCACHE=/private/tmp/liveline-gocache go build ./...`
- `docker compose exec -T frontend npm run build`

Sensitive scan must not find real Worker tokens, full install commands, SSH
private keys, database passwords, full proxy links, or full `nodes.share_link`
values.

## Result

Stage 3.3.63 implements the remote readonly preflight Worker/API path while
keeping real transit creation No-Go.
