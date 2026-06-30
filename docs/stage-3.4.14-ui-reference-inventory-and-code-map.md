# Stage 3.4.14 UI Reference Inventory And Code Map

## Scope

Stage 3.4.14 is a documentation-only inventory pass. It maps the current productized frontend UI, the repository-visible reference/design assets, and the backend capabilities that can support future UI work.

This stage does not change code, API behavior, database schema, Worker behavior, deployment configuration, node data, route data, or share links.

## Reference Asset Inventory

本仓库未发现已提交的 UI 设计文件夹，本阶段基于已合并前端代码和 PR 语义进行盘点。

Checked repository paths and filename patterns included:

- Design or reference directories: `ui`, `design`, `reference`, `mockup`, `screenshots`, `figma`, `界面`, `参考图`
- Design or image files: `*.png`, `*.jpg`, `*.jpeg`, `*.webp`, `*.fig`, `*.figma`, `*.pdf`
- Product UI implementation files under `frontend/app` and `frontend/components`

No committed reference screenshots or Figma/design files were found in the repository. Previously supplied UI screenshots are external request context only; they are not copied, transformed, or committed in this stage.

## Frontend Entry Map

| User-facing page | Active component | Main purpose | Primary data source |
| --- | --- | --- | --- |
| 总览 | `frontend/components/AppShell.tsx` `DashboardPanel` | Product dashboard with counts, attention items, recent creations, and quick actions | Real API reads plus frontend fallback copy |
| 线路搭建 | `frontend/components/LineBuilderPanel.tsx` | Customer-first line-building entry board and demo modals | Real API reads plus demo-only modal state |
| 客户线路 | `frontend/components/CustomerLinesPanel.tsx` | Customer line list, line health display, detail/edit/client modals | Real nodes/routes/resources when present, otherwise demo lines |
| 服务器资源 | `frontend/components/ServerResourcesPanel.tsx` | Landing/transit/provider resource overview | Real VPS, nodes, and transit resources |
| 任务记录 | `frontend/components/TaskHistoryPanel.tsx` | Business-friendly task history with collapsed technical details | Real tasks and task logs |
| 设置 | `frontend/components/AppShell.tsx` `SettingsPanel` | Local preference-style settings screen | Frontend local state only |
| 高级调试 | `frontend/components/AdvancedDebugPanel.tsx` | Access to original technical panels | Existing real technical panels |

`frontend/app/page.tsx` renders `AppShell` directly.

Shared UI helpers:

- `frontend/components/ProductIcons.tsx`: product icon set and platform icon labels.
- `frontend/app/globals.css`: main visual system for the product shell and pages.
- `frontend/app/ui-overrides.css`: later-stage density and alignment overrides.
- `frontend/lib/api.ts`: frontend API types and wrapper helpers.

## Current Product UI Data Flow

### App Shell And Navigation

`AppShell` owns the current product navigation:

- `dashboard`
- `lineBuilder`
- `customerLines`
- `serverResources`
- `tasks`
- `settings`
- `advancedDebug`

The topbar notification and help buttons are presentation-only. The sidebar health card currently displays a product status message and navigates to Advanced Debug when clicked.

Authentication uses:

- `GET /api/auth/me`
- `GET /api/auth/csrf`
- `POST /api/auth/logout`

### Overview Page

The overview dashboard reads:

- `GET /api/health`
- `GET /api/vps`
- `GET /api/nodes`
- `GET /api/transit-resources`
- `GET /api/transit-routes`
- `GET /api/tasks?limit=8`

Derived product signals:

- Normal line count combines active nodes and active routes.
- Risk count includes stale transit resources and failed/running task pressure.
- Abnormal count includes failed tasks.
- Pending count includes running tasks.
- Attention items combine real conditions with safe fallback reminders when no active nodes or routes exist.

Current gap:

- There is no backend `overview` aggregate endpoint.
- There is no persisted alert/notification model.
- The attention list is a frontend composition layer, not a durable notification system.

### Line Builder Page

`LineBuilderPanel` reads:

- `GET /api/vps`
- `GET /api/nodes`
- `GET /api/transit-resources`
- `GET /api/transit-routes`
- `GET /api/tasks?limit=8`

The four visible entry cards open frontend-only modals:

- `AddLandingServerModal`
- `AddTransitServerModal`
- `CreateDirectNodeModal`
- `CreateTransitLineModal`

