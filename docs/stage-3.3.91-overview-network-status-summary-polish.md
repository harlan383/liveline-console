# Stage 3.3.91 Overview Network Status Summary Polish

## Purpose

Stage 3.3.91 turns the `总览` page into a network-build status summary. The operator should be able to see, at a glance:

- whether landing servers are present
- whether a direct Reality node exists and has exportable client configuration
- whether transit server Workers are online
- whether a transit route is active
- whether cutover is still not executed
- whether anything needs attention

This is a frontend-only usability polish stage. It does not change backend APIs, Worker behavior, database schema, or production network state.

## Product Principle

LiveLine Console is a lightweight self-use network-building and troubleshooting helper, not a commercial node platform.

The current priority is to finish and simplify the network-building workflow:

- add / read landing VPS records
- create direct Reality nodes
- create transit routes
- transiently export client test configuration
- keep original direct nodes retained
- avoid accidental `nodes.share_link` mutation
- avoid automatic cutover

Troubleshooting is intentionally deferred to a later independent module.

## Displayed Summary

The overview page now focuses on four core status cards:

1. `落地服务器`
   - count of landing server records
   - whether records are present
   - Worker-online summary when available

2. `直连节点`
   - whether a direct node exists
   - entry IP and port
   - whether client configuration can be exported

3. `中转服务器`
   - count of transit server resources
   - Worker online/offline state
   - Worker version when available

4. `中转链路`
   - route status
   - transit entry and landing target
   - clear `未 cutover` marker

The page does not display complete node links and does not display raw `nodes.share_link`.

## Available Link Summary

The `当前可用链路` section shows only non-sensitive routing facts:

- direct node entry IP and port
- direct node configuration readiness
- transit route entry and target
- transit route status and purpose

It does not show VLESS links, Reality private material, full share links, tokens, or secrets.

## Safety Summary

The overview page explicitly records:

- `nodes.share_link`: not modified by the transit flow
- `transit_routes.share_link`: not written unless an existing route indicates otherwise
- `cutover`: not executed
- original direct node: retained

The page text clarifies that the system is currently used for network building and test configuration export, not automatic replacement of the original node.

## Next-Step Navigation

The overview page includes navigation-only buttons:

- `去落地服务器`
- `去中转服务器`
- `去中转链路`

These buttons only switch local frontend panels. They do not create Worker commands, execute remote checks, create nodes, create routes, or perform cutover.

## Not Implemented

This stage does not add:

- automatic diagnostics
- log reading
- Worker commands
- remote checks
- cutover
- node recommendation
- multi-route algorithms
- automatic node creation
- automatic transit route creation

The overview page is only a status summary plus navigation surface.

## Safety Boundary

This stage does not:

- execute cutover
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- display complete node links
- create Worker commands
- create VPS records
- create nodes
- create transit routes
- add listening ports
- restart, stop, or delete `socat`
- modify Xray
- modify firewalls, cloud firewalls, or cloud security groups
- execute SSH or remote commands
- add database migrations
- deploy the public console
- run client tests
- modify Worker binaries

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go builds are not required because this stage modifies only frontend display/CSS and documentation.

## Result

The overview page now reads as a network-build dashboard: landing, direct node, transit Worker, transit route, safety state, attention items, and navigation are visible without exposing complete node links or offering execution actions.
