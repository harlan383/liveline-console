# Stage 3.3.97 Protected Remote Cleanup Delete Flow

## Stage Goal

Stage 3.3.97 upgrades the Stage 3.3.95 delete buttons from local system-record deletion into protected remote cleanup flows.

The new rule is:

```text
Remote cleanup must succeed before the LiveLine Console system record is soft-deleted.
```

This stage develops the protected code path only. It does not run production cleanup, does not trigger Worker commands manually, and does not operate on the existing working direct node or transit route.

## Why Stage 3.3.95 Is Not Enough

Stage 3.3.95 intentionally deleted only local records. That was safe, but it could leave these real services running without a visible management record:

- Xray services on landing VPS hosts
- socat services on transit servers
- Worker services on landing or transit hosts
- listening ports that still accept traffic

Stage 3.3.97 adds a stronger but still protected flow: a delete action creates a fixed Worker cleanup command, the Worker performs allowlisted cleanup, and only a successful result soft-deletes the local system records.

## Protected APIs

New protected cleanup APIs:

```text
POST /api/nodes/{node_id}/remote-cleanup-delete
POST /api/vps/{vps_id}/remote-cleanup-delete
POST /api/transit-routes/{route_id}/remote-cleanup-delete
POST /api/transit-resources/{resource_id}/remote-cleanup-delete
```

Each request requires:

- authenticated admin session
- CSRF token
- request body confirmation:

```json
{
  "confirm": "CONFIRM_REMOTE_DELETE"
}
```

The API creates a Worker command and returns the queued command summary. It does not run SSH directly from the backend and does not soft-delete records until the Worker result reports success.

Only one remote cleanup command may be pending, claimed, or running for the same server record at a time. The lock is server-scoped across all cleanup command types, so a node cleanup blocks a landing-server cleanup on the same VPS, and a route cleanup blocks a transit-resource cleanup on the same transit server.

## Worker Command Types

Stage 3.3.97 adds these Worker command types:

```text
cleanup_landing_node
cleanup_landing_server
cleanup_transit_route
cleanup_transit_resource
```

Minimum Worker version for these commands:

```text
0.1.21-stage-3.3.97
```

The Worker rejects unsafe payload keys such as arbitrary shell commands, command arrays, raw systemd unit content, raw ExecStart values, or broad delete directives.

## Resource Cleanup Rules

### Direct Node

`cleanup_landing_node` cleans one LiveLine-managed Xray node service.

Allowed cleanup:

- stop and disable the approved LiveLine Xray service
- remove the approved LiveLine Xray systemd unit
- remove the approved LiveLine Xray config path when it is inside the LiveLine-managed path set
- run `systemctl daemon-reload`
- verify the node port is no longer listening
- soft-delete the `nodes` record only after cleanup succeeds

Not allowed:

- reading, returning, logging, or modifying complete `nodes.share_link`
- modifying firewall or cloud security group rules
- modifying non-LiveLine Xray services
- cutover

The payload uses service candidates so both the current one-node-one-service layout and the historical `liveline-xray.service` layout can be cleaned safely. Legacy cleanup still verifies that the service/config is LiveLine-managed and that the config port matches the node port before deletion.

### Landing Server

`cleanup_landing_server` cascades through all undeleted direct nodes on the landing VPS and then schedules landing Worker self-cleanup.

Allowed cleanup:

- cleanup all listed LiveLine Xray node plans
- schedule delayed Worker self-cleanup after the Worker result is submitted
- expire active Worker setup tokens for that landing server
- mark the landing Worker as `deleted`
- soft-delete the landing VPS record after success

Not allowed:

- stopping arbitrary services
- deleting arbitrary VPS files
- modifying firewall or cloud security group rules
- reading or exporting complete node links

Worker self-cleanup is delayed because the Worker must submit its final result first. The Worker schedules a fixed, generated cleanup script for its own LiveLine Worker service only. It does not accept arbitrary script content from the frontend or backend.

### Transit Route

`cleanup_transit_route` cleans one LiveLine-managed socat route service.

Allowed cleanup:

- stop and disable `liveline-socat-<port>.service`
- remove `/etc/systemd/system/liveline-socat-<port>.service`
- run `systemctl daemon-reload`
- verify the route port is no longer listening
- soft-delete the `transit_routes` record after success

Not allowed:

- stopping non-LiveLine services
- deleting arbitrary systemd units
- modifying firewalls or cloud security groups
- modifying Xray
- modifying `nodes.share_link`
- writing `transit_routes.share_link`
- cutover

The Worker validates the service name and service path from the approved route port. It does not accept raw systemd unit content or arbitrary ExecStart values.

### Transit Resource

`cleanup_transit_resource` cascades through all undeleted socat routes under the transit resource and then schedules transit Worker self-cleanup.

Allowed cleanup:

- cleanup all listed LiveLine socat route services
- schedule delayed Worker self-cleanup after result submission
- expire active Worker setup tokens for that transit resource
- mark the transit Worker as `deleted`
- soft-delete the transit resource record after success

Not allowed:

- removing non-LiveLine services
- deleting arbitrary remote files
- modifying firewall or cloud security group rules
- cutover

## Failure Behavior

Remote cleanup failure is intentionally conservative:

- if Worker cleanup fails, the command is marked failed
- the related system records remain visible and undeleted
- no local record is soft-deleted on failed cleanup
- the operator must review the failure before retrying or taking manual action

This prevents LiveLine Console from hiding records for resources that may still be running remotely.

## Database Strategy

No database migration is required.

The flow reuses existing soft-delete fields and status fields:

- `nodes.deleted_at` plus `nodes.status = deleted`
- `transit_routes.deleted_at` plus `transit_routes.status = deleted`
- `transit_resources.deleted_at` plus `transit_resources.status = deleted`
- `vps_servers.status = deleted`
- `workers.status = deleted` plus cleanup metadata
- active Worker setup tokens are marked expired

The flow does not hard-delete command history, audit logs, Worker command records, or historical resource records.

## Frontend Changes

Delete actions remain visible in the daily resource lists:

- landing server rows
- direct node rows under landing servers
- transit server rows
- transit route rows

The modals now require:

```text
CONFIRM_REMOTE_DELETE
```

The modal copy explains that the action creates a protected remote cleanup Worker command and only soft-deletes system records after remote cleanup succeeds.

## Audit And Logging

Allowed audit/log content:

- object type
- object id
- object name
- Worker command id
- cleanup command type
- cleanup status
- delete mode
- whether remote cleanup was performed

Forbidden audit/log content:

- complete `nodes.share_link`
- complete candidate links
- SSH private keys
- Worker tokens or Worker secrets
- database passwords
- complete client configuration links

## Safety Boundary

This stage does not:

- execute cutover
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- generate or record complete node links
- create VPS records
- create nodes
- create transit routes
- add listening ports
- modify Xray outside fixed cleanup of approved LiveLine services
- modify firewall, cloud firewall, or cloud security group rules
- deploy the public console
- run SSH manually
- trigger production cleanup manually
- clean official production resources during development

## Validation Plan

Required validation for this implementation:

- `git diff --check`
- `git diff --cached --check`
- Python compile check for `backend/app`
- Python compile check for `backend/tests`
- backend unit tests covering protected cleanup creation and result persistence
- Go Worker tests
- Go Worker build
- Linux amd64 Worker binary rebuild
- frontend build
- sensitive information scan

## Result

Stage 3.3.97 provides the protected remote cleanup delete flow in code and UI.

The core acceptance boundary is:

```text
Cleanup succeeds first; system records are soft-deleted only after success.
```

No production cleanup was executed in this stage.