Important boundary:

- These product modals do not call real create APIs.
- They keep the Stage 3.4 product flow safe by showing the intended experience without creating servers, nodes, routes, Worker commands, listeners, or share links.

Current gap:

- The productized builder is not wired to the real protected backend create flows.
- It lacks durable customer, platform, usage, and line ownership data.

### Customer Lines Page

`CustomerLinesPanel` reads:

- `GET /api/nodes`
- `GET /api/transit-routes`
- `GET /api/transit-resources`

It derives customer lines from:

- Active direct nodes.
- Active transit routes.
- Resource and node names, regions, and notes.

When no live line data is available, it falls back to `defaultDemoLines` for product UI continuity.

Frontend-only behavior:

- Customer/platform/purpose/mode classification is inferred from display text.
- Edit operations update local `lineOverrides` only and show a demo safety message.
- Client detail and monitoring modals are product displays, not persisted changes.
- Monitoring metrics are derived/fallback presentation values.
- QR-style display is frontend-only and does not upload or persist client material.

Safety behavior:

- Normal list views do not expose full client links.
- Technical client fields are masked or summarized.

Current gaps:

- No persisted customer model.
- No persisted line assignment model.
- No persisted main/backup line relation.
- No persisted platform, purpose, or customer ownership fields on nodes/routes.
- No real client-side connectivity telemetry model.

### Server Resources Page

`ServerResourcesPanel` reads:

- `GET /api/vps`
- `GET /api/nodes`
- `GET /api/transit-resources`

Tabs:

- Landing servers from `vps_servers`.
- Self-managed transit servers from `transit_resources` with `resource_type=server`.
- Provider transit entries from non-server `transit_resources`.

Actions:

- View opens a local detail modal.
- Add server opens demo-only product modals.
- New direct node and new transit line buttons open demo-only product modals.

Current gap:

- Product server onboarding is not wired to the real technical onboarding flows.
- Provider transit entry management is still UI-level; there is no dedicated provider-entry workflow model.

### Task History Page

`TaskHistoryPanel` reads:

- `GET /api/tasks?limit=30`
- `GET /api/tasks/{task_id}/logs`

Frontend behavior:

- Maps technical task types to business-friendly labels.
- Shows result advice derived from status and normalized result data.
- Keeps technical IDs, raw result JSON, and logs inside collapsed details.
- Redacts sensitive-looking values before display.

Current gap:

- Category/status/search filters are frontend-side.
- Date range controls are currently UI state only and are not used to query or filter results.
- There is no backend task search/filter API designed for the product task table.

### Settings Page

`SettingsPanel` uses local React state only:

- Default platform.
- Default landing region.
- Default port range.
- Reminder toggles.
- UI preference toggles.

Current gap:

- No persisted settings API or database table.
- Save/reset messages are frontend-local only.

### Advanced Debug Page

`AdvancedDebugPanel` preserves the original technical panels:

- `SystemStatus`
- `ServerManagementPanel`
- `TransitServersPanelWithWorkerFolding`
- `TransitRoutesPanel`
- `TransitTopologyPreviewPanel`

This page remains the bridge to existing real technical operations. Product pages intentionally keep safer, beginner-facing flows separate from these debug panels.

## Backend Capability Map

### Mounted Routers

`backend/app/main.py` mounts:

- `/api/health`
- `/api/admin`
- `/api/auth`
- `/api/nodes`
- `/api/tasks`
- `/api/transit-resources`
- `/api/transit-routes`
- `/api/vps`
- `/api/workers`
- Worker setup routes

The app also installs the HAProxy real-execution approval gate.

### Auth And Admin

Available capabilities:

- Admin initialization.
- Login/logout.
- Session and CSRF handling.
- Auth rate limiting.
- Audit logging.

Relevant files:

- `backend/app/api/routes/admin.py`
- `backend/app/api/routes/auth.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/auth_rate_limit.py`
- `backend/app/models/admin_user.py`
- `backend/app/models/admin_session.py`
- `backend/app/models/audit_log.py`

### Health

Available capabilities:

- Backend/database/Redis/Worker health check.

Relevant files:

- `backend/app/api/routes/health.py`
- `backend/app/schemas/health.py`

### Landing Servers And Direct Nodes

Available VPS and landing capabilities:

