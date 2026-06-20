# Stage 3.3.95 Resource List Safe Delete

## Stage Goal

Stage 3.3.95 adds safe delete actions to the daily resource lists:

- transit servers
- landing servers
- direct nodes
- transit routes

The action deletes or soft-deletes LiveLine Console system records only. It does not perform remote cleanup, stop services, delete remote files, change firewall rules, or change client links.

## Definition Of Delete

In this stage, delete means:

```text
Delete / soft-delete the LiveLine Console system record so it no longer appears in daily lists. Real services on remote servers are not handled.
```

This stage never treats a UI delete button as permission to operate on a remote machine.

## Database Strategy

No database migration is required.

- `nodes`: uses existing `deleted_at`; status is set to `deleted`.
- `transit_resources`: uses existing `deleted_at`; status is set to `deleted`.
- `transit_routes`: uses existing `deleted_at`; status is set to `deleted`.
- `vps_servers`: uses existing `status`; status is set to `deleted`.

List APIs already filter deleted records through `deleted_at IS NULL` or `status != "deleted"`.

## Backend API Changes

The safe delete APIs are:

```text
DELETE /api/transit-resources/{id}?confirm=true
DELETE /api/vps/{id}?confirm=true
DELETE /api/nodes/{id}?confirm=true
DELETE /api/transit-routes/{id}?confirm=true
```

Each endpoint requires:

- authenticated admin session
- CSRF token
- `confirm=true`

Each endpoint returns a safe result shape:

```json
{
  "success": true,
  "data": {
    "id": "...",
    "deleted": true,
    "delete_mode": "soft_delete",
    "remote_action_performed": false,
    "message": "系统记录已删除；未执行远程清理。"
  }
}
```

## Per-resource Rules

### Transit Server

`transit_resources` deletion is blocked when the server still has undeleted transit routes.

Error code:

```text
TRANSIT_RESOURCE_HAS_ACTIVE_ROUTES
```

Message:

```text
该中转服务器下仍有中转链路，请先删除链路记录。
```

The endpoint does not stop `socat`, delete Worker records, remove systemd services, or connect to the transit host.

### Landing Server

`vps_servers` deletion is blocked when the landing server still has undeleted direct nodes.

Error code:

```text
VPS_HAS_ACTIVE_NODES
```

Message:

```text
该落地服务器下仍有直连节点，请先删除节点记录。
```

The endpoint does not stop Xray, delete Xray config, close ports, modify cloud security groups, or connect to the VPS.

### Direct Node

`nodes` deletion is allowed for active, disabled, failed, and other non-deleted node states.

The endpoint only marks the system record deleted. It does not stop remote Xray, delete remote Xray config, close ports, read a complete `nodes.share_link`, or write a complete share link to logs.

The UI warns that remote Xray may continue running and clients may still be able to use the node.

### Transit Route

`transit_routes` deletion is allowed for non-cutover records.

This stage uses a conservative cutover guard: if `transit_routes.share_link` is already present, deletion is blocked as a cutover-risk record.

Error code:

```text
TRANSIT_ROUTE_CUTOVER_BLOCKED
```

Message:

```text
该中转链路处于 cutover 状态，本阶段不允许删除。
```

The endpoint does not stop `socat`, delete systemd service files, close ports, modify firewall rules, modify Xray, mutate `nodes.share_link`, or write `transit_routes.share_link`.

## Frontend UI Changes

Delete buttons are added to:

- the transit server list row actions
- the landing server list row actions
- direct node child rows under landing servers
- the transit route table row actions

All delete modals require the operator to type:

```text
DELETE
```

The modal copy explains:

- only the local system record is deleted
- no SSH or remote cleanup is executed
- remote services may keep running
- dependent records must be deleted first when applicable

After a successful delete, the list is refreshed and the UI shows:

```text
系统记录已删除；未执行远程清理。
```

## Audit And Logging

Allowed audit content:

- object type
- object id
- action
- admin id
- timestamp
- result

Forbidden content:

- complete `nodes.share_link`
- complete candidate transit link
- SSH private key
- Worker token plaintext
- database password
- complete client configuration

## Safety Boundary

This stage does not:

- execute cutover
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- generate or record complete node links
- create Worker commands
- create VPS records
- create nodes
- create transit routes
- add listening ports
- restart, stop, or delete `socat`
- modify Xray
- stop Xray
- delete Xray config
- modify firewalls, cloud firewalls, or cloud security groups
- execute SSH or remote commands
- deploy the public console
- clean remote VPS files
- delete Workers
- stop Workers

## Acceptance Criteria

- Each supported list has a visible delete action.
- Every delete action opens a confirmation modal.
- The operator must type `DELETE`.
- Deleting transit servers is blocked when undeleted routes exist.
- Deleting landing servers is blocked when undeleted nodes exist.
- Deleting nodes only soft-deletes the system record.
- Deleting transit routes is blocked for cutover-risk records.
- No endpoint performs remote cleanup.
- No complete links or secrets are logged or documented.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- Python compile check for `backend/app`
- frontend build
- backend tests covering safe delete behavior
- sensitive information scan

## Result

Stage 3.3.95 adds safe delete controls for resource lists while preserving the project boundary: deletion only hides or soft-deletes local system records, and remote services are left untouched.
