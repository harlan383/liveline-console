# Stage 3.3.79 Multi-resource capability check

## Stage goal

This stage audits whether the current LiveLine Console codebase can support more than one transit server, landing server, landing node, and transit route.

This is a boundary check only. It does not change runtime behavior, database state, Worker commands, Xray configuration, socat services, firewall rules, `nodes.share_link`, or cutover state.

## Product principle

LiveLine Console is a lightweight, self-use network setup and troubleshooting assistant. It is not intended to become a complex commercial node platform.

The current priority is still the "build the network" workflow:

- create a direct landing node through controlled automation;
- create a transit route through controlled automation;
- view node and transit route status;
- temporarily export / copy a client test configuration;
- confirm the client can browse through the route;
- keep the original direct node;
- avoid accidental `nodes.share_link` mutation;
- avoid automatic cutover;
- avoid complex recommendation, automatic switching, or large state-machine behavior.

Troubleshooting remains a later independent module. Future troubleshooting stages may cover Worker online state, port listening checks, Xray status, socat status, route connectivity, client failure hints, log summaries, and one-click readonly diagnostics.

## What was inspected

The audit reviewed the current local code only:

- `backend/app/models/vps_server.py`
- `backend/app/models/node.py`
- `backend/app/models/transit_resource.py`
- `backend/app/models/transit_route.py`
- `backend/app/models/worker.py`
- `backend/app/models/worker_command.py`
- `backend/alembic/versions/0001_initial_schema.py`
- `backend/alembic/versions/0004_create_transit_resources.py`
- `backend/alembic/versions/0006_create_transit_routes.py`
- `backend/alembic/versions/0008_worker_foundation.py`
- `backend/app/api/routes/vps.py`
- `backend/app/api/routes/nodes.py`
- `backend/app/api/routes/transit_resources.py`
- `backend/app/api/routes/transit_routes.py`
- `backend/app/services/landing_node_create.py`
- `backend/app/services/transit_route_create.py`
- `backend/app/services/worker_targeting.py`
- `worker/cmd/liveline-worker/main.go`
- `frontend/components/TransitRoutesPanel.tsx`
- `frontend/lib/api.ts`

No production hosts, databases, Workers, or remote services were queried.

## Capability matrix

| Capability | Data structure | Current UI/API | Current automation | Production verification | Conclusion |
| --- | --- | --- | --- | --- | --- |
| Multiple transit servers | Supported by `transit_resources` rows and Worker `server_id` binding. Duplicate `entry_host` is rejected for non-deleted server resources. | Supported for adding/listing Worker-based transit resources. | Worker command targeting can select online Workers by `server_id` and role, but real route creation is still approval-locked to one known transit resource / Worker. | Verified only for the Hong Kong transit server. | Partially supported: metadata/UI supports multiple; real automation is not generalized. |
| Multiple landing servers | Supported by multiple `vps_servers` rows. Duplicate non-deleted IP is rejected. | Supported for adding/listing Worker-based landing servers. | Worker targeting can bind by landing `server_id`, but formal landing node creation is locked to the approved landing VPS and `27939/TCP`. | Verified only for the accepted landing VPS. | Partially supported: server inventory supports multiple; formal node creation is not generalized. |
| Multiple nodes on one landing server | The `Node` model relates many nodes to one VPS, but the initial migration creates a partial unique index `uq_nodes_one_not_deleted_per_vps` on `vps_id` where `status != 'deleted'`. | The landing server UI can display child node rows, but current accepted flow treats one active node per landing server as the safe model. | Formal landing creation is locked to approved port `27939` and does not implement multi-inbound Xray append / ownership management. | Verified one active node on one landing VPS. | Not currently supported for multiple active nodes on one landing server without schema and automation changes. |
| Multiple transit routes | `transit_routes` supports multiple rows and has non-unique indexes for resource / listen port lookup. | Route list/table can show multiple rows. | Current real-create path is locked to `hk-socat-live-23843`, approved route id, approved transit resource, approved Worker, approved landing node, and port `23843`. | Verified one active socat route. | Data/display can hold multiple; controlled creation is single-route locked. |
| One transit server reused by multiple routes | The schema permits multiple `transit_routes` with the same `transit_resource_id` if listen ports differ. | Planning UI can select Worker-online resources for local plans. | Worker real-create code uses the fixed service `liveline-socat-23843.service` and fixed listen port `23843`; generalized service naming and port conflict management are not implemented. | Verified one route on one transit server. | Structurally possible, but not automation-verified or generalized. |