- List/create/update/delete landing VPS records.
- Generate Worker bootstrap/install material.
- Create landing node plan.
- Create protected landing node execution command.
- BBR enable plan/dry-run/real-execution flow.
- Remote cleanup delete and offline local remove.

Available node capabilities:

- List/detail nodes.
- Local delete record.
- Remote cleanup delete.
- Export node share link.
- Scrub deleted-node share links.

Relevant files:

- `backend/app/api/routes/vps.py`
- `backend/app/api/routes/nodes.py`
- `backend/app/schemas/landing_node_plan.py`
- `backend/app/services/landing_node_plan.py`
- `backend/app/services/landing_node_create.py`
- `backend/app/services/node_display.py`
- `backend/app/models/vps_server.py`
- `backend/app/models/node.py`

Important data notes:

- Direct node creation is protected and Worker-backed.
- Successful landing node creation writes `nodes.share_link` only after Worker success.
- Product UI currently does not call this real create flow.

### Transit Resources

Available transit-resource capabilities:

- List/create/update resources.
- Enable/disable/delete resource records.
- Remote cleanup delete and offline local remove.
- Worker bootstrap and install command generation with custom interface name.
- Worker acceptance and upgrade acceptance checks.

Relevant files:

- `backend/app/api/routes/transit_resources.py`
- `backend/app/schemas/transit_resource.py`
- `backend/app/services/worker_binding.py`
- `backend/app/models/transit_resource.py`

Important data notes:

- Resource types are `server`, `iepl`, `iplc`, and `other`.
- Statuses include `active`, `disabled`, `pending_worker`, `worker_online`, and `worker_offline`.
- Notes validation rejects sensitive markers.

### Transit Routes

Available transit-route capabilities:

- List/detail routes.
- Rename `transit_routes.name`.
- Local delete record.
- Remote cleanup delete and offline local remove.
- Candidate summary and transient candidate export.
- Read-only preflight planning and command creation.
- HAProxy readiness approval.
- HAProxy route create dry-run.
- Final approval.
- Real execution command creation.
- Legacy worker-create plan/execute paths.

Relevant files:

- `backend/app/api/routes/transit_routes.py`
- `backend/app/api/routes/transit_haproxy_real_execution_gate.py`
- `backend/app/schemas/transit_route.py`
- `backend/app/services/transit_route_create.py`
- `backend/app/services/share_link_compat.py`
- `backend/app/models/transit_route.py`

Important data notes:

- `transit_routes.name` is the display name.
- Internal route/service names remain separate from display names.
- Candidate export can return a transient client link, but the API also reports non-persistence flags.
- Real route creation is Worker-backed and guarded by planned listen port, target port, firewall confirmation, dry-run, final approval, and Worker version checks.
- Product UI currently does not call the real protected route create flow.

### Workers And Commands

Available Worker capabilities:

- Worker token creation.
- Worker setup script and binary download.
- Worker register and heartbeat.
- Worker command polling and result/failure reporting.
- Admin command creation.
- Worker and Worker command listing/detail.

Relevant files:

- `backend/app/api/routes/workers.py`
- `backend/app/schemas/workers.py`
- `backend/app/schemas/worker_commands.py`
- `backend/app/services/worker_commands.py`
- `backend/app/services/worker_targeting.py`
- `backend/app/models/worker.py`
- `backend/app/models/worker_command.py`

Important data notes:

- Minimum Worker versions are centralized in `worker_targeting.py`.
- Current frontend type constant is `CURRENT_WORKER_INSTALL_VERSION`.
- Command payload/result serialization redacts sensitive fields.

### Tasks And Logs

Available task capabilities:

- List tasks.
- Get task detail.
- Get task logs.

Relevant files:

- `backend/app/api/routes/tasks.py`
- `backend/app/schemas/tasks.py`
- `backend/app/models/task.py`
- `backend/app/models/task_log.py`
- `backend/app/services/task_logging.py`

Current gap:

- Product task history has no dedicated backend filtering/search API yet.

## Database Model Inventory

Existing SQLAlchemy models:

- `admin_users`
- `admin_sessions`
- `audit_logs`
- `vps_servers`
- `nodes`
- `tasks`
- `task_logs`
- `transit_resources`
- `transit_routes`
- `vps_task_locks`
- `worker_tokens`
- `workers`
- `worker_commands`

Existing migrations:

