# Stage 3.3.119 Unified Delete Offline Local Remove

## Goal

Upgrade the existing delete buttons so the same action can handle both normal protected remote cleanup and offline local soft-removal.

This stage is for expired or unreachable resources where the Worker is offline and remote cleanup cannot be executed. It does not add a separate button.

## Delete Definition

Normal online delete still means:

- create a protected cleanup Worker command;
- let the online Worker clean the remote service;
- soft-delete LiveLine Console records only after Worker success.

Offline local remove means:

- do not create any Worker command;
- do not SSH or connect to any remote server;
- do not stop, restart, disable, or delete remote services;
- soft-delete LiveLine Console records only;
- keep historical commands, audit records, and existing link fields.

Offline local remove is only allowed when no cleanup-capable online Worker is available for the target resource.

## Resource Rules

### Transit Server

When no online transit Worker is available for the transit resource:

- mark `transit_resources.status = deleted`;
- set `transit_resources.deleted_at`;
- soft-delete related `transit_routes`;
- mark related Workers as deleted / cleanup expected offline;
- expire active Worker tokens;
- create no Worker command.

### Landing Server

When no online landing Worker is available for the VPS:

- mark `vps_servers.status = deleted`;
- soft-delete related `nodes`;
- soft-delete related transit routes that reference those nodes;
- mark related Workers as deleted / cleanup expected offline;
- expire active Worker tokens;
- create no Worker command.

### Direct Node

When no online landing Worker is available for the node's VPS:

- mark `nodes.status = deleted`;
- set `nodes.deleted_at`;
- soft-delete related transit routes;
- keep `nodes.share_link` unchanged;
- create no Worker command.

### Transit Route

When no online transit Worker is available for the transit resource:

- mark `transit_routes.status = deleted`;
- set `transit_routes.deleted_at`;
- keep `transit_routes.share_link` unchanged;
- reject cutover routes that already have a stored share link;
- create no Worker command.

## API Changes

The existing remote cleanup endpoints now accept two confirmation phrases:

- `CONFIRM_REMOTE_DELETE` for the existing protected remote cleanup flow;
- `CONFIRM_OFFLINE_LOCAL_REMOVE` for offline local soft-removal.

Endpoints:

- `POST /api/transit-resources/{id}/remote-cleanup-delete`
- `POST /api/vps/{id}/remote-cleanup-delete`
- `POST /api/nodes/{id}/remote-cleanup-delete`
- `POST /api/transit-routes/{id}/remote-cleanup-delete`

If a normal remote cleanup request cannot proceed because the Worker is unavailable, the backend returns `REMOTE_CLEANUP_UNAVAILABLE` with `offline_local_remove_available=true` and the required confirmation text.

If an online cleanup-capable Worker exists, offline local remove is rejected with `RESOURCE_HAS_ONLINE_WORKER_USE_NORMAL_DELETE`.

## UI Changes

The existing delete buttons remain the only entry point.

The confirmation modal now shows:

- whether remote cleanup will execute;
- whether a Worker command will be created;
- whether cutover will occur;
- whether share links will be modified.

When the Worker is offline, the same modal switches to `离线本地移除确认` and requires:

```text
CONFIRM_OFFLINE_LOCAL_REMOVE
```

Offline local remove success message:

```text
已本地移除记录。由于 Worker 离线，未执行远程清理。
```

## Safety Boundary

This stage does not:

- execute SSH;
- connect to remote VPS hosts;
- create Worker commands for offline local remove;
- stop, restart, disable, or delete remote Xray, socat, gost, or Worker services;
- mutate cloud security groups, cloud firewall, or server firewall;
- read, print, or modify full `nodes.share_link`;
- write `transit_routes.share_link`;
- perform cutover;
- physically delete database records;
- delete audit logs;
- delete historical `worker_commands`.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- backend unit tests
- frontend build
- sensitive information scan

Worker code is unchanged, so Go build/test is not required for this stage.