## Direct answers

### Can the system add multiple transit servers?

Yes for local records and Worker bootstrap flows. The system can create multiple `transit_resources` records as long as each non-deleted server resource has a unique `entry_host`.

However, real transit route creation is not yet multi-resource generalized. The current safe create/export path is explicitly locked to the approved Hong Kong transit resource and Worker.

### Can the system add multiple landing servers?

Yes for local records and Worker bootstrap flows. The system can create multiple `vps_servers` records as long as each non-deleted landing server has a unique IP.

However, formal landing node creation is currently locked to the approved landing VPS, interface, and port. Multi-landing inventory is supported; multi-landing automated node creation still needs staged generalization.

### Can one landing server generate multiple nodes?

No, not safely in the current accepted model.

Although the SQLAlchemy relationship allows a VPS to have child node rows, the initial migration defines `uq_nodes_one_not_deleted_per_vps`, which allows only one non-deleted node per VPS. Current formal creation also assumes a single approved node on `27939/TCP` and does not implement multi-inbound Xray append, per-inbound ownership markers, or per-node rollback.

Supporting multiple active nodes on one landing server would require an explicit later stage.

### Can the system add multiple transit routes?

The database and list UI can store and show multiple `transit_routes` rows. There is no unique database constraint that globally limits the table to one route.

The current controlled Worker real-create path is nevertheless locked to one approved route: `hk-socat-live-23843` on `23843/TCP`. Additional real routes require parameterized approvals, service naming, conflict checks, and Worker execution generalization.

### Can one transit server be reused by multiple transit routes?

Structurally yes. Multiple route rows can reference the same `transit_resource_id`.

Operationally this is not generalized yet. A safe implementation must allocate a distinct listen port per route, generate a distinct LiveLine-managed systemd service name/path, confirm the port is free, prevent service overwrite, and isolate rollback to the one route being created.

## Current hard locks and single-route assumptions

The current safety model intentionally hard-locks the production route path. These locks are helpful for the accepted single-route setup, but they prevent generic multi-resource automation:

- `backend/app/schemas/transit_route.py` stores approved constants for one transit resource, Worker, landing node, listen port, target host/port, service name, service path, route id, and candidate name.
- `backend/app/api/routes/transit_routes.py` checks those constants in `worker-create-plan`, `worker-create-execute`, candidate summary, and candidate export.
- `backend/app/services/transit_route_create.py` persists only the approved real-create result and writes one approved route shape.
- `worker/cmd/liveline-worker/main.go` validates and executes only the approved `socat` route template and fixed service path.
- `frontend/components/TransitRoutesPanel.tsx` contains the approved candidate route id and default planned listen port for the current single-route workflow.
- `backend/app/services/landing_node_create.py` locks formal landing creation to the approved landing VPS, interface, and `27939/TCP`.
- `backend/alembic/versions/0001_initial_schema.py` prevents multiple non-deleted nodes on the same VPS through `uq_nodes_one_not_deleted_per_vps`.

## Data-structure support versus automation verification

### Data-structure-supported today

- Multiple transit server records.
- Multiple landing server records.
- Multiple Worker records bound to different `server_id` values.
- Multiple transit route records in the table.
- Multiple transit routes referencing one transit resource, as long as application logic avoids listen-port conflicts.

### Not automation-verified today

- Real creation of a second transit route on the same transit server.
- Real creation of a route on a second transit server.
- Real creation of a route to a second landing node.
- Real creation of a second active node on one landing VPS.
- General route candidate export for arbitrary routes.
- General route promotion / cutover state across multiple candidate routes.

### Currently blocked by design

- Multiple active nodes on one landing VPS, because of `uq_nodes_one_not_deleted_per_vps`.
- Arbitrary transit real-create parameters, because the current route execution path is approval-locked to one known route.
- Generic candidate export, because the current candidate export endpoint accepts only the approved candidate route.

## Minimal changes for future multi-resource support

### Multi-transit-server route creation

Minimal future changes:

