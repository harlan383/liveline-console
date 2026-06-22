# Stage 3.3.123-b — backend/UI implementation patch

## Purpose

Apply the first implementation patch for Stage 3.3.123 so the transit route create path can choose either:

```text
socat
haproxy_tcp
```

The UI may display `haproxy_tcp` as `HAProxy TCP mode`.

## Safety boundary

```text
No public deploy.
No docker compose up/down/restart.
No Worker binary rebuild or replacement.
No real HAProxy route creation test.
No existing socat service stop/restart/delete.
No Xray mutation.
No firewall, cloud security group, or cloud firewall mutation.
No cutover.
No full node/share link in commits, logs, docs, or PR.
No transit_routes.share_link write.
```

## Files to patch

```text
backend/app/api/routes/transit_routes.py
frontend/lib/api.ts
frontend/components/TransitRoutesPanel.tsx
docs/stage-3.3.123-haproxy-tcp-backend-ui-create-path.md
```

## Backend patch target

### 1. Imports

In `backend/app/api/routes/transit_routes.py`, extend the schema imports to include:

```python
FORWARDING_METHOD_HAPROXY_TCP,
FORWARDING_METHOD_SOCAT,
```

Extend worker targeting imports to include:

```python
minimum_worker_version_for_transit_forwarding_method,
worker_supports_transit_forwarding_method,
```

### 2. Constants

Near the command constants, add:

```python
TRANSIT_ROUTE_CREATE_FORWARDING_METHODS = {
    FORWARDING_METHOD_SOCAT,
    FORWARDING_METHOD_HAPROXY_TCP,
}
```

### 3. Boundary text

Change generic text that says only fixed socat template to neutral method-specific wording where it applies to both methods. For example:

```text
fixed forwarding template selected by forwarding_method only
```

Do not remove the safety statements about no arbitrary shell, no firewall mutation, no Xray mutation, no cutover, and no share-link mutation.

### 4. worker-create-plan

In `create_transit_route_worker_create_plan`, replace the fixed `payload.forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD` guard with an allowlist guard:

```python
if payload.forwarding_method not in TRANSIT_ROUTE_CREATE_FORWARDING_METHODS:
    return error_response(400, "TRANSIT_METHOD_NOT_SUPPORTED", "当前只允许 socat 或 HAProxy TCP mode。")
```

Keep the existing fixed approval checks for resource, landing node, listen port, landing target host, and landing target port unchanged in this first patch unless a test proves they must change. This means Stage 3.3.123-b adds method support but does not yet generalize all route targets.

After resolving `target_worker`, add:

```python
if not worker_supports_transit_forwarding_method(target_worker, payload.forwarding_method):
    return error_response(
        400,
        "WORKER_FORWARDING_METHOD_UNSUPPORTED",
        "当前在线 Worker 版本不支持所选转发方式，请先升级中转 Worker。",
        {
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(payload.forwarding_method),
            "target_worker_version": target_worker.worker_version,
            "forwarding_method": payload.forwarding_method,
        },
    )
```

Set the route name according to the method:

```python
route_name = payload.route_name if hasattr(payload, "route_name") else APPROVED_TRANSIT_ROUTE_NAME
```

If the plan request has no `route_name` field, use:

```python
route_name = (
    f"hk-haproxy-live-{payload.planned_listen_port}"
    if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP
    else APPROVED_TRANSIT_ROUTE_NAME
)
```

Return:

```python
"minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(payload.forwarding_method)
```

### 5. worker-create-execute

In `create_transit_route_worker_create_execute`, replace the fixed socat method guard:

```python
if payload.forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD:
```

with:

```python
if payload.forwarding_method not in TRANSIT_ROUTE_CREATE_FORWARDING_METHODS:
    return error_response(400, "TRANSIT_METHOD_NOT_SUPPORTED", "当前只允许 socat 或 HAProxy TCP mode。")
```

Keep the existing explicit checks for selected resource, node, listen port, target host, and target port for this first patch unless tests require otherwise.

After resolving `target_worker` and checking role/interface, add:

