# Stage 3.3.48 — Transit UI Flow Reconciliation

## 1. Purpose

Stage 3.3.48 reconciles the current transit-server UI flow with the current
transit-route creation flow.

This stage is documentation-only. It corrects the operating model after reviewing
the latest UI behavior and development records. It does not install Worker on a
VPS, run Worker commands, run SSH, create transit routes, generate listener ports,
modify firewall rules, or perform cutover.

## 2. Corrected UI responsibility split

The current console has two separate layers:

| UI area | Current responsibility | Not responsible for |
| --- | --- | --- |
| Transit Servers / 中转服务器列表 | Add and manage transit server resources; generate a bound `role=transit` Worker install command; display pending / online / offline Worker state; allow read-only Worker checks when online | Selecting landing nodes, creating transit links, generating usable client endpoints, opening ports, installing `socat` / `gost`, or cutover |
| Transit Links / 中转链路列表 | Compose a future route by selecting transit server + landing node + planned listen port + forwarding method; plan read-only preflight; later enter a separately approved real execution flow | Adding a new transit server resource or installing Worker by itself |

The earlier assumption that transit servers could be treated as a plain resource
record without considering Worker binding is outdated for the current UI.

## 3. Current transit-server add flow

The current add-transit-server flow is Worker based:

1. Operator fills transit server name, public IPv4, and token expiration.
2. Frontend calls `POST /api/transit-resources/worker-bootstrap`.
3. Backend creates a `transit_resources` record with status `pending_worker`.
4. Backend creates a one-time Worker token with `role=transit`.
5. The token is bound to the new `transit_resources.id` through
   `worker_tokens.server_id`.
6. Frontend displays the install command.
7. If the operator later runs the install command on the VPS, Worker registers and
   stores `workers.server_id = transit_resources.id`.
8. Heartbeat updates the Worker status and synchronizes the transit resource
   display status.

For the current selected resource:

| Field | Value |
| --- | --- |
| Transit server name | `香港中转服务器` |
| Transit server IP | `163.223.216.108` |
| Role | `transit` |
| Connection mode | Worker install command |
| Current state | `pending_worker` resource / active one-time token |
| Current production action | No remote execution performed by this stage |

The generated Worker install command is sensitive because it contains a one-time
token. It must not be copied into documentation, PR comments, logs, screenshots, or
chat messages without redaction.

## 4. Worker install command boundary

Executing the generated install command on a VPS is a real environment change.
When run manually by the operator, the install script is expected to:

- install `liveline-worker`,
- register the Worker with the console,
- write `/etc/liveline-worker/config.yaml`,
- create `liveline-worker.service`,
- enable and restart the Worker systemd service,
- begin heartbeat reporting.

Worker v1 / current Worker command channel remains limited. It does not create
transit routes by itself, does not install `socat` or `gost`, does not add
listening ports, does not modify firewall rules, does not modify cloud security
groups, does not modify Xray, does not modify `nodes.share_link`, and does not
perform cutover.

## 5. Current transit-route creation flow

The existing real transit-route creation endpoint is still legacy SSH/RQ based.
It expects a selected transit resource to be an active server resource with SSH
metadata and a provided SSH private key.

The current real creation path requires:

- selected transit resource exists,
- `resource_type == server`,
- `status == active`,
- `has_ssh == true`,
- `ssh_host`, `ssh_port`, and `ssh_username` are present,
- operator uploads or pastes a transit-server SSH private key,
- backend stores the SSH key as a temporary credential,
- backend enqueues an RQ job such as `create_transit_route_job` or
  `create_socat_route_job`.

This legacy creation path does not yet match the current Worker-based transit
server onboarding path.

## 6. Reconciliation finding

The current UI direction is correct:

- Transit Servers is the resource onboarding layer.
- Transit Links is the route composition layer.

The current implementation has a remaining flow gap:

