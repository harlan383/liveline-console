# Stage 3.3.80 Network build usability polish plan

## Stage goal

This stage reviews the current LiveLine Console network-building pages and records a minimal usability polish plan.

This is a planning-only stage. It does not change UI behavior, backend APIs, Worker logic, database state, production services, or client configuration.

## Product position

LiveLine Console is a lightweight, self-use network setup and troubleshooting assistant. It is not intended to become a complex commercial node platform.

The near-term product goal is to keep the "build the network" flow simple:

- add landing and transit servers through Worker bootstrap;
- create the direct Reality landing node through controlled automation;
- create the Hong Kong `socat` transit route through controlled automation;
- view node / route state;
- temporarily export or copy client test configuration;
- import the client configuration and browse normally;
- retain the original direct node;
- avoid accidental `nodes.share_link` mutation;
- avoid automatic cutover;
- avoid complex recommendation, automatic switching, or broad platform state machines.

Troubleshooting should stay as a later independent module after the user confirms the network-building workflow is complete.

## Current network-building completion state

The current accepted workflow already covers the core setup path:

- direct VLESS Reality landing node creation has succeeded and passed client acceptance;
- Hong Kong `socat` transit route `hk-socat-live-23843` has been created and passed client candidate testing;
- the transit route remains active;
- `liveline-socat-23843.service` remains the accepted service for the candidate route;
- the transit route page can show the candidate summary;
- the candidate export endpoint can transiently produce a test client configuration;
- HTTP manual-copy fallback works when the browser Clipboard API is unavailable;
- the original direct node remains retained;
- `nodes.share_link` remains unchanged;
- `transit_routes.share_link` remains unwritten;
- no automatic cutover has occurred;
- Stage 3.3.79 recorded multi-resource support boundaries.

## Current page inventory

The codebase no longer has the old active `ReadVpsPanel.tsx` or `TransitResourcesPanel.tsx` components. Their old SSH/RQ flows have been removed from the active UI.

Current relevant pages are:

- `frontend/components/AppShell.tsx`: global navigation, page descriptions, topbar badges, dashboard.
- `frontend/components/ServerManagementPanel.tsx`: landing server records, Worker install command generation, node rows, share-link export, landing preflight, node dry-run / formal create controls.
- `frontend/components/TransitRoutesPanel.tsx`: transit server resource table, transit route planning, readonly preflight, Worker dry-run create plan, candidate summary, transient candidate export, route table.
- `frontend/lib/api.ts`: frontend types and API calls for nodes, transit resources, transit routes, Worker commands, and candidate export.
- README and stage docs: safety boundaries, accepted route records, feature-complete records, and multi-resource audit.

## Current complexity points

### Landing server / VPS flow

The landing server page is functional, but several advanced actions sit directly on each server row:

- `创建节点计划`
- `安装命令`
- `Worker 检查`
- `只读预检`
- `删除`

For self-use, this is powerful but visually busy. A new or occasional operator may not immediately know the next safe action after adding a landing server.

The page does show node rows and masked `share_link` state, but it could more plainly label the lifecycle:

1. server record created;
2. Worker installed / online;
3. preflight ready;
4. node exists;
5. client link export available;
6. client validation status.

### Direct node create / export flow

The direct node row supports view, copy, and QR-code actions. The safety boundary is strong: full links are hidden by default and exported only on demand.

The main usability gap is not the export itself, but the status language. The page could more explicitly say whether the direct node is:

- direct landing node;
- active;
- client-validated;
- original retained fallback;
- not replaced by the transit candidate.

### Transit server page

The transit server page is cleaner than older SSH/RQ flows and now focuses on Worker resources. It still exposes `Worker 检查` on the row, which is useful but may feel like a primary setup action.

For lightweight network setup, the primary status should be:

- Worker not installed;
- Worker online;
- usable for local route planning;
- not a transit route by itself.

Advanced checks can be visually secondary.

### Transit route page

The transit route page currently carries the most complexity. It contains:

- candidate route summary / transient export;
- route planning form;
- readonly preflight simple panel;
- Worker create path dry-run;
- route table;
- safety boundary details.

This is correct from a safety and audit perspective, but it mixes normal user tasks with engineering / debugging tasks. For day-to-day self-use, the most important visible area should be:

