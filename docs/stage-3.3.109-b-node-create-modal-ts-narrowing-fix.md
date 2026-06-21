# Stage 3.3.109-b Node Create Modal TS Narrowing Fix

## Stage Goal

Stage 3.3.109-b fixes a frontend production build failure introduced after the direct node create modal was moved into a dedicated `nodePlan` modal branch.

The failing TypeScript check was:

```text
This comparison appears to be unintentional because the types '"delete" | "add" | "edit" | "deleteNode" | "workerCommand"' and '"nodePlan"' have no overlap.
```

## Root Cause

Stage 3.3.109 added an early dedicated return for:

```text
mode === "nodePlan"
```

The later shared modal branch still contained a stale conditional render for the same mode. TypeScript correctly narrowed `mode` after the early return, so the later comparison was unreachable and failed production build.

## Fix

Removed the stale shared-branch render:

```text
mode === "nodePlan" ? renderNodePlanForm() : null
```

The direct node create modal remains handled by the dedicated `nodePlan` branch.

## Not Changed

This stage did not change:

- backend node creation logic
- Worker command logic
- share-link export logic
- QR-code behavior
- Xray behavior
- firewall or security-group behavior

## Safety Boundary

This stage only fixes frontend TypeScript narrowing.

It did not:

- execute SSH
- deploy the public console
- create a Worker command
- create a production node
- install, restart, or stop Xray
- read or modify `nodes.share_link`
- write or log a full VLESS / V2Ray link
- modify cloud security groups, cloud firewall, or server firewall
- cut over any route

## Validation

Required validation:

```bash
git diff --check
git diff --cached --check
docker compose exec -T frontend npm run build
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```
