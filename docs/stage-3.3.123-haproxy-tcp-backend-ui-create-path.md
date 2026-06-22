# Stage 3.3.123 — HAProxy TCP backend/UI create path

## Stage entry

Stage 3.3.123 starts after Stage 3.3.122 was merged and the public controller pulled main successfully.

Baseline merged Stage 3.3.122 commit:

```text
6142fa1d531dfe70de914d04b8cdb2a4c0f98e63
```

Stage branch:

```text
stage-3.3.123
```

## Goal

Add backend and UI create-path support for choosing the forwarding method:

```text
socat
haproxy_tcp
```

The UI may display the HAProxy option as `HAProxy TCP mode`.

## Non-goals

```text
No public deploy.
No Worker binary rebuild or replacement.
No real HAProxy route creation.
No existing socat route stop/restart/delete.
No Xray mutation.
No firewall, cloud security group, or cloud firewall mutation.
No cutover.
No nodes.share_link full read, print, log, or mutation.
No transit_routes.share_link write.
No full VLESS/V2Ray link in docs, PR, logs, or chat.
```

## Current baseline observations

### Backend schema

`backend/app/schemas/transit_route.py` already defines and normalizes:

```text
FORWARDING_METHOD_HAPROXY_TCP = "haproxy_tcp"
normalize_forwarding_method("haproxy") -> "haproxy_tcp"
normalize_forwarding_method("haproxy-tcp") -> "haproxy_tcp"
```

Readonly preflight, dry-run plan, and real execute request models already accept normalized `forwarding_method`.

### Backend route handler

`backend/app/api/routes/transit_routes.py` already passes `payload.forwarding_method` into readonly preflight Worker command payloads and matching preflight lookup.

Current remaining blockers are fixed socat approval checks and generic Worker version selection:

```text
worker-create-plan still requires payload.forwarding_method == APPROVED_TRANSIT_FORWARDING_METHOD
worker-create-execute still requires payload.forwarding_method == APPROVED_TRANSIT_FORWARDING_METHOD
resolve_command_target_worker(... command_type="transit_route_create") still uses the generic socat-capable version floor
response minimum_supported_worker_version still reports the generic transit_route_create version
UI simplified create form hardcodes forwarding_method="socat"
```

### Backend Worker version helper

`backend/app/services/worker_targeting.py` already has:

```text
minimum_worker_version_for_transit_forwarding_method()
minimum_worker_version_key_for_transit_forwarding_method()
worker_supports_transit_forwarding_method()
```

Stage 3.3.123 should use those helpers when the selected forwarding method is `haproxy_tcp`.

## Backend implementation target

### 1. Add forwarding method constants/helpers to transit_routes.py

Suggested helpers:

```python
SUPPORTED_WORKER_CREATE_FORWARDING_METHODS = {"socat", "haproxy_tcp"}


def create_forwarding_method_label(method: str) -> str:
    if method == "haproxy_tcp":
        return "HAProxy TCP mode"
    return "socat"
```

### 2. Replace fixed socat method guard for plan and execute

Instead of:

```python
if payload.forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD:
    ... only socat ...
```

Use:

```python
if payload.forwarding_method not in SUPPORTED_WORKER_CREATE_FORWARDING_METHODS:
    return error_response(400, "TRANSIT_METHOD_NOT_SUPPORTED", "当前只允许 socat 或 HAProxy TCP mode。")
```

Keep existing fixed socat approvals for the existing 23843 socat route where applicable. HAProxy creation must still require matching readonly preflight and explicit confirmations.

### 3. Worker version gating by forwarding method

After resolving a target worker, verify:

```python
worker_supports_transit_forwarding_method(target_worker, payload.forwarding_method)
```

If not supported, return a clear error:

```text
WORKER_FORWARDING_METHOD_UNSUPPORTED
当前在线 Worker 版本不支持所选转发方式，请先升级中转 Worker。
```

Response should report:

```python
minimum_worker_version_for_transit_forwarding_method(payload.forwarding_method)
```

rather than the generic `minimum_worker_version_for_command("transit_route_create")`.

### 4. HAProxy route naming/service naming

For `haproxy_tcp`, backend/UI should produce LiveLine-owned names consistent with Worker helper:

```text
route_name: hk-haproxy-live-<listen_port>
service_name: liveline-haproxy-<listen_port>.service
service_path: /etc/systemd/system/liveline-haproxy-<listen_port>.service
```

The Worker remains the source of truth for actual config/service file creation.

### 5. Keep share-link and cutover boundaries unchanged

The backend must continue to avoid reading or writing full node links during create commands. Candidate export remains transient and is still the only plaintext candidate-link response point.

## UI implementation target

### 1. TypeScript forwarding method type

In `frontend/lib/api.ts`, update create-path request types from only `socat` / `gost` to include `haproxy_tcp` where appropriate.

Suggested shared type:

```ts
export type TransitForwardingMethod = "socat" | "gost" | "haproxy_tcp";
```

For real create request:

```ts
forwarding_method: "socat" | "haproxy_tcp";
```

### 2. TransitRoutesPanel simplified create modal

Currently simplified create hardcodes `socat`. Stage 3.3.123 should add a select:

```text
socat
HAProxy TCP mode
```

The submitted readonly preflight and create execute payloads should both use `createForm.forwardingMethod`.

### 3. UI warnings for HAProxy TCP mode

When HAProxy TCP mode is selected, show:

```text
中转 VPS 必须已安装 HAProxy。
HAProxy TCP mode 会创建 liveline-haproxy-<port>.service。
新监听端口必须已在云安全组、云防火墙、服务器本机防火墙放行。
当前页面不会自动安装 HAProxy，不会修改防火墙，不会 cutover。
```

### 4. Progress labels

Progress label can change based on selected method:

```text
socat: 创建 socat 服务 / 检查监听
haproxy_tcp: 创建 HAProxy TCP 服务 / 检查监听
```

## Validation target

Run from repository root / module locations as appropriate:

```bash
python3 -m compileall backend/app
cd frontend && npm run lint
cd frontend && npm run build
```

If frontend lint/build commands are not configured, report the exact failure and run the closest available validation.

## Safety reminder

Real HAProxy route creation must be delayed until a later explicitly authorized stage. Before any new HAProxy listen port is created, the user must confirm all three are open for the chosen TCP port:

```text
cloud security group
cloud firewall
server local firewall
```
