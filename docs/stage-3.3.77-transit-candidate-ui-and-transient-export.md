# Stage 3.3.77 Transit Candidate UI And Transient Export

## Stage Goal

Stage 3.3.77 adds safe candidate route visibility and transient client export
for the already validated Hong Kong `socat` `23843/TCP` candidate path.

This stage does not perform cutover, mutate `nodes.share_link`, write
`transit_routes.share_link`, replace the original direct node, create Worker
commands, restart or stop `socat`, modify Xray, change firewall rules, or run
SSH / remote commands.

## Current Candidate Route

| Field | Value |
| --- | --- |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| route name | `hk-socat-live-23843` |
| transit entry | `163.223.216.108:23843` |
| forwarding target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| service | `liveline-socat-23843.service` |
| route status | `active` |
| service status | `active / enabled` |
| client manual test | `passed` |
| short stability | `3-5 minutes passed` |
| route share_link | `NULL / empty` |
| cutover status | `not_cutover` |

## Backend Additions

Two authenticated transit-route candidate endpoints were added:

- `GET /api/transit-routes/{route_id}/candidate-summary`
- `POST /api/transit-routes/{route_id}/candidate-export`

The summary endpoint returns only a safe candidate summary:

- route id and route name
- transit resource id / name
- candidate entry host and listen port
- landing target host and port
- forwarding method
- service name / path
- route status
- landing node id / name and landing VPS IP
- route share-link presence only
- `recommended_candidate=true`
- `cutover_status=not_cutover`
- safety boundary

It does not return a full client link or full `nodes.share_link`.

The transient export endpoint requires all confirmations:

- `confirm_transient_export=true`
- `confirm_no_database_write=true`
- `confirm_no_share_link_mutation=true`
- `confirm_no_cutover=true`

When confirmed, it returns a transient candidate test configuration for
administrator copy/import. The full candidate link is returned only in that
single response, is not written to the database, and is not recorded in audit
logs.

## Frontend Additions

The `中转链路` page now includes a candidate route panel:

- shows `hk-socat-live-23843`
- shows the candidate entry and landing target
- shows service and route status
- shows route share-link status as `NULL / 未写入`
- shows cutover status as `未切换`
- provides `查看候选配置摘要`
- provides `临时导出测试配置`

Before transient export, the operator must confirm:

- this is a transient export
- no database write
- no `nodes.share_link` mutation
- no cutover
- original direct node remains retained

The frontend displays only the masked candidate link by default. The full
candidate link can be copied from the transient response but is not rendered as
a persistent text field.

## Audit And Link Safety

The export endpoint records an audit event with only route-level identity:

- action: `export_transit_route_candidate`
- resource type: `transit_route`
- resource id: candidate route id

The audit record does not include the full candidate link, Worker secret, token,
SSH private key, database password, or full node link.

## Tests

Backend tests cover:

- export rejects missing confirmation
- missing route returns 404
- non-active route is rejected
- candidate summary does not return full node share link
- candidate export returns the candidate server and port
- candidate export preserves Reality parameter presence flags
- candidate export does not mutate `nodes.share_link`
- candidate export does not write `transit_routes.share_link`
- audit does not include the full candidate link

## Stage Boundary

Stage 3.3.77 did not:

- perform cutover
- mutate `nodes.share_link`
- write `transit_routes.share_link`
- replace or delete the original direct node
- create a Worker command
- add a listening port
- restart, stop, disable, or delete `socat`
- modify Xray
- modify firewall, cloud firewall, or cloud security group rules
- execute SSH or remote commands
- add a database migration

## Next Stage Recommendation

Proceed to `Stage 3.3.77b-system-test-candidate-export` to validate the UI and
transient export flow end to end.

Alternatively, proceed to `Stage 3.3.78-route-promotion-decision` if the
operator wants to decide whether this candidate should move toward formal route
promotion after system testing.