```python
if not worker_supports_transit_forwarding_method(target_worker, payload.forwarding_method):
    return error_response(
        400,
        "WORKER_FORWARDING_METHOD_UNSUPPORTED",
        "当前在线 Worker 版本不支持所选转发方式，请先升级中转 Worker。",
        {
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(payload.forwarding_method),
            "target_worker_version": target_worker.worker_version,
            "forwarding_method": payload.forwarding_method,
        },
    )
```

Return:

```python
"minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(payload.forwarding_method)
```

### 6. Firewall message

Replace hardcoded `23843/TCP` wording in confirmation errors with the selected port:

```python
f"必须确认云安全组已放行 {payload.planned_listen_port}/TCP。"
f"必须确认云防火墙已放行 {payload.planned_listen_port}/TCP。"
```

## Frontend API types

In `frontend/lib/api.ts`, add a shared type:

```ts
export type TransitForwardingMethod = "socat" | "gost" | "haproxy_tcp";
export type TransitCreateForwardingMethod = "socat" | "haproxy_tcp";
```

Then update:

```ts
TransitReadonlyPreflightCommandRequest.forwarding_method: TransitForwardingMethod;
TransitRouteWorkerCreateExecuteRequest.forwarding_method: TransitCreateForwardingMethod;
```

## Frontend TransitRoutesPanel patch target

### 1. Types

Change:

```ts
type ForwardingMethod = "socat" | "gost";
```

to:

```ts
type ForwardingMethod = "socat" | "gost" | "haproxy_tcp";
type CreateForwardingMethod = "socat" | "haproxy_tcp";
```

Change create form state:

```ts
forwardingMethod: CreateForwardingMethod;
```

### 2. Display labels

Add helper:

```ts
function forwardingMethodLabel(method: string) {
  if (method === "haproxy_tcp") return "HAProxy TCP mode";
  if (method === "socat") return "socat";
  if (method === "gost") return "gost";
  return method || "-";
}
```

Use this helper when displaying route forwarding method and create form selected method.

### 3. Simplified create modal

Replace read-only `socat` input with a select:

```tsx
<label>
  转发方式
  <select
    value={createForm.forwardingMethod}
    onChange={(event) =>
      setCreateForm({
        ...createForm,
        forwardingMethod: event.target.value as CreateForwardingMethod,
      })
    }
  >
    <option value="socat">socat</option>
    <option value="haproxy_tcp">HAProxy TCP mode</option>
  </select>
</label>
```

### 4. Submit selected method

In `submitSimplifiedTransitRouteCreate`, replace both hardcoded `forwarding_method: "socat"` payload values with:

```ts
forwarding_method: createForm.forwardingMethod,
```

### 5. Find created route

In `findCreatedTransitRoute`, replace the hardcoded check:

```ts
route.forwarding_method === "socat"
```

with:

```ts
route.forwarding_method === createForm.forwardingMethod
```

### 6. UI warning when HAProxy is selected

If `createForm.forwardingMethod === "haproxy_tcp"`, show a warning in the create modal:

```text
HAProxy TCP mode 要求中转 VPS 已安装 HAProxy。
创建后会使用 LiveLine 管理的 liveline-haproxy-<port>.service。
本页面不会自动安装 HAProxy，不会修改防火墙，不会 cutover。
新监听端口仍必须在云安全组、云防火墙、服务器本机防火墙中放行。
```

### 7. Progress text

Change the command-running label based on selected method where practical:

```text
socat: 创建 socat 服务 / 检查监听
haproxy_tcp: 创建 HAProxy TCP 服务 / 检查监听
```

If the current labels are static, a simple neutral label is acceptable:

```text
创建中转服务 / 检查监听
```

## Validation commands

Run from the repository root:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app
```

Run frontend validation from the frontend module:

```bash
cd frontend
npm run lint
npm run build
```

If lint/build are not configured or fail due to existing unrelated environment issues, report the exact output and do not hide it.

## Final report requirements

Report:

```text
modified files
commit id
git status
backend compile result
frontend lint/build result
whether any deploy happened: no
whether any Worker was replaced: no
whether any HAProxy route was created: no
whether current socat route was touched: no
whether firewall/security group/cloud firewall was changed: no
whether any share link was printed or written: no
```