1. Replace global approved constants with a per-route approval record or approval payload stored in the database.
2. Select the Worker by the chosen transit resource and role, while keeping online/version/interface checks.
3. Require a fresh readonly preflight tied to the chosen resource, target node, listen port, and method.
4. Keep the current no-shell, no-arbitrary-systemd, no-firewall, no-Xray, no-share-link mutation boundary.

### Multiple routes on one transit server

Minimal future changes:

1. Add application-level and ideally database-level protection for `(transit_resource_id, listen_port)` where `deleted_at IS NULL` and status is active/creating.
2. Generate service names and paths deterministically per route, for example `liveline-socat-{listen_port}.service` or `liveline-socat-{route_id}.service`.
3. Refuse to overwrite an existing service file unless it is provably LiveLine-owned by the same route.
4. Verify the listen port is free before creation and listening after start.
5. Roll back only the service and files created by the current route.

### Multiple landing servers

Minimal future changes:

1. Generalize landing-node create approval from a fixed server id/IP/interface/port to a per-server approval packet.
2. Keep Worker role/version/heartbeat targeting.
3. Keep preflight gates for Xray absence or LiveLine ownership.
4. Continue writing `nodes.share_link` only after successful Xray start and port verification.

### Multiple nodes on one landing server

This is the largest change and should be a separate explicit stage.

Minimal future changes:

1. Review and likely replace `uq_nodes_one_not_deleted_per_vps`.
2. Define LiveLine-owned multi-inbound Xray config semantics.
3. Allocate and validate one unique port per node.
4. Append / remove only LiveLine-managed inbound blocks, without overwriting unknown Xray config.
5. Store per-node ownership metadata sufficient for rollback.
6. Ensure `nodes.share_link` writes only the node being created and never rewrites other node links.

## Conflict points to guard before generalization

### Port conflicts

Guard at both backend and Worker layers:

- transit listen port already planned or active for the same transit resource;
- transit listen port already bound on the remote host;
- landing Xray node port already used by another active node;
- protected ports such as SSH, current fallback ports, console ports, database ports, and historical problem ports.

### Service conflicts

Guard before writing or enabling services:

- existing `liveline-socat-*.service` with a different route owner;
- existing service path that is not LiveLine-owned;
- systemd unit name collision;
- rollback accidentally deleting a service created by another route.

### Xray inbound overwrite

Guard before multi-node support:

- do not overwrite unknown existing Xray config;
- do not delete non-LiveLine inbounds;
- do not regenerate Reality materials for existing nodes unless a rotation stage is approved;
- do not log private keys or full configs.

### `share_link` mutation

Keep the current principle:

- default APIs return masked link metadata only;
- explicit export requires confirmation;
- transit candidate export remains transient unless a later stage approves database mutation;
- never mutate `nodes.share_link` when adding a transit route;
- never write full links to README, docs, PRs, audit logs, Worker logs, or terminal output.

## Recommended next steps

For this self-use system, avoid adding a broad multi-route platform immediately. The current network-building workflow is already feature-complete enough for a single landing node plus one accepted Hong Kong socat route.

Recommended staged path:

1. `Stage 3.3.79b-multi-transit-route-generalization-plan`: design only, no code.
2. `Stage 3.3.79c-transit-route-port-and-service-uniqueness-guards`: add conflict guards before allowing a second route.
3. `Stage 3.3.79d-second-transit-route-dry-run-only`: validate a second route as dry-run only.
4. `Stage 3.3.80-public-console-https-reverse-proxy`: HTTPS for safer admin access and Clipboard API behavior.
5. Later, if needed, a separate multi-node landing-server plan after deciding whether one VPS should really host more than one active Xray node.

## Safety boundary for this stage

This stage did not:

- execute SSH or remote commands;
- deploy the public console;
- create Worker commands;
- create transit routes;
- add listening ports;
- start, stop, restart, or delete `socat` / `gost`;
- modify Xray;
- modify firewall, cloud firewall, or security group rules;
- read, export, or mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- generate full client links;
- perform cutover;
- add database migrations;
- change backend, frontend, or Worker behavior.

## Validation checklist

- `git diff --check`
- `git diff --cached --check`
- Sensitive information scan: no Worker secret, token, SSH private key, database password, complete proxy link, complete candidate link, or real `nodes.share_link` value in README/docs.

No backend, frontend, or Worker build is required because this stage changes only README and documentation.