- route name;
- entry `transit IP:port`;
- target `landing IP:port`;
- service status / service name;
- route status;
- client validation state;
- `share_link` database state;
- cutover state;
- transient export action.

Readonly preflight and dry-run create path are important, but after a route has been created and accepted they should not compete with the candidate route card.

### Global navigation / status badges

`AppShell.tsx` still contains global status copy around older `socat 18443` and `gost 8443` routes. Given the current accepted candidate route is `hk-socat-live-23843`, this legacy status can confuse the operator.

This is a documentation-stage observation only. A later UI polish stage should update the global status wording to reflect:

- current accepted candidate: Hong Kong `socat` 23843;
- original direct node retained;
- no automatic cutover;
- no default `nodes.share_link` mutation.

### Error prompts

Several API failures currently bubble up as `ERROR_CODE: message`. This is useful for development but can be too technical for self-use.

Common failures should be mapped to plain operator-facing hints:

- Worker offline;
- Worker version unsupported;
- public console URL not configured;
- session expired / CSRF invalid;
- planned port not allowed or already in use;
- target landing port not reachable;
- candidate route not active;
- database or backend health issue.

This should be a small polish layer, not a full troubleshooting module.

## Usability optimization table

| Area | Current issue | Affects network setup? | Suggested optimization | Complexity | Priority |
| --- | --- | --- | --- | --- | --- |
| Global topbar / sidebar status | Legacy `socat 18443` / `gost 8443` copy can conflict with the accepted `hk-socat-live-23843` route context. | Yes. It can confuse which path is current. | Update global badges to say accepted candidate `socat 23843`, direct node retained, no automatic cutover. | S | P0 |
| Transit route page | Candidate route, planning, readonly preflight, dry-run create path, and route table all appear in one flow. | Yes. Advanced controls can distract from the simple export/test workflow. | Put readonly preflight and Worker dry-run create path under a collapsed `高级调试 / 创建前检查` section by default. | S-M | P0 |
| Transit route candidate card | The candidate summary is present, but service/client/database/cutover status could be clearer at a glance. | Yes. This is the main "can I use it?" page. | Add a compact status summary: entry, target, service, route, client validation, database link state, cutover state. | S-M | P1 |
| Candidate export area | Export is safe, but the operator still has to read several confirmations to understand it is temporary. | Yes. Export is a normal self-use action. | Rewrite export copy around one plain message: temporary test config, no DB write, original node unchanged, manual client import. | S | P1 |
| HTTP manual copy fallback | Fallback exists and works, but could be visually framed as expected under HTTP. | Yes, for current public console access. | Keep textarea fallback, add short note that HTTPS later restores automatic clipboard support. | S | P2 |
| Landing server row actions | Many actions appear at the same level: plan, install command, edit, Worker check, preflight, delete. | Somewhat. It can slow the user down. | Group `Worker 检查` and `只读预检` under `高级检查`; keep `安装命令` and node actions primary. | M | P1 |
| Landing node create modal | Dry-run and formal create concepts are visible and technical. | Yes, but only during create flow. | Add a small stepper: Worker online -> preflight -> plan -> confirm create -> export link. | M | P2 |
| Direct node row | It shows share-link status but does not explicitly call out "original direct node retained". | Somewhat. | Add a muted badge on the accepted direct node: `原直连节点 / 保留`. | S | P1 |
| Transit server row | Worker check is row-level primary, while the main useful status is Worker online / usable for route planning. | Somewhat. | Add `可用于本地规划` when Worker is online; move `Worker 检查` secondary. | S-M | P1 |
| Route table buttons | `查看 / 诊断 / 删除` are visible even when some are disabled. | Somewhat. | Keep `查看`; move disabled diagnostics/delete into advanced or mark as later-stage unavailable. | S | P2 |
| Error messages | Raw error codes can be noisy. | Yes, when setup fails. | Add a small frontend dictionary for frequent errors and keep raw code in a detail line. | M | P1 |
| Troubleshooting module | Several checks exist inside setup pages, but no unified troubleshooting entry yet. | No for current setup completion. | Do not expand now. Plan it later as `Stage 3.3.90-troubleshooting-module-plan`. | XL | No |
| Multi-resource management | Stage 3.3.79 shows data support but automation is single-route locked. | Not for current self-use route. | Avoid broad multi-resource platform work until a second route/server is actually needed. | L-XL | No |

