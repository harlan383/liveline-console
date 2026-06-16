# Stage 3.3.37-a Formal Create Worker Targeting Hotfix

## Stage Goal

Stage 3.3.37-a fixes the formal landing-node create Worker targeting guard.
The formal create endpoint was still locked to an older Worker ID, while the
current Stage 3.3.37 Worker had already been upgraded and re-registered.

This stage is a code hotfix only. It does not trigger formal creation.

## Issue

The formal create endpoint:

```text
POST /api/vps/{server_id}/landing-node-create
```

returned `400 Bad Request`, and the database still showed zero
`landing_node_create` commands. This was safe because no real execution was
triggered, but it meant the backend could not target the current eligible
Worker.

The root cause was a hard-coded historical Worker ID in:

```text
backend/app/services/landing_node_create.py
```

## Hotfix

The backend no longer locks formal creation to one historical Worker ID.
Instead, it selects the latest eligible Worker that satisfies all of the
following:

- `server_id = 968519b3-9017-4b27-a9a0-d5731033f84f`
- `role = landing`
- `status = online`
- `interface_name = ens17`
- runtime heartbeat is still fresh
- `worker_version >= 0.1.4-stage-3.3.37`
- supports `landing_node_create`

If multiple Workers match, the backend chooses the newest one by heartbeat,
then registration time, then creation time.

## Guardrails Kept

This hotfix does not weaken the formal execution guard:

- only approved server `968519b3-9017-4b27-a9a0-d5731033f84f` is allowed
- only approved port `27939/TCP` is allowed
- all second-confirmation fields must be `true`
- a clean `landing_preflight` is still required
- `27939/TCP` must still be confirmed not listening by preflight and Worker
- Xray must still be absent
- existing Xray config must still be absent
- `node.share_link` may only be written after successful Worker completion
- real `vless://` links must not be written to docs, logs, terminal output, or chat

## Safety Boundary

This stage does not:

- execute SSH
- execute remote commands
- deploy the public console
- connect to the landing VPS
- trigger `landing_node_create`
- install Xray
- create nodes
- add listening ports
- modify firewall / cloud security group rules
- modify `node.share_link`
- generate a real node link
- perform cutover

## Modified Files

- `backend/app/services/landing_node_create.py`
  - removes the old hard-coded Worker ID target
  - selects the latest eligible online `ens17` landing Worker
  - keeps server, port, confirmation, preflight, Xray, and share-link guards
- `README.md`
  - records Stage 3.3.37-a scope and status
- `docs/stage-3.3.37-a-formal-create-worker-targeting-hotfix.md`
  - records this hotfix, guardrails, and safety boundary

## Validation Checklist

- `git diff --check`
- `python3 -m compileall backend/app`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `curl -s http://127.0.0.1:8000/api/health`
- `curl -I http://127.0.0.1:3000`
- Redis `temp_credential:*` count is `0`
- pending / running tasks count is `0`
- `landing_node_create` command count remains `0`
- sensitive scan finds no real token, password, `SESSION_SECRET`,
  Reality privateKey, complete `vless://` node link, or complete Worker token

## Conclusion

Stage 3.3.37-a keeps formal creation protected while allowing the backend to
target the current upgraded Worker. Real execution remains separate and must
only happen through explicit user action in the protected UI.
