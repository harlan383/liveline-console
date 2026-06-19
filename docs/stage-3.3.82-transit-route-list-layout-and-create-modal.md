# Stage 3.3.82 Transit Route List Layout and Create Modal

## Purpose

Stage 3.3.82 reshapes the transit routes page into a simpler management layout that matches the landing server and transit server pages more closely. The page now emphasizes the existing route list, route status, candidate summary, and transient test export. Advanced planning and Worker-oriented controls remain available but stay collapsed by default.

LiveLine Console remains a lightweight self-use network build and troubleshooting helper. This stage does not turn it into a complex commercial node platform and does not introduce automatic recommendation, automatic switching, or cutover behavior.

## Layout Changes

- The page title remains `中转链路`.
- The subtitle now explains the daily workflow: add routes, view status, and transiently export test configuration.
- A top-level `新增中转链路` button was added next to `刷新`.
- Existing transit routes are displayed as management cards instead of a large candidate-debug panel.
- Each route card shows:
  - route name
  - entry host and port
  - landing target host and port
  - forwarding method
  - service name
  - route status
  - `SHARE_LINK` unwritten state
  - `CUTOVER` not switched state
- Each route card keeps ordinary actions:
  - `查看摘要`
  - `临时导出测试配置`

The full candidate link is not shown in the route list. It is only available through the existing transient export response and HTTP manual-copy fallback.

## Add Route Modal

The new `新增中转链路` modal lets the operator prepare a local configuration preview. It includes:

- route name
- transit server selector
- landing node / landing server selector
- transit listen port
- forwarding method, currently fixed to `socat`
- safety confirmations
- local configuration preview

The modal only generates local state. It does not call a real create API, does not create a Worker command, does not save a route to the database, and does not bind or open a port.

The preview includes:

- route name
- transit server
- entry port
- landing target
- forwarding method
- expected service name, such as `liveline-socat-<port>.service`
- explicit no-op safety boundary:
  - remote creation was not executed
  - Worker command was not created
  - listening port was not added
  - database `share_link` was not written
  - cutover was not executed

## Real Creation Boundary

Current real creation automation remains locked to the already verified production route:

- `hk-socat-live-23843`
- `23843/TCP`
- `64.90.13.19:27939`
- `liveline-socat-23843.service`

Multi-route real creation is intentionally not wired in this stage. If generic multi-route creation is needed later, it should be planned separately as:

- `Stage 3.3.84-transit-route-generic-create-plan`

## Advanced Section

The Stage 3.3.81 `高级调试与审批操作` section remains collapsed by default. It still contains:

- local planning controls
- readonly preflight controls
- Worker allowlist confirmation
- dry-run create path controls
- approval and debug controls

These controls are retained for development, approval, and troubleshooting, but they no longer dominate the daily route management page.

## Safety Boundary

This stage does not:

- Execute cutover.
- Modify `nodes.share_link`.
- Write `transit_routes.share_link`.
- Read or export complete `nodes.share_link`.
- Generate or record complete node links.
- Create Worker commands.
- Create VPS resources, nodes, or transit routes.
- Add listening ports.
- Restart, stop, or delete `socat`.
- Modify Xray.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Execute SSH or remote commands.
- Add database migrations.
- Deploy the public console.
- Run client tests.
- Modify backend APIs.
- Modify Worker binaries.

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go builds are not required because this stage does not modify backend or Worker code.

## Result

The transit routes page now behaves more like a concise management page: route cards are first-class, candidate summary and transient export remain available as normal route actions, and new route setup starts from a local preview-only modal. No production state changes are performed.