| Area | Current state |
| --- | --- |
| Transit server onboarding | Worker based and bound to `transit_resources.id` |
| Worker status / check | Worker registration, heartbeat, and read-only `collect_status` / `service_status` style commands exist |
| Transit link planning | Local / no-op read-only preflight plan exists |
| Real transit-route creation | Still legacy SSH/RQ based and expects SSH metadata |
| Worker-based route creation | Not yet implemented / not authorized |

Therefore a newly added Worker transit server can be onboarded and checked, but it
cannot safely be assumed to work with the old SSH-based real route creation path.

## 7. Correct future target flow

The intended future Worker-based route flow should be:

1. Add transit server through Transit Servers.
2. Generate the bound `role=transit` Worker install command.
3. After explicit operator approval, manually run the install command on the VPS.
4. Confirm Worker registration and heartbeat.
5. Run only read-only Worker checks.
6. Open Transit Links.
7. Select the online transit server.
8. Select the accepted landing node, currently `liveline-reality-27939`.
9. Generate or record one candidate TCP listener port from `10000-30000`.
10. Generate a no-op read-only preflight plan.
11. If approved, run a separately authorized read-only preflight.
12. Only after that, open a separate real execution approval stage.
13. Real route creation must remain No-Go until a Worker-based create route command
    is designed, implemented, validated, and separately approved.

## 8. Immediate next recommended stages

Recommended follow-up stages:

1. `Stage 3.3.49-transit-worker-install-approval` — record whether the operator
   allows manually running the generated Worker install command on
   `香港中转服务器` / `163.223.216.108`. This should install only Worker and must not
   create transit links.
2. `Stage 3.3.50-transit-worker-registration-acceptance` — after manual install,
   record Worker registration / heartbeat / online acceptance.
3. `Stage 3.3.51-transit-link-worker-readonly-plan` — in Transit Links, select the
   online transit server, accepted landing node, and candidate `10000-30000` port,
   then generate only a no-op / read-only plan.
4. `Stage 3.3.52-transit-worker-readonly-preflight-execution-approval` — approve
   only read-only Worker checks for the selected route plan.
5. Future implementation stage — design Worker-based transit route creation. This
   must not reuse the old SSH/RQ route creation path without explicit migration or
   compatibility work.

## 9. UI / backend cleanup recommendations

Future code work should consider:

- Clearly marking the old SSH-based route creation path as legacy.
- Hiding or disabling old SSH route creation controls for Worker-only transit
  resources.
- Adding a Worker-specific route planning path in Transit Links.
- Preventing Worker `pending_worker` / `worker_online` resources with missing SSH
  metadata from being submitted to the legacy create route endpoint.
- Showing a clear message: Worker transit resources require Worker-based route
  creation flow; legacy SSH route creation requires SSH metadata and is not the
  default path.
- Keeping all full client links and private credentials redacted by default.

## 10. No-Go boundary for this stage

Stage 3.3.48 does not:

- run the generated Worker install command,
- execute SSH,
- execute Worker commands,
- run read-only preflight,
- install Worker on any real VPS,
- install `socat` or `gost`,
- create or modify systemd services,
- create a transit route,
- generate a usable transit client endpoint,
- generate or bind a real listener port,
- open or modify firewall rules,
- modify cloud security groups or cloud firewalls,
- modify iptables / nftables,
- modify Xray config,
- modify `nodes.share_link`,
- export full client links,
- create, delete, rebuild, or rotate nodes,
- run database migrations,
- deploy the public console,
- perform cutover.

## 11. Sensitive-data handling

This document intentionally excludes:

- complete Worker install command,
- full one-time Worker token,
- Worker secret,
- full `vless://` links,
- full `nodes.share_link` values,
- Reality private keys,
- database passwords,
- full Xray configuration,
- provider credentials,
- SSH private keys.

## 12. Stage result

Stage 3.3.48 is complete when this document is merged.

Result:

- Current UI layer responsibilities are corrected and recorded.
- The Worker-based transit server onboarding flow is recorded as the current
  correct flow.
- The legacy SSH/RQ transit-route creation gap is recorded.
- The current selected transit server state is recorded without sensitive token
  material.
- Next recommended stage is Worker install approval, not route creation.
