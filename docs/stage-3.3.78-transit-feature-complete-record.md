# Stage 3.3.78 Transit Feature Complete Record

## Stage Goal

Stage 3.3.78 records the product principle and current feature-complete line
for the lightweight transit-building workflow.

This project is a self-use lightweight network setup and troubleshooting helper.
It is not intended to become a complex commercial node platform.

This stage is documentation-only. It does not change code, deploy the public
console, execute production commands, or run client tests.

## Product Positioning

The current priority is to complete the "build the network" workflow:

- automatically create direct landing nodes;
- automatically create transit routes;
- view node and transit route status;
- transiently export or copy client test configuration;
- confirm that clients can browse normally after import;
- retain the original direct node;
- avoid accidental `nodes.share_link` mutation;
- avoid automatic cutover;
- avoid complex recommendation, automatic switching, or broad state-machine
  behavior.

The system should stay simple, direct, and easy to reason about.

## Current Functional Closure

The current workflow has reached the intended lightweight network-building
closure:

- direct landing node creation has been automated;
- the approved Hong Kong `socat` transit route has been created;
- transit route status can be viewed;
- `liveline-socat-23843.service` remains active;
- `23843/TCP` remains listening;
- candidate route UI can display the route context;
- candidate summary can be viewed without exposing the full node link;
- transient candidate export works;
- HTTP manual-copy fallback works;
- client import can browse normally after the observed warm-up period;
- the exit remains the landing VPS / landing region;
- the original direct node remains retained;
- `nodes.share_link` remains unchanged;
- `transit_routes.share_link` remains unwritten for the candidate route;
- no automatic cutover has occurred.

## Troubleshooting Scope

The troubleshooting module is intentionally not expanded in the current stage.

Troubleshooting should be planned as a later independent stage after the
network-building workflow is accepted as complete. Future troubleshooting
features may include:

- Worker online-state diagnosis;
- port listening checks;
- Xray status checks;
- `socat` status checks;
- transit route connectivity checks;
- client-unavailable reason hints;
- log summaries;
- one-click read-only diagnosis.

Those capabilities should be designed separately and reviewed for complexity,
risk, and operational value before implementation.

## Development Principles

Future work should follow these principles:

- prefer simple and clear flows;
- prioritize self-use efficiency;
- keep buttons and actions few enough to avoid misoperation;
- focus on completing setup and copying usable configuration;
- avoid platform-style complexity unless the user explicitly approves it;
- when a new suggestion appears, explain its purpose, impact, and complexity
  before implementation.

## Non-Goals For This Record

Stage 3.3.78 does not:

- perform cutover;
- mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- read or export full `nodes.share_link`;
- generate or record a full node link;
- create a Worker command;
- restart, stop, disable, or delete `socat`;
- modify Xray;
- modify firewall, cloud firewall, or cloud security group rules;
- execute SSH or remote commands;
- add a database migration;
- change backend or frontend code;
- deploy the public console;
- execute client tests.

## Next Stage Guidance

Recommended next-stage choices:

- `Stage 3.3.78-route-promotion-decision` if the operator wants to decide
  whether the candidate route should become a recommended entry;
- `Stage 3.3.79-longer-stability-test-result` if the operator wants more
  observation before any route-promotion decision;
- `Stage 3.3.80-public-console-https-reverse-proxy` if the operator wants to
  harden public console access and restore browser secure-context behavior.

Troubleshooting expansion should remain a later standalone planning stage.
