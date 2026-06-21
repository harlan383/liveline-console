# Stage 3.3.117 Generalize Worker-Side Transit Route Create Approval

## Goal

Stage 3.3.117 fixes the Worker-side approval gate for protected
`transit_route_create` commands.

After Stage 3.3.116, the backend and frontend were able to create and poll the
protected create flow:

- `transit_readonly_preflight` succeeded.
- `worker-create-execute` succeeded.
- A `transit_route_create` Worker command was created.
- The transit Worker claimed the command.

The Worker then failed before creating the socat route because its local binary
still compared the command against historical fixed Worker, transit resource,
landing node, and interface approval constants.

## Root Cause

The backend payload already contains the current approved Worker and resource
identity, including:

- `transit_worker_id`
- `transit_resource_id`
- `interface_name`
- `planned_listen_port`
- `landing_target_host`
- `landing_target_port`
- `forwarding_method`
- `execution_mode`
- `approved_real_execution`

The bundled Worker binary still enforced an older fixed Worker id and returned:

```text
transit_route_create worker_id is not approved
```

## Fix

The Worker now validates protected real transit creation against the current
Worker identity instead of historical production ids:

- `payload.transit_worker_id` must exist and match the current Worker id.
- `payload.transit_resource_id` must match the current Worker config `server_id`.
- `payload.interface_name` must match the current Worker config `interface_name`.
- `route_name` may be dynamic but must match a safe label pattern.

The strict protected execution boundary remains unchanged:

- listen port remains fixed to `23843/TCP`
- landing target host remains fixed to the approved landing target
- landing target port remains fixed to `27939/TCP`
- forwarding method remains fixed to `socat`
- execution mode must be `real_create`
- `approved_real_execution` must be true
- no arbitrary shell is accepted
- no arbitrary systemd unit content is accepted
- service name and service path are derived by the Worker

The Worker config writer now stores `server_id` from the registration response
so future Worker registrations carry the local resource binding needed for this
approval check.

The next remote upgrade stage should confirm that the deployed transit Worker
config contains the expected `server_id`. This PR does not edit remote config
files.

## Worker Version And Binary

The Worker version was updated to:

```text
0.1.23-stage-3.3.117
```

The bundled Linux amd64 Worker binary was rebuilt at:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

The binary was verified to contain the new version string.

## Safety Boundary

This stage only changes Worker-side approval logic, tests, docs, and the bundled
Worker artifact.

It does not:

- execute SSH or remote commands
- deploy the public console
- upgrade a remote Worker
- create a real transit route
- create a Worker command
- install, restart, stop, or delete socat/gost/Xray
- read or print full `nodes.share_link`
- write `transit_routes.share_link`
- mutate `nodes.share_link`
- log full VLESS/V2Ray links
- modify firewall, cloud firewall, or security group rules
- cut over traffic
- physically delete database records

Remote transit Worker upgrade is intentionally left for:

```text
Stage 3.3.118-public-deploy-and-upgrade-transit-worker-0.1.23
```

## Validation

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./...`
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./...`
- rebuild `backend/worker-binaries/liveline-worker-linux-amd64`
- verify `0.1.23-stage-3.3.117` in the bundled Worker binary
- `docker compose build backend frontend`
- `docker compose run --rm backend python -m unittest discover tests`
- `docker compose exec -T frontend npm run build`
