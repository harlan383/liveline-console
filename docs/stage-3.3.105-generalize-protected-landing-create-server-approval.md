# Stage 3.3.105 Generalize Protected Landing Create Server Approval

## Stage Goal

Stage 3.3.105 replaces the old fixed historical landing-server guard in the protected `landing_node_create` path with a protected active-server approval model.

The purpose is to allow a newly added landing server to enter the existing protected direct Reality node creation flow when it has a bound online landing Worker and a recent clean `landing_preflight`.

This stage only changes code and documentation. It does not execute a real node creation command.

## Background

The previous protected create implementation still required the historical landing server id and IP from Stage 3.3.37. A newly added landing server could pass preflight and plan generation, but the formal create endpoint rejected it with `FORMAL_SERVER_NOT_APPROVED`.

That was too narrow for the current self-use network-build workflow. The create path should remain protected, but the approval target should be the current active landing server and its bound Worker, not one historical server record.

## Guard Changes

The protected create path now validates the current landing server dynamically:

- The VPS record must exist and must not be deleted.
- The approved port remains fixed at `27939/TCP`.
- A recent successful `landing_preflight` is still required.
- The preflight result must have no warnings or errors.
- The preflight result must not report `interface_mismatch`.
- The preflight result must not show existing Xray or existing Xray config.
- A landing Worker must be bound to the same `vps.id`.
- The Worker must be online and have a fresh heartbeat.
- The Worker role must be `landing`.
- The Worker version must support `landing_node_create`.
- The Worker `interface_name` must match the latest preflight default public interface.

The backend no longer checks the historical Stage 3.3.37 server id or IP as a hard allowlist.

## What Remains Fixed and Protected

This stage does not add dynamic-port formal creation.

The following protections remain unchanged:

- Formal create still uses `27939/TCP`.
- Non-approved ports are rejected.
- Frontend simplified creation still requires the operator confirmation for `27939/TCP` firewall readiness.
- Only successful Worker execution can write `nodes.share_link`.
- Failed creation must not write `nodes.share_link`.
- Complete client links must not be written to logs, docs, PRs, or audit text.
- Cloud security groups, cloud firewalls, and server firewalls are not modified.

## Result Persistence

The result ingest path now persists a successful `landing_node_create` result to the command-bound server id instead of the historical fixed server id.

On success:

- A node row is created for `command.server_id`.
- The fixed port remains `27939/TCP`.
- The full share link is stored only in `nodes.share_link`.
- The command result keeps only masked/share-link presence metadata.
- The related VPS record is marked active with the managed Xray config path.

On failure:

- No node row is created.
- `nodes.share_link` is not written.
- Complete links are not exposed.

## UI Message

The simplified node create flow now reports a clearer Chinese error when formal approval fails because of server approval, missing preflight interface, or Worker/preflight interface mismatch.

## Safety Boundary

This stage did not:

- Execute SSH.
- Deploy the public console.
- Create a production node.
- Create a Worker command.
- Install Xray.
- Generate a real complete node link into logs, docs, PRs, or chat.
- Read complete `nodes.share_link`.
- Modify existing deleted resources.
- Restore old nodes.
- Cut over any route.
- Modify cloud security groups, cloud firewalls, or server firewalls.
- Physically delete database records.

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Backend unit tests
- Backend Docker build
- Frontend build because the frontend error message changed
- Sensitive information scan