Complexity scale:

- S: text, display, section order, or collapsed UI only.
- M: small frontend logic adjustment.
- L: backend API or database behavior involved.
- XL: broad platform behavior or operational state machine.

Priority scale:

- P0: reduces safety confusion or misoperation risk.
- P1: noticeably improves self-use speed.
- P2: useful later.
- No: not recommended now because it adds platform complexity.

## Recommended first 1-3 small changes

### 1. Collapse advanced transit route debugging sections

Recommended next stage: `Stage 3.3.81-transit-page-advanced-sections-collapse`

Default-collapse:

- readonly preflight controls;
- Worker allowlist wording;
- Worker dry-run create path;
- future real-create approval controls if exposed;
- disabled diagnosis/delete controls.

Keep the candidate route card and transient export controls prominent.

Why first:

- no database change;
- no Worker change;
- no production action;
- reduces accidental clicks;
- keeps the normal self-use workflow focused.

### 2. Add clearer route and node status summary cards

Recommended next stage: `Stage 3.3.82-network-build-status-summary-ui`

For the transit candidate card, show:

- entry: `163.223.216.108:23843`;
- target: `64.90.13.19:27939`;
- service: `liveline-socat-23843.service`;
- route status: active;
- client validation: passed / not recorded;
- database link: not written;
- cutover: not switched.

For the direct node row, show:

- original direct node retained;
- active status;
- link generated but hidden;
- client validation status if recorded.

Why second:

- it helps the operator understand the current topology without opening docs;
- it does not need new remote commands if based on existing API fields and accepted records;
- it reduces confusion between direct node, candidate route, and cutover.

### 3. Polish transient export and copy text

Recommended next stage: `Stage 3.3.83-export-copy-text-polish`

Make the export area say, in plain language:

- this is a temporary test configuration;
- it does not replace the original direct node;
- it does not write to the database;
- it does not change `nodes.share_link`;
- it does not cut over;
- copy it and manually import it into the client.

Why third:

- the export flow is already functional;
- copy fallback is already implemented;
- wording polish is low risk and directly improves self-use.

## What not to do now

Do not build a complex route platform yet:

- no automatic recommendation engine;
- no automatic cutover;
- no automatic route switching;
- no multi-route load balancing;
- no traffic statistics platform;
- no subscription system;
- no broad route state machine;
- no generic multi-node Xray manager until explicitly needed.

If a future suggestion adds complexity, first explain its purpose, impact, and complexity, then ask the user whether it is worth doing.

## Troubleshooting module boundary

This stage does not implement troubleshooting.

Later, after the user accepts the network-building flow as complete, a standalone troubleshooting plan may include:

- Worker online status checks;
- port listening checks;
- Xray status checks;
- `socat` status checks;
- transit route connectivity checks;
- client-unavailable reason hints;
- log summaries;
- one-click readonly diagnosis.

Recommended future stage:

- `Stage 3.3.90-troubleshooting-module-plan`

## Suggested next stages

- `Stage 3.3.81-transit-page-advanced-sections-collapse`: collapse advanced transit-route debug sections by default.
- `Stage 3.3.82-network-build-status-summary-ui`: add clearer direct/transit status summaries.
- `Stage 3.3.83-export-copy-text-polish`: simplify transient export and manual copy wording.
- `Stage 3.3.90-troubleshooting-module-plan`: plan troubleshooting only after the network-building flow is accepted.

## Safety boundary for this stage

This stage did not:

- perform cutover;
- mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- read or export the full `nodes.share_link`;
- generate or record a full node link;
- create Worker commands;
- create a new VPS;
- create a node;
- create a transit route;
- add listening ports;
- restart, stop, disable, or delete `socat`;
- modify Xray;
- modify firewall, cloud firewall, or cloud security group rules;
- execute SSH or remote commands;
- add a database migration;
- deploy the public console;
- execute client tests;
- change backend, frontend, or Worker code.

## Validation checklist

- `git diff --check`
- `git diff --cached --check`
- Sensitive information scan: no Worker secret, token, SSH private key, database password, complete candidate link, complete node link, or real `nodes.share_link` value in README/docs.

No backend, Go, or frontend build is required because this stage changes only README and documentation.
