# Stage 3.3.115 Worker Command Read Endpoint And Transit Poll Fix

## Goal

Stage 3.3.115 fixes the transit route create polling path after the readonly preflight command succeeds.

The UI already creates a `transit_readonly_preflight` command and then polls:

```text
GET /api/workers/commands/{command_id}
```

Production showed the command existed in `worker_commands` and had already succeeded, but the GET endpoint returned 404. This caused the transit create modal to stop with an unhelpful `undefined: undefined` error before it could call `worker-create-execute`.

## Fix

- Added an admin `GET /api/workers/commands/{command_id}` endpoint.
- The endpoint reads by `worker_commands.id`.
- Pending, claimed, running, succeeded, failed, expired, and completed commands return 200 when the record exists.
- Missing command ids return a structured `WORKER_COMMAND_NOT_FOUND` 404.
- The response reuses the existing Worker command serializer and does not include raw payload by default.
- The command serializer redacts sensitive result fields such as share links, candidate/client links, uuid, private keys, and short ids.
- Transit route create polling now retries short command-status 404 windows for up to 30 seconds.
- Transit route create error formatting no longer emits `undefined: undefined`.

## Safety Boundary

This stage only changes command status reading and frontend polling behavior.

It does not:

- execute SSH or remote commands
- deploy the public console
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
- modify Worker source or binary

## Validation

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `docker compose run --rm backend python -m unittest discover tests`
- `docker compose exec -T frontend npm run build`

No Worker build is required because this stage does not modify Worker source or binaries.
