# Stage 3.3.136 New Transit HAProxy Readiness And Route Create Approval

## Goal

Stage 3.3.136 adds a read-only HAProxy TCP route creation readiness and approval package after manual transit Worker heartbeat acceptance.

The target real transit resource context is:

- Resource name: `mkiepl广港`
- Resource id: `80ec346d-3ac1-402e-ab09-33cb404ca81c`
- Entry host: `109.244.79.147`
- Worker role: `transit`
- Expected Worker version: `0.1.24-stage-3.3.122`
- Expected interface: `eth0`

This stage does not create a route. It only checks whether the selected resource, Worker, landing node, planned listen port, and explicit safety confirmations are ready for a later HAProxy TCP route creation stage.

## Backend Changes

The backend adds:

- `TransitHaproxyReadinessApprovalRequest`
- `POST /api/transit-routes/haproxy-readiness-approval`

The endpoint is read-only. It does not call `db.add`, does not commit a database transaction, does not create a `WorkerCommand`, does not create a `TransitRoute`, does not install HAProxy, and does not read or return a full client link.

The readiness response includes:

- `ready`
- `blocked`
- `status`
- `summary`
- `next_action`
- `transit_resource`
- `transit_worker`
- `landing_node`
- `planned_route`
- `checks`
- `safety_boundary`

## Readiness Checks

The approval package records these checks:

- `transit_resource_exists`
- `transit_resource_not_deleted`
- `transit_worker_found`
- `transit_worker_online`
- `transit_worker_role_is_transit`
- `transit_worker_version_supported`
- `transit_worker_interface_detected`
- `landing_node_exists`
- `landing_node_has_target_host`
- `landing_target_port_valid`
- `planned_listen_port_valid`
- `forwarding_method_is_haproxy_tcp`
- `security_group_confirmation_present`
- `cloud_firewall_confirmation_present`
- `server_firewall_confirmation_present`
- `no_cutover_confirmed`
- `no_share_link_mutation_confirmed`
- `no_full_client_link_confirmed`
- `worker_command_not_created`
- `haproxy_not_created`
- `firewall_not_modified`

The package is ready only when all readiness and safety checks pass.

## Frontend Changes

The transit routes page advanced section now includes a HAProxy TCP route creation approval package panel.

The panel:

- Displays the selected transit resource, Worker version/status/interface, landing node, planned listen port, and forwarding method.
- Requires explicit manual confirmations for cloud security group, cloud firewall, server firewall, no cutover, no share-link mutation, and no full client link export.
- Calls the read-only readiness endpoint.
- Shows ready/blocked check results.
- Shows a disabled next-stage action marker instead of any real create button.

The panel does not create a Worker command and does not trigger remote execution.

## Safety Boundary

Stage 3.3.136 does not:

- Deploy Worker
- Execute SSH or any remote command
- Create a Worker command
- Create a HAProxy route
- Install, start, stop, restart, or delete HAProxy
- Create a listener
- Modify firewall, cloud firewall, or cloud security group
- Modify or stop existing socat services
- Modify Xray
- Cut over traffic
- Read, print, or record full `nodes.share_link`
- Write `transit_routes.share_link`
- Generate, show, log, or document a full VLESS/V2Ray client link

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Backend unit tests for the HAProxy readiness endpoint
- Frontend production build
- Sensitive information scan

## Next Stage

A later stage may request explicit user approval for real HAProxy TCP route creation. That future stage must separately authorize any Worker command and remote HAProxy service creation.