- Initial schema through Worker command channel.
- Transit resources and transit routes.
- VPS server management fields.
- Worker foundation and command channel.

No customer, customer-line, settings, notification, alert, platform, line assignment, or client telemetry table is currently present.

## Product UI Versus Real Capability Matrix

| Product requirement area | Current UI state | Current backend support | Gap |
| --- | --- | --- | --- |
| Customer list / customers | Derived labels and demo data | No customer model | Need customer/assignment model or explicit frontend-only decision |
| Customer lines | Derived from active nodes/routes or demo fallback | Nodes/routes exist | Need persisted ownership, platform, usage, main/backup relation |
| Overview cards | Frontend aggregates real API data | Health, VPS, nodes, resources, routes, tasks APIs exist | No overview aggregate/alert API |
| Today attention | Frontend-composed list | No notification/alert model | Need alert source of truth if alerts become real |
| Server resource cards | Real VPS/resources plus product rendering | VPS and transit resources APIs exist | Product onboarding is not connected to real create flows |
| Add landing/transit server modals | Demo-only | Real technical create/bootstrap APIs exist | Need safe product wrapper if/when enabled |
| Create direct node modal | Demo-only | Protected landing-node plan/create APIs exist | Need connect product modal to plan/create approval flow |
| Create transit line modal | Demo-only | Protected HAProxy dry-run/final/real execution APIs exist | Need connect product modal to preflight/approval/real create flow |
| Settings | Local React state only | No settings API/model | Need persisted settings API if settings matter |
| Task table | Real tasks, frontend labels/filtering | Task list/detail/log APIs exist | Need backend filters/date/search for scale |
| Advanced debug | Real technical panels retained | Existing technical APIs exist | Keep separate from product pages |

## Safe Reuse Opportunities

The next product stages can reuse existing protected backend flows without weakening safety boundaries:

- Direct node create:
  - Plan: `POST /api/vps/{vps_id}/landing-node-plan`
  - Execute: `POST /api/vps/{vps_id}/landing-node-create`
- Transit route create:
  - Readiness: `POST /api/transit-routes/haproxy-readiness-approval`
  - Dry-run: `POST /api/transit-routes/haproxy-route-create-dry-run`
  - Final approval: `POST /api/transit-routes/haproxy-route-create-final-approval`
  - Real execution: `POST /api/transit-routes/haproxy-route-create-real-execution`
- Worker install:
  - Landing bootstrap: `POST /api/vps/worker-bootstrap`
  - Transit install command: `POST /api/transit-resources/{resource_id}/worker-install-command`
- Cleanup:
  - Node/server/route/resource remote cleanup delete endpoints
  - Offline local remove modes

Any product connection to these APIs should preserve the existing approval gates, Worker version targeting, no-firewall-mutation boundary, no cutover boundary, and share-link mutation rules.

## Recommended Next Implementation Slices

1. **Customer metadata model design**
   - Decide whether customers and assignments become backend models.
   - Suggested entities: customer, line assignment, platform, purpose, main/backup role.
   - Avoid overloading `node_name`, `route.name`, or notes as durable customer metadata.

2. **Overview aggregate API**
   - Add a read-only aggregate endpoint only after data semantics are stable.
   - Keep alerts separate from hardcoded fallback copy.

3. **Product task filtering API**
   - Add status/type/date/search filters to task list.
   - Keep raw JSON/logs available only in technical detail views.

4. **Settings persistence**
   - If settings are product requirements, add a minimal user/admin settings model and API.
   - Until then, keep settings clearly local or demo-only.

5. **Product create flow integration**
   - Wire product modals to existing protected plan/dry-run/approval APIs in separate stages.
   - Do not bypass existing Worker command safety checks.
   - Preserve explicit port/firewall confirmation and no-share-link-mutation boundaries.

6. **Advanced Debug separation**
   - Keep all raw Worker/Xray/HAProxy/JSON details in Advanced Debug.
   - Product pages should continue to show business labels and safe summaries.

## Safety Boundary

This stage did not:

- Modify frontend runtime code.
- Modify backend API code.
- Modify database schema or migrations.
- Modify Worker code or binaries.
- Modify Docker Compose or deployment ports.
- Execute remote commands.
- Create, delete, or mutate nodes.
- Create, delete, or mutate transit routes.
- Create Worker commands.
- Read, output, or mutate full share links.
- Commit design screenshots or reference image assets.
